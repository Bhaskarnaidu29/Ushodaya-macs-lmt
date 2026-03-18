# loanrec.py - Loan Recovery with Advance Integration
# Regular, Prepaid (with type-specific calculations), Arrears
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# Import advance module
try:
    from advance import get_advance_balance
    ADVANCE_ENABLED = True
    print("✅ Advance module loaded successfully")
except ImportError as e:
    ADVANCE_ENABLED = False
    print(f"⚠️ Advance module not found: {e}")

loanrec_bp = Blueprint("loanrec", __name__, template_folder="templates")


def _close_loan_if_done(cursor, loanid, user_id):
    """Close loan automatically when principal and interest are zero."""
    cursor.execute("""
        SELECT principaloutstanding, interestoutstanding
        FROM Loans
        WHERE loanid = ?
    """, (loanid,))
    
    row = cursor.fetchone()
    
    if not row:
        return
    
    principal = float(row[0] or 0)
    interest = float(row[1] or 0)
    
    # 1 paisa tolerance
    if principal <= 0.01 and interest <= 0.01:
        cursor.execute("""
            UPDATE Loans
            SET loanstatus = 'Closed',
                principaloutstanding = 0,
                interestoutstanding = 0,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanid = ?
        """, (user_id, loanid))


def _apply_advance_manually(cursor, member_code, loanid, loanrecid, amount_needed, user_id):
    """
    Apply advance when payment_mode = 'advance'.
    Returns: (amount_applied, new_balance)
    """
    if not ADVANCE_ENABLED:
        return (Decimal('0'), Decimal('0'))
    
    try:
        balance = get_advance_balance(member_code, loanid)
        
        if balance <= 0:
            return (Decimal('0'), Decimal('0'))
        
        amount_to_apply = min(balance, amount_needed)
        
        if amount_to_apply <= 0:
            return (Decimal('0'), balance)
        
        # Update LoanRec.advancerecovery
        cursor.execute("""
            UPDATE LoanRec
            SET advancerecovery = ISNULL(advancerecovery, 0) + ?,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanrecid = ?
        """, (float(amount_to_apply), user_id, loanrecid))
        
        # Insert Debit entry in AdvanceRecovery
        cursor.execute("""
            INSERT INTO AdvanceRecovery (
                member_code, loanid, amount, creditdebit, notes,
                createdby, createddate, transactiondate
            )
            VALUES (?, ?, ?, 'Debit', ?, ?, GETDATE(), GETDATE())
        """, (
            member_code, loanid, float(amount_to_apply),
            f"Applied via recovery dropdown to LoanRec #{loanrecid}",
            user_id
        ))
        
        new_balance = get_advance_balance(member_code, loanid)
        return (amount_to_apply, new_balance)
        
    except Exception as e:
        print(f"❌ Error applying advance: {str(e)}")
        import traceback
        traceback.print_exc()
        return (Decimal('0'), Decimal('0'))


