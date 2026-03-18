# loanrec.py - Loan Recovery with PrepaidType Integration + ADVANCE RECOVERY + UNDO
# ═══════════════════════════════════════════════════════════════════════════
# FEATURES:
# 1. Regular Recovery with Advance Integration (Payment Mode Dropdown)
# 2. Prepaid/Closure with PrepaidType calculations
# 3. Arrears Recovery with Admin authorization
# 4. Undo Recovery (Admin/Manager only, After DayEnd only)
# ═══════════════════════════════════════════════════════════════════════════
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

# ═══════════════════════════════════════════════════════════════════════════
# IMPORT ADVANCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════
try:
    from advance import get_advance_balance
    ADVANCE_ENABLED = True
except ImportError:
    ADVANCE_ENABLED = False
    print("WARNING: Advance module not found. Advance integration disabled.")

loanrec_bp = Blueprint("loanrec", __name__, template_folder="templates")


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _close_loan_if_done(cursor, loanid, user_id):
    """
    Close loan automatically when principal and interest are zero.
    """
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
    Manually apply advance to LoanRec EMI when payment_mode = 'advance'.
    
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
            f"Auto-applied via recovery posting to LoanRec #{loanrecid}",
            user_id
        ))
        
        new_balance = get_advance_balance(member_code, loanid)
        return (amount_to_apply, new_balance)
        
    except Exception as e:
        print(f"Error applying advance: {str(e)}")
        return (Decimal('0'), Decimal('0'))


def _can_undo_recovery(cursor, loanrecid, role):
    """
    Check if recovery can be undone.
    
    RULES:
    1. Only Admin or Manager can undo
    2. Can only undo if recovery date is AFTER latest DayEnd date
    
    Returns: (can_undo, message)
    """
    # Check role
    if role not in ['Admin', 'Manager']:
        return (False, "Only Admin and Manager can undo recovery")
    
    # Get recovery date
    cursor.execute("""
        SELECT modifieddate, duedate
        FROM LoanRec
        WHERE loanrecid = ?
    """, (loanrecid,))
    
    rec = cursor.fetchone()
    if not rec:
        return (False, "LoanRec not found")
    
    recovery_date = rec[0] or rec[1]
    
    if not recovery_date:
        return (False, "No recovery date found")
    
    # Get latest DayEnd date
    cursor.execute("""
        SELECT TOP 1 dayenddate
        FROM DayEnd
        ORDER BY dayenddate DESC
    """)
    
    dayend = cursor.fetchone()
    
    if dayend and dayend[0]:
        dayend_date = dayend[0]
        
        # Can only undo if recovery is AFTER dayend
        if recovery_date <= dayend_date:
            return (False, f"Cannot undo: Recovery is before/on DayEnd date ({dayend_date.strftime('%d %b %Y')}). Only records after this date can be undone.")
    
    return (True, "Can undo")


# ═══════════════════════════════════════════════════════════════════════════
# REGULAR RECOVERY POSTING (WITH ADVANCE INTEGRATION)
# ═══════════════════════════════════════════════════════════════════════════
@loanrec_bp.route("/", methods=["GET", "POST"])
def recovery_posting():
    """Center-wise regular loan recovery posting with ADVANCE PAYMENT MODE DROPDOWN."""
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

        selected_center = request.args.get("center_id")
        members = []
        center_info = None
        
        # ═══════════════════════════════════════════════════════════════
        # ADVANCE BALANCES DICTIONARY
        # ═══════════════════════════════════════════════════════════════
        advance_balances = {}  # {member_code: {loanid: balance}}

        if selected_center:
            c.execute("""
                SELECT id, center_name, center_no
                FROM Center WHERE id=?
            """, (selected_center,))
            center_info = c.fetchone()

            # Pending EMIs
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
                    ISNULL(lr.additionalsavingsdueamount, 0), -- [12]
                    ISNULL(lr.additionalsavingspaidamount, 0), -- [13]
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
            
            # ═══════════════════════════════════════════════════════════════
            # GET ADVANCE BALANCES FOR ALL MEMBERS
            # ═══════════════════════════════════════════════════════════════
            if ADVANCE_ENABLED and members:
                for m in members:
                    member_code = m[0]
                    loanid = m[2]
                    
                    if member_code not in advance_balances:
                        advance_balances[member_code] = {}
                    
                    if loanid not in advance_balances[member_code]:
                        balance = get_advance_balance(member_code, loanid)
                        advance_balances[member_code][loanid] = float(balance)

        # ── POST: Process recovery ────────────────────────────────────────
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
                    
                    # ═══════════════════════════════════════════════════════════
                    # GET PAYMENT MODE (cash or advance)
                    # ═══════════════════════════════════════════════════════════
                    payment_mode = request.form.get(f"payment_mode_{loanrecid}", "cash")
                    
                    cash_payment = principal + interest + savings + additional_sav

                    if cash_payment == 0 and payment_mode != 'advance':
                        continue

                    # Get loanrec details
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
                    
                    # ═══════════════════════════════════════════════════════════
                    # HANDLE ADVANCE PAYMENT MODE
                    # ═══════════════════════════════════════════════════════════
                    advance_applied = Decimal('0')
                    
                    if payment_mode == 'advance' and ADVANCE_ENABLED:
                        # Member selected advance payment
                        # Apply advance to cover the EMI
                        advance_applied, new_balance = _apply_advance_manually(
                            c, member_code, loanid, loanrecid, total_due, user_id
                        )
                        
                        if advance_applied > 0:
                            # Allocate advance to principal/interest/savings
                            remaining_advance = advance_applied
                            
                            # Priority: Interest → Principal → Savings
                            advance_to_interest = min(remaining_advance, Decimal(str(i_due)))
                            if advance_to_interest > 0:
                                interest += advance_to_interest
                                remaining_advance -= advance_to_interest
                            
                            advance_to_principal = min(remaining_advance, Decimal(str(p_due)))
                            if advance_to_principal > 0:
                                principal += advance_to_principal
                                remaining_advance -= advance_to_principal
                            
                            advance_to_savings = min(remaining_advance, Decimal(str(s_due)))
                            if advance_to_savings > 0:
                                savings += advance_to_savings
                                remaining_advance -= advance_to_savings
                            
                            total_advance_used += advance_applied

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

                    # Auto-close loan if fully paid
                    _close_loan_if_done(c, loanid, user_id)

                    # Post savings transaction
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
                
                # ═══════════════════════════════════════════════════════════
                # SUCCESS MESSAGE WITH ADVANCE INFO
                # ═══════════════════════════════════════════════════════════
                msg = f"✅ Recovery posted! {posted_count} EMI(s) | Cash: ₹{float(total_collected):,.2f}"
                
                if total_advance_used > 0:
                    msg += f" | Advance: ₹{float(total_advance_used):,.2f}"
                
                flash(msg, "success")
                return redirect(url_for("loanrec.recovery_posting", center_id=selected_center))

            except Exception as e:
                conn.rollback()
                flash(f"Error posting recovery: {str(e)}", "danger")
                import traceback
                traceback.print_exc()
                return redirect(url_for("loanrec.recovery_posting", center_id=selected_center))

    except Exception as e:
        flash(f"Page error: {str(e)}", "danger")
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


# ═══════════════════════════════════════════════════════════════════════════
# UNDO RECOVERY (Admin/Manager only, After DayEnd only)
# ═══════════════════════════════════════════════════════════════════════════
@loanrec_bp.route("/undo/<int:loanrecid>", methods=["POST"])
def undo_recovery(loanrecid):
    """
    Undo a recovery posting.
    
    RESTRICTIONS:
    1. Only Admin or Manager can undo
    2. Can only undo if recovery date is AFTER latest DayEnd date
    """
    try:
        role = session.get("role", "")
        user_id = session.get("user_id", 1)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check permissions
        can_undo, msg = _can_undo_recovery(cursor, loanrecid, role)
        
        if not can_undo:
            flash(f"❌ {msg}", "danger")
            conn.close()
            return redirect(request.referrer or url_for("loanrec.recovery_posting"))
        
        # Get LoanRec details before undoing
        cursor.execute("""
            SELECT 
                lr.loanid,
                l.member_code,
                lr.principalpaidamount,
                lr.interestpaidamount,
                lr.savingspaidamount,
                lr.advancerecovery,
                lr.emisequence,
                m.full_name
            FROM LoanRec lr
            JOIN Loans l ON lr.loanid = l.loanid
            JOIN Members m ON l.member_code = m.member_code
            WHERE lr.loanrecid = ?
        """, (loanrecid,))
        
        rec = cursor.fetchone()
        
        if not rec:
            flash("LoanRec not found", "danger")
            conn.close()
            return redirect(request.referrer or url_for("loanrec.recovery_posting"))
        
        loanid = rec[0]
        member_code = rec[1]
        principal_paid = float(rec[2] or 0)
        interest_paid = float(rec[3] or 0)
        savings_paid = float(rec[4] or 0)
        advance_used = float(rec[5] or 0)
        emisequence = rec[6]
        member_name = rec[7]
        
        # Reverse LoanRec payment
        cursor.execute("""
            UPDATE LoanRec
            SET principalpaidamount = 0,
                interestpaidamount = 0,
                savingspaidamount = 0,
                advancerecovery = 0,
                paid = 0,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanrecid = ?
        """, (user_id, loanrecid))
        
        # Reverse Loans outstanding
        cursor.execute("""
            UPDATE Loans
            SET principaloutstanding = principaloutstanding + ?,
                interestoutstanding = interestoutstanding + ?,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanid = ?
        """, (principal_paid, interest_paid, user_id, loanid))
        
        # Reverse advance if used
        if advance_used > 0 and ADVANCE_ENABLED:
            # Insert Credit entry to restore balance
            cursor.execute("""
                INSERT INTO AdvanceRecovery (
                    member_code, loanid, amount, creditdebit, notes,
                    createdby, createddate, transactiondate
                )
                VALUES (?, ?, ?, 'Credit', ?, ?, GETDATE(), GETDATE())
            """, (
                member_code, loanid, advance_used,
                f"Undo recovery for LoanRec #{loanrecid} - EMI #{emisequence}",
                user_id
            ))
        
        # Delete Savings transactions (only after DayEnd)
        cursor.execute("""
            DELETE FROM Savings
            WHERE loanrecid = ?
        """, (loanrecid,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(
            f"✅ Recovery undone successfully! | "
            f"Member: {member_name} | EMI #{emisequence} | "
            f"Principal: ₹{principal_paid:,.2f} | Interest: ₹{interest_paid:,.2f}" +
            (f" | Advance Restored: ₹{advance_used:,.2f}" if advance_used > 0 else ""),
            "success"
        )
        
        return redirect(request.referrer or url_for("loanrec.recovery_posting"))
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        flash(f"Error undoing recovery: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return redirect(request.referrer or url_for("loanrec.recovery_posting"))


# NOTE: Continue with prepaid_posting and arrears_posting functions below
# (Keep your existing prepaid and arrears functions as they are)