# ═══════════════════════════════════════════════════════════════
# REGULAR RECOVERY POSTING WITH ADVANCE DROPDOWN
# ═══════════════════════════════════════════════════════════════
@loanrec_bp.route("/", methods=["GET", "POST"])
def recovery_posting():
    """Center-wise regular loan recovery posting with ADVANCE DROPDOWN."""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        staff = session.get("username", "admin")
        branchid = session.get("branchid", 1)
        user_id = session.get("user_id", 1)

        c.execute("""
            SELECT id, center_name, center_no
            FROM Center WHERE branchid=? ORDER BY center_name
        """, (branchid,))
        centers = c.fetchall()

        # Read center_id from GET args OR POST form (so POST submissions retain center)
        selected_center = request.args.get("center_id") or request.form.get("center_id")
        members = []
        center_info = None
        advance_balances = {}

        if selected_center:
            c.execute("""
                SELECT id, center_name, center_no
                FROM Center WHERE id=?
            """, (selected_center,))
            center_info = c.fetchone()

            # Get pending EMIs
            c.execute("""
                SELECT
                    m.member_code,                          -- [0]
                    m.full_name,                            -- [1]
                    l.loanid,                               -- [2]
                    lr.loanrecid,                           -- [3]
                    ISNULL(lr.emisequence, 0),              -- [4]
                    lr.duedate,                             -- [5]
                    lr.principaldueamount,                  -- [6]
                    lr.interestdueamount,                   -- [7]
                    lr.savingsdueamount,                    -- [8]
                    ISNULL(lr.principalpaidamount, 0),      -- [9]
                    ISNULL(lr.interestpaidamount, 0),       -- [10]
                    ISNULL(lr.savingspaidamount, 0),        -- [11]
                    ISNULL(lr.additionalsavingsdueamount, 0),   -- [12]
                    ISNULL(lr.additionalsavingspaidamount, 0),  -- [13]
                    lr.paid,                                -- [14]
                    ISNULL(LP.ProductName, 'N/A')           -- [15]
                FROM Members m
                JOIN Loans l ON m.member_code = l.member_code
                JOIN LoanRec lr ON l.loanid = lr.loanid
                LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
                WHERE m.center_id = ?
                  AND lr.paid = 0
                  AND lr.emisequence > 0
                  AND lr.duedate <= GETDATE()
                  AND l.loanstatus = 'Active'
                ORDER BY m.full_name, lr.emisequence
            """, (selected_center,))
            members = c.fetchall()
            
            # Get advance balances
            if ADVANCE_ENABLED and members:
                for m in members:
                    member_code = m[0]
                    loanid = m[2]

                    try:
                        if member_code not in advance_balances:
                            advance_balances[member_code] = {}

                        balance = get_advance_balance(member_code, loanid)
                        advance_balances[member_code][loanid] = float(balance)
                    except Exception as e:
                        print(f"Error getting balance for {member_code}/{loanid}: {e}")
                        advance_balances[member_code][loanid] = 0

        # POST: Process recovery
        if request.method == "POST":
            if not selected_center:
                flash("Please select a center first.", "warning")
                return redirect(url_for("loanrec.recovery_posting"))

            selected_members = request.form.getlist("selected_member")
            if not selected_members:
                flash("Please select at least one member.", "warning")
                return redirect(url_for("loanrec.recovery_posting", center_id=selected_center))
            
            try:
                posted_count = 0
                total_collected = Decimal('0')
                total_advance_used = Decimal('0')

                for loanrecid in selected_members:
                    principal = Decimal(str(request.form.get(f"principal_{loanrecid}", 0) or 0))
                    interest = Decimal(str(request.form.get(f"interest_{loanrecid}", 0) or 0))
                    savings = Decimal(str(request.form.get(f"savings_{loanrecid}", 0) or 0))
                    addl_due = Decimal(str(request.form.get(f"addl_due_{loanrecid}", 0) or 0))
                    extra_addl = Decimal(str(request.form.get(f"extra_addl_{loanrecid}", 0) or 0))
                    additional_sav = addl_due + extra_addl
                    
                    # Get payment mode
                    payment_mode = request.form.get(f"payment_mode_{loanrecid}", "cash")
                    
                    cash_payment = principal + interest + savings + additional_sav

                    # Skip only if truly nothing to post (advance rows handled below)
                    if cash_payment == 0 and payment_mode != 'advance':
                        continue

                    # Get loan details
                    c.execute("""
                        SELECT lr.loanid, l.member_code,
                               lr.principaldueamount, lr.interestdueamount,
                               lr.savingsdueamount
                        FROM LoanRec lr
                        JOIN Loans l ON lr.loanid = l.loanid
                        WHERE lr.loanrecid = ?
                    """, (loanrecid,))
                    rec = c.fetchone()
                    if not rec:
                        continue

                    loanid = rec[0]
                    member_code = rec[1]
                    p_due = float(rec[2] or 0)
                    i_due = float(rec[3] or 0)
                    s_due = float(rec[4] or 0)
                    
                    total_due = Decimal(str(p_due)) + Decimal(str(i_due)) + Decimal(str(s_due))
                    
                    # Apply advance if payment mode is 'advance'
                    advance_applied = Decimal('0')
                    
                    if payment_mode == 'advance' and ADVANCE_ENABLED:
                        advance_applied, new_balance = _apply_advance_manually(
                            c, member_code, loanid, loanrecid, total_due, user_id
                        )
                        
                        if advance_applied > 0:
                            # Reset form values — advance fills them from DB due amounts
                            principal = Decimal('0')
                            interest  = Decimal('0')
                            savings   = Decimal('0')
                            remaining = advance_applied
                            
                            # Priority: Interest → Principal → Savings
                            if i_due > 0 and remaining > 0:
                                to_interest = min(remaining, Decimal(str(i_due)))
                                interest += to_interest
                                remaining -= to_interest
                            
                            if p_due > 0 and remaining > 0:
                                to_principal = min(remaining, Decimal(str(p_due)))
                                principal += to_principal
                                remaining -= to_principal
                            
                            if s_due > 0 and remaining > 0:
                                to_savings = min(remaining, Decimal(str(s_due)))
                                savings += to_savings
                                remaining -= to_savings
                            
                            # Recalculate cash_payment to reflect advance amounts
                            cash_payment = principal + interest + savings + additional_sav
                            total_advance_used += advance_applied
                        else:
                            # Advance balance is 0 — skip silently
                            flash(f"No advance balance available for member. Skipped.", "warning")
                            continue

                    is_fully_paid = (float(principal) >= p_due and float(interest) >= i_due)

                    # Update LoanRec
                    c.execute("""
                        UPDATE LoanRec
                        SET principalpaidamount = principalpaidamount + ?,
                            interestpaidamount = interestpaidamount + ?,
                            savingspaidamount = savingspaidamount + ?,
                            paid = ?,
                            recordversion = recordversion + 1,
                            modifiedby = ?,
                            modifieddate = GETDATE()
                        WHERE loanrecid = ?
                    """, (
                        float(principal), float(interest), float(savings),
                        1 if is_fully_paid else 0,
                        user_id, loanrecid
                    ))

                    # Update Loans outstanding
                    c.execute("""
                        UPDATE Loans
                        SET principaloutstanding = principaloutstanding - ?,
                            interestoutstanding = CASE
                                WHEN interestoutstanding - ? < 0 THEN 0
                                ELSE interestoutstanding - ? END,
                            modifiedby = ?,
                            modifieddate = GETDATE()
                        WHERE loanid = ?
                    """, (
                        float(principal), float(interest), float(interest),
                        user_id, loanid
                    ))

                    _close_loan_if_done(c, loanid, user_id)

                    # Post savings
                    if savings > 0:
                        c.execute("""
                            INSERT INTO Savings (
                                member_code, loanrecid, amount, credit_debit, savingtype,
                                createdby, createddate, transactiondate, loanid,
                                Branchid, interestcalculated
                            ) VALUES (?, ?, ?, 'Credit', 'RegularSavings',
                                      ?, GETDATE(), GETDATE(), ?, ?, 0)
                        """, (member_code, loanrecid, float(savings), staff, loanid, branchid))

                    if additional_sav > 0:
                        c.execute("""
                            INSERT INTO Savings (
                                member_code, loanrecid, amount, credit_debit, savingtype,
                                createdby, createddate, transactiondate, loanid,
                                Branchid, interestcalculated
                            ) VALUES (?, ?, ?, 'Credit', 'AdditionalSavings',
                                      ?, GETDATE(), GETDATE(), ?, ?, 0)
                        """, (member_code, loanrecid, float(additional_sav), staff, loanid, branchid))

                    posted_count += 1
                    total_collected += cash_payment

                conn.commit()
                
                msg = f"✅ Recovery posted! {posted_count} EMI(s) | Cash: ₹{float(total_collected):,.2f}"
                
                if total_advance_used > 0:
                    msg += f" | Advance: ₹{float(total_advance_used):,.2f}"
                
                flash(msg, "success")
                return redirect(url_for("loanrec.recovery_posting", center_id=selected_center))

            except Exception as e:
                conn.rollback()
                print(f"❌ Error: {str(e)}")
                import traceback
                traceback.print_exc()
                flash(f"Error: {str(e)}", "danger")
                return redirect(url_for("loanrec.recovery_posting", center_id=selected_center))

    except Exception as e:
        print(f"❌ Page error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error: {str(e)}", "danger")
        members = []
        centers = []
        selected_center = None
        center_info = None
        advance_balances = {}

    finally:
        conn.close()

    return render_template("loanrec_main.html",
                           centers=centers,
                           members=members,
                           selected_center=selected_center,
                           center_info=center_info,
                           today=datetime.now().strftime('%d %b %Y'),
                           advance_balances=advance_balances,
                           advance_enabled=ADVANCE_ENABLED)


# ═══════════════════════════════════════════════════════════════
# PREPAID LOAN CLOSURE WITH PREPAIDTYPE CALCULATION
# ═══════════════════════════════════════════════════════════════
@loanrec_bp.route("/prepaid", methods=["GET", "POST"])
def prepaid_posting():
    """Prepaid/early closure with PrepaidType-based calculation."""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        branchid = session.get("branchid", 1)
        user_id = session.get("user_id", 1)

        # Get active prepaid types
        c.execute("""
            SELECT prepaidtypeid, prepaidtypename,
                   ISNULL(haspreclosurecharges, 0) AS haspreclosurecharges,
                   ISNULL(preclosurechargespercent, 0) AS chargespercent,
                   ISNULL(fullinterest, 0) AS fullinterest,
                   ISNULL(fullsavings, 0) AS fullsavings
            FROM PrepaidType
            WHERE active = 1
            ORDER BY prepaidtypename
        """)
        prepaid_types = c.fetchall()

        c.execute("""
            SELECT id, center_name, center_no
            FROM Center WHERE branchid=? ORDER BY center_name
        """, (branchid,))
        centers = c.fetchall()

        selected_center = request.args.get("center_id")
        active_loans = []

        if selected_center:
            c.execute("""
                SELECT
                    l.loanid,                       -- [0]
                    l.member_code,                  -- [1]
                    m.full_name,                    -- [2]
                    l.loanamount,                   -- [3]
                    ISNULL(l.principaloutstanding, 0), -- [4]
                    ISNULL(l.interestoutstanding, 0),  -- [5]
                    l.disbursementdate,             -- [6]
                    l.tenure,                       -- [7]
                    ISNULL(LP.ProductName,'N/A'),   -- [8]
                    ISNULL(l.emi, 0),               -- [9]
                    ISNULL(l.savingsdueamount, 0)   -- [10]
                FROM Loans   l
                JOIN Members m ON l.member_code = m.member_code
                LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
                WHERE m.center_id   = ?
                  AND l.loanstatus  = 'Active'
                  AND l.principaloutstanding > 0
                ORDER BY m.full_name
            """, (selected_center,))
            active_loans = c.fetchall()

        # ── POST: Process prepayment ──────────────────────────────────────
        if request.method == "POST":
            try:
                loanid = request.form.get("loanid")
                prepaid_type_id = request.form.get("prepaid_type")

                if not loanid or not prepaid_type_id:
                    flash("Please select both loan and prepaid type.", "warning")
                    return redirect(url_for("loanrec.prepaid_posting",
                                            center_id=selected_center))

                # Get loan details
                c.execute("""
                    SELECT member_code, 
                           ISNULL(principaloutstanding, 0),
                           ISNULL(interestoutstanding, 0),
                           ISNULL(savingsdueamount, 0),
                           ISNULL(usedsavingsonprepaid, 0),
                           ISNULL(usedaddlsavingsonprepaid, 0),
                           loanamount
                    FROM Loans WHERE loanid = ?
                """, (loanid,))
                loan = c.fetchone()

                if not loan:
                    flash("Loan not found.", "danger")
                    return redirect(url_for("loanrec.prepaid_posting"))

                member_code = loan[0]
                principal_outstanding = float(loan[1])
                interest_outstanding = float(loan[2])
                savings_due = float(loan[3])
                loan_amount = float(loan[6])

                # Get prepaid type configuration
                c.execute("""
                    SELECT prepaidtypename, haspreclosurecharges, 
                           ISNULL(preclosurechargespercent, 0),
                           ISNULL(fullinterest, 0),
                           ISNULL(fullsavings, 0)
                    FROM PrepaidType
                    WHERE prepaidtypeid = ?
                """, (prepaid_type_id,))
                ptype = c.fetchone()

                if not ptype:
                    flash("Invalid prepaid type.", "danger")
                    return redirect(url_for("loanrec.prepaid_posting"))

                prepaid_type_name = ptype[0]
                has_charges = bool(ptype[1])
                charges_percent = float(ptype[2])
                full_interest = bool(ptype[3])
                full_savings = bool(ptype[4])

                # ──────────────────────────────────────────────────────────
                # CALCULATE PREPAID AMOUNT BASED ON TYPE
                # ──────────────────────────────────────────────────────────

                prepaid_amount = principal_outstanding  # Always collect principal

                # Add interest if fullinterest=True
                if full_interest:
                    prepaid_amount += interest_outstanding

                # Add savings if fullsavings=True
                if full_savings:
                    prepaid_amount += savings_due

                # Calculate preclosure charges if applicable
                preclosure_charges = 0.0
                if has_charges and charges_percent > 0:
                    # Charges on principal outstanding
                    preclosure_charges = principal_outstanding * (charges_percent / 100)
                    prepaid_amount += preclosure_charges

                # Round to 2 decimal places
                prepaid_amount = round(prepaid_amount, 2)
                preclosure_charges = round(preclosure_charges, 2)

                # ──────────────────────────────────────────────────────────
                # UPDATE LOANS TABLE
                # ──────────────────────────────────────────────────────────
                c.execute("""
                    UPDATE Loans
                    SET principaloutstanding = 0,
                        interestoutstanding  = 0,
                        loanstatus           = 'Closed',
                        prepaidamount        = ?,
                        preclosurecharges    = ?,
                        prepaidfullsavings   = ?,
                        modifiedby           = ?,
                        modifieddate         = GETDATE()
                    WHERE loanid = ?
                """, (prepaid_amount, preclosure_charges, (1 if full_savings else 0),
                      user_id, loanid))

                # ──────────────────────────────────────────────────────────
                # MARK ALL UNPAID LOANREC AS PAID
                # Based on prepaid type:
                # - Death: Only principal paid (fullinterest=0)
                # - Prepaid/SpecialPrepaid: All amounts paid (fullinterest=1)
                # ──────────────────────────────────────────────────────────
                if full_interest:
                    # Mark all dues as fully paid
                    c.execute("""
                        UPDATE LoanRec
                        SET paid                = 1,
                            principalpaidamount = principaldueamount,
                            interestpaidamount  = interestdueamount,
                            savingspaidamount   = savingsdueamount,
                            recordversion       = recordversion + 1,
                            modifiedby          = ?,
                            modifieddate        = GETDATE()
                        WHERE loanid = ? AND paid = 0
                    """, (user_id, loanid))
                else:
                    # Death case: Only principal paid, interest waived
                    c.execute("""
                        UPDATE LoanRec
                        SET paid                = 1,
                            principalpaidamount = principaldueamount,
                            interestpaidamount  = 0,
                            savingspaidamount   = 0,
                            recordversion       = recordversion + 1,
                            modifiedby          = ?,
                            modifieddate        = GETDATE()
                        WHERE loanid = ? AND paid = 0
                    """, (user_id, loanid))

                conn.commit()

                flash(
                    f"✅ Loan #{loanid} closed ({prepaid_type_name}). "
                    f"Prepaid: ₹{prepaid_amount:,.2f} | "
                    f"Charges: ₹{preclosure_charges:,.2f}",
                    "success"
                )
                return redirect(url_for("loanrec.prepaid_posting",
                                        center_id=selected_center))

            except Exception as e:
                conn.rollback()
                flash(f"Prepaid error: {str(e)}", "danger")
                import traceback;
                traceback.print_exc()
                return redirect(url_for("loanrec.prepaid_posting"))

    except Exception as e:
        flash(f"Page error: {str(e)}", "danger")
        prepaid_types = [];
        centers = [];
        active_loans = [];
        selected_center = None

    finally:
        conn.close()

    return render_template("loanrec_prepaid.html",
                           prepaid_types=prepaid_types,
                           centers=centers,
                           active_loans=active_loans,
                           selected_center=selected_center)


# ═══════════════════════════════════════════════════════════════
# ARREARS RECOVERY POSTING WITH ADMIN AUTHORIZATION
# Add this to loanrec.py after prepaid_posting() route
# ═══════════════════════════════════════════════════════════════

@loanrec_bp.route("/arrears", methods=["GET", "POST"])
def arrears_posting():
    """
    Arrears Recovery with Admin Authorization
    - First posting must be 0 with admin password
    - Password: SYSTEMDATE + BRANCHCODE + MEMBERNAME + MEMBERCODE
    - Recovery priority: Interest → Principal → Savings
    """
    conn = get_db_connection()
    c = conn.cursor()

    try:
        branchid = session.get("branchid", 1)
        user_id = session.get("user_id", 1)
        emp_name = session.get("emp_name", "Admin")

        # Get branch code
        c.execute("SELECT Code FROM Branches WHERE Id = ?", (branchid,))
        branch_row = c.fetchone()
        branch_code = branch_row[0] if branch_row else "BR01"

        # Get centers
        c.execute("""
            SELECT id, center_name, center_no
            FROM Center WHERE branchid=? ORDER BY center_name
        """, (branchid,))
        centers = c.fetchall()

        selected_center = request.args.get("center_id")
        arrears_members = []
        center_info = None

        if selected_center:
            c.execute("SELECT id, center_name, center_no FROM Center WHERE id=?", (selected_center,))
            center_info = c.fetchone()

            # Get arrears members: due date < last dayend date AND not paid
            c.execute("""
                SELECT 
                    m.member_code,                          -- [0]
                    m.full_name,                            -- [1]
                    l.loanid,                               -- [2]
                    lr.loanrecid,                           -- [3]
                    ISNULL(lr.emisequence, 0),              -- [4]
                    lr.duedate,                             -- [5]
                    lr.principaldueamount,                  -- [6]
                    lr.interestdueamount,                   -- [7]
                    lr.savingsdueamount,                    -- [8]
                    ISNULL(lr.principalpaidamount, 0),      -- [9]
                    ISNULL(lr.interestpaidamount, 0),       -- [10]
                    ISNULL(lr.savingspaidamount, 0),        -- [11]
                    ISNULL(lr.ArrearsFlag, 0),              -- [12]
                    ISNULL(lr.ZeroPostingDone, 0),          -- [13]
                    ISNULL(LP.ProductName, 'N/A'),          -- [14]
                    DATEDIFF(day, lr.duedate, 
                        (SELECT TOP 1 DayendDate FROM Dayend 
                         WHERE BranchId = ? ORDER BY DayendDate DESC)) AS days_overdue  -- [15]
                FROM Members m
                JOIN Loans l ON m.member_code = l.member_code
                JOIN LoanRec lr ON l.loanid = lr.loanid
                LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
                WHERE m.center_id = ?
                  AND lr.paid = 0
                  AND lr.emisequence > 0
                  AND lr.duedate < (SELECT TOP 1 DayendDate FROM Dayend 
                                    WHERE BranchId = ? ORDER BY DayendDate DESC)
                  AND l.loanstatus = 'Active'
                ORDER BY days_overdue DESC, m.full_name, lr.emisequence
            """, (branchid, selected_center, branchid))
            arrears_members = c.fetchall()

        # ═══════════════════════════════════════════════════════
        # POST: Process Arrears Recovery
        # ═══════════════════════════════════════════════════════
        if request.method == "POST":
            if not selected_center:
                flash("Please select a center first.", "warning")
                return redirect(url_for("loanrec.arrears_posting"))

            action = request.form.get("action")

            # ─────────────────────────────────────────────────────
            # ACTION: ZERO POSTING WITH ADMIN AUTHORIZATION
            # ─────────────────────────────────────────────────────
            if action == "zero_posting":
                loanrecid = request.form.get("loanrecid")
                member_code = request.form.get("member_code")
                member_name = request.form.get("member_name")
                entered_password = request.form.get("auth_password", "").upper()

                if not all([loanrecid, member_code, member_name, entered_password]):
                    flash("All fields are required for authorization", "danger")
                    return redirect(url_for("loanrec.arrears_posting", center_id=selected_center))

                # Generate password: SYSTEMDATE + BRANCHCODE + MEMBERNAME + MEMBERCODE
                system_date = datetime.now().strftime('%Y%m%d')
                generated_password = f"{system_date}{branch_code}{member_name.upper()}{member_code}".replace(" ", "")

                # Check password
                if entered_password != generated_password:
                    flash(f"❌ Invalid Authorization Password! Generated: {generated_password}", "danger")
                    return redirect(url_for("loanrec.arrears_posting", center_id=selected_center))

                try:
                    # Insert 0 posting record
                    c.execute("""
                        UPDATE LoanRec
                        SET principalpaidamount = 0,
                            interestpaidamount = 0,
                            savingspaidamount = 0,
                            ArrearsFlag = 1,
                            ZeroPostingDone = 1,
                            ArrearsAuthPassword = ?,
                            ArrearsAuthDate = GETDATE(),
                            ArrearsAuthorizedBy = ?,
                            PostingType = 'ARREARS_ZERO',
                            recordversion = recordversion + 1,
                            modifiedby = ?,
                            modifieddate = GETDATE()
                        WHERE loanrecid = ?
                    """, (generated_password, emp_name, user_id, loanrecid))

                    conn.commit()
                    flash(f"✅ Zero Posting Authorized! Member can now make payments.", "success")
                    return redirect(url_for("loanrec.arrears_posting", center_id=selected_center))

                except Exception as e:
                    conn.rollback()
                    flash(f"Error: {str(e)}", "danger")
                    return redirect(url_for("loanrec.arrears_posting", center_id=selected_center))

            # ─────────────────────────────────────────────────────
            # ACTION: ARREARS RECOVERY PAYMENT
            # Priority: Interest → Principal → Savings
            # ─────────────────────────────────────────────────────
            elif action == "recovery_payment":
                selected_arrears = request.form.getlist("selected_arrear")
                if not selected_arrears:
                    flash("No members selected.", "warning")
                    return redirect(url_for("loanrec.arrears_posting", center_id=selected_center))

                try:
                    posted_count = 0
                    total_collected = Decimal("0.00")

                    for lrec_id_str in selected_arrears:
                        lrec_id = int(lrec_id_str)

                        # Get recovery amount
                        recovery_amount = float(request.form.get(f"recovery_{lrec_id}", 0) or 0)

                        if recovery_amount <= 0:
                            continue

                        # Get current LoanRec record
                        c.execute("""
                            SELECT loanid, principaldueamount, interestdueamount, savingsdueamount,
                                   principalpaidamount, interestpaidamount, savingspaidamount,
                                   ZeroPostingDone
                            FROM LoanRec WHERE loanrecid = ?
                        """, (lrec_id,))
                        lr = c.fetchone()
                        if not lr:
                            continue

                        loanid = lr[0]
                        principal_due = float(lr[1] or 0)
                        interest_due = float(lr[2] or 0)
                        savings_due = float(lr[3] or 0)
                        principal_paid = float(lr[4] or 0)
                        interest_paid = float(lr[5] or 0)
                        savings_paid = float(lr[6] or 0)
                        zero_posting_done = lr[7]

                        # Check if zero posting was done
                        if not zero_posting_done:
                            flash(f"EMI #{lrec_id}: Zero posting not authorized yet!", "warning")
                            continue

                        # Calculate pending amounts
                        interest_pending = interest_due - interest_paid
                        principal_pending = principal_due - principal_paid
                        savings_pending = savings_due - savings_paid

                        # Allocate recovery with PRIORITY: Interest → Principal → Savings
                        remaining = recovery_amount
                        interest_allocation = 0
                        principal_allocation = 0
                        savings_allocation = 0

                        # 1st Priority: Interest
                        if remaining > 0 and interest_pending > 0:
                            interest_allocation = min(remaining, interest_pending)
                            remaining -= interest_allocation

                        # 2nd Priority: Principal
                        if remaining > 0 and principal_pending > 0:
                            principal_allocation = min(remaining, principal_pending)
                            remaining -= principal_allocation

                        # 3rd Priority: Savings
                        if remaining > 0 and savings_pending > 0:
                            savings_allocation = min(remaining, savings_pending)
                            remaining -= savings_allocation

                        # Update paid amounts
                        new_interest_paid = interest_paid + interest_allocation
                        new_principal_paid = principal_paid + principal_allocation
                        new_savings_paid = savings_paid + savings_allocation

                        # Check if fully paid
                        mark_paid = (new_interest_paid >= interest_due and
                                     new_principal_paid >= principal_due and
                                     new_savings_paid >= savings_due)

                        # Update LoanRec
                        c.execute("""
                            UPDATE LoanRec
                            SET principalpaidamount = ?,
                                interestpaidamount = ?,
                                savingspaidamount = ?,
                                paid = ?,
                                ArrearsFlag = CASE WHEN ? = 1 THEN 0 ELSE 1 END,
                                PostingType = CASE WHEN ? = 1 THEN 'REGULAR' ELSE 'ARREARS_RECOVERY' END,
                                recordversion = recordversion + 1,
                                modifiedby = ?,
                                modifieddate = GETDATE()
                            WHERE loanrecid = ?
                        """, (new_principal_paid, new_interest_paid, new_savings_paid,
                              (1 if mark_paid else 0), mark_paid, mark_paid, user_id, lrec_id))

                        # Update Loans outstanding
                        c.execute("""
                            UPDATE Loans
                            SET principaloutstanding = principaloutstanding - ?,
                                interestoutstanding = interestoutstanding - ?,
                                modifiedby = ?,
                                modifieddate = GETDATE()
                            WHERE loanid = ?
                        """, (principal_allocation, interest_allocation, user_id, loanid))

                        _close_loan_if_done(c, loanid, user_id)

                        posted_count += 1
                        total_collected += Decimal(str(recovery_amount))

                    conn.commit()
                    flash(f"✅ Arrears recovery posted! {posted_count} EMI(s) | Total: ₹{float(total_collected):,.2f}",
                          "success")
                    return redirect(url_for("loanrec.arrears_posting", center_id=selected_center))

                except Exception as e:
                    conn.rollback()
                    flash(f"Error: {str(e)}", "danger")
                    import traceback
                    traceback.print_exc()
                    return redirect(url_for("loanrec.arrears_posting", center_id=selected_center))

    except Exception as e:
        flash(f"Page error: {str(e)}", "danger")
        arrears_members = []
        centers = []
        selected_center = None
        center_info = None

    finally:
        conn.close()

    return render_template("loanrec_arrears.html",
                           centers=centers,
                           arrears_members=arrears_members,
                           selected_center=selected_center,
                           center_info=center_info,
                           branch_code=branch_code,
                           today=datetime.now().strftime('%d %b %Y'))

