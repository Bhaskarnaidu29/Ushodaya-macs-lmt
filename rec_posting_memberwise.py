# rec_posting_memberwise.py - Complete Member-wise Recovery System
# Regular, Prepaid, Arrears with tabs

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

rec_member_bp = Blueprint("rec_member", __name__, template_folder="templates")


def _close_loan_if_done(cursor, loanid, user_id):
    """Auto-close loan when principal outstanding reaches zero."""
    cursor.execute("SELECT principaloutstanding FROM Loans WHERE loanid = ?", (loanid,))
    row = cursor.fetchone()
    if row and float(row[0] or 0) <= 0.01:
        cursor.execute("""
            UPDATE Loans
            SET loanstatus = 'Closed',
                principaloutstanding = 0,
                modifiedby = ?,
                modifieddate = GETDATE()
            WHERE loanid = ?
        """, (user_id, loanid))


# ═══════════════════════════════════════════════════════════════
# REGULAR RECOVERY - MEMBER-WISE
# ═══════════════════════════════════════════════════════════════
@rec_member_bp.route("/", methods=["GET", "POST"])
def member_recovery():
    """Member-wise regular recovery posting."""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        branchid = session.get("branchid", 1)
        user_id = session.get("user_id", 1)

        # Get all active members
        c.execute("""
            SELECT member_code, full_name, center_id
            FROM Members 
            WHERE BranchId = ? AND status = 'ACTIVE'
            ORDER BY full_name
        """, (branchid,))
        members = c.fetchall()

        selected_member = request.args.get("member_code") or request.form.get("member_code")
        member_info = None
        pending_emis = []

        if selected_member:
            # Get member details
            c.execute("""
                SELECT m.member_code, m.full_name, c.center_name
                FROM Members m
                LEFT JOIN Center c ON m.center_id = c.id
                WHERE m.member_code = ?
            """, (selected_member,))
            member_info = c.fetchone()

            # Get pending EMIs (non-arrears only)
            c.execute("""
                SELECT 
                    l.loanid,
                    lr.loanrecid,
                    ISNULL(lr.emisequence, 0) AS emisequence,
                    lr.duedate,
                    lr.principaldueamount,
                    lr.interestdueamount,
                    lr.savingsdueamount,
                    ISNULL(lr.principalpaidamount, 0),
                    ISNULL(lr.interestpaidamount, 0),
                    ISNULL(lr.savingspaidamount, 0),
                    ISNULL(lr.additionalsavingsdueamount, 0),
                    ISNULL(LP.ProductName, 'N/A')
                FROM Loans l
                JOIN LoanRec lr ON l.loanid = lr.loanid
                LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
                WHERE l.member_code = ?
                  AND lr.paid = 0
                  AND lr.emisequence > 0
                  AND lr.duedate <= GETDATE()
                  AND l.loanstatus = 'Active'
                  AND ISNULL(lr.advancerecovery, 1) = 1
                ORDER BY lr.emisequence
            """, (selected_member,))
            pending_emis = c.fetchall()

        # POST: Save recovery
        if request.method == "POST" and request.form.get("action") == "save":
            if not selected_member:
                flash("Please select a member first.", "warning")
                return redirect(url_for("rec_member.member_recovery"))

            selected_loanrecs = request.form.getlist("selected_loanrec")
            if not selected_loanrecs:
                flash("No EMIs selected.", "warning")
                return redirect(url_for("rec_member.member_recovery", member_code=selected_member))

            try:
                posted_count = 0
                total_collected = Decimal("0.00")

                for lrec_id_str in selected_loanrecs:
                    lrec_id = int(lrec_id_str)
                    principal_paid = float(request.form.get(f"p_{lrec_id}", 0) or 0)
                    interest_paid = float(request.form.get(f"i_{lrec_id}", 0) or 0)
                    savings_paid = float(request.form.get(f"s_{lrec_id}", 0) or 0)
                    addl_sav_paid = float(request.form.get(f"as_{lrec_id}", 0) or 0)
                    advance_recov = float(request.form.get(f"adv_{lrec_id}", 0) or 0)
                    payment_mode = request.form.get(f"mode_{lrec_id}", "Cash")

                    total_paid = principal_paid + interest_paid + savings_paid + addl_sav_paid

                    c.execute("""
                        SELECT loanid, principaldueamount, interestdueamount,
                               savingsdueamount, paid
                        FROM LoanRec WHERE loanrecid = ?
                    """, (lrec_id,))
                    lr = c.fetchone()
                    if not lr or lr[4]:
                        continue

                    loanid = lr[0]
                    principal_due = float(lr[1] or 0)
                    interest_due = float(lr[2] or 0)
                    savings_due = float(lr[3] or 0)

                    mark_paid = (principal_paid >= principal_due and 
                                interest_paid >= interest_due and 
                                savings_paid >= savings_due)

                    # Update LoanRec
                    c.execute("""
                        UPDATE LoanRec
                        SET principalpaidamount = ?, 
                            interestpaidamount = ?,
                            savingspaidamount = ?, 
                            additionalsavingspaidamount = ?,
                            advancerecovery = ?, 
                            paid = ?,
                            recoverydate = GETDATE(),
                            paymentmode = ?,
                            recordversion = recordversion + 1,
                            modifiedby = ?, 
                            modifieddate = GETDATE()
                        WHERE loanrecid = ?
                    """, (principal_paid, interest_paid, savings_paid, addl_sav_paid,
                          advance_recov, (1 if mark_paid else 0), payment_mode,
                          user_id, lrec_id))

                    # Update Loans outstanding
                    c.execute("""
                        UPDATE Loans
                        SET principaloutstanding = principaloutstanding - ?,
                            interestoutstanding = interestoutstanding - ?,
                            modifiedby = ?, 
                            modifieddate = GETDATE()
                        WHERE loanid = ?
                    """, (principal_paid, interest_paid, user_id, loanid))

                    # Insert savings records
                    if savings_paid > 0:
                        c.execute("""
                            INSERT INTO savings (member_code, loanrecid, amount, credit_debit, 
                                               savingtype, createdby, createddate, modifiedby, 
                                               modifieddate, transactiondate, loanid, paymentid, Branchid)
                            VALUES (?, ?, ?, 'Credit', 'GENERAL', ?, GETDATE(), ?, 
                                   GETDATE(), GETDATE(), ?, ?, ?)
                        """, (selected_member, lrec_id, savings_paid, user_id, user_id, 
                             loanid, payment_mode, branchid))

                    if addl_sav_paid > 0:
                        c.execute("""
                            INSERT INTO savings (member_code, loanrecid, amount, credit_debit, 
                                               savingtype, createdby, createddate, modifiedby, 
                                               modifieddate, transactiondate, loanid, paymentid, Branchid)
                            VALUES (?, ?, ?, 'Credit', 'ADDITIONAL', ?, GETDATE(), ?, 
                                   GETDATE(), GETDATE(), ?, ?, ?)
                        """, (selected_member, lrec_id, addl_sav_paid, user_id, user_id, 
                             loanid, payment_mode, branchid))

                    _close_loan_if_done(c, loanid, user_id)

                    posted_count += 1
                    total_collected += Decimal(str(total_paid))

                conn.commit()
                flash(f"✅ Recovery posted! {posted_count} EMI(s) | Total: ₹{float(total_collected):,.2f}", "success")
                return redirect(url_for("rec_member.member_recovery", member_code=selected_member))

            except Exception as e:
                conn.rollback()
                flash(f"Error: {str(e)}", "danger")
                import traceback
                traceback.print_exc()
                return redirect(url_for("rec_member.member_recovery", member_code=selected_member))

    except Exception as e:
        flash(f"Page error: {str(e)}", "danger")
        members = []
        selected_member = None
        member_info = None
        pending_emis = []

    finally:
        conn.close()

    return render_template("rec_member_main.html",
                          members=members,
                          selected_member=selected_member,
                          member_info=member_info,
                          pending_emis=pending_emis,
                          today=datetime.now().strftime('%d %b %Y'))


# ═══════════════════════════════════════════════════════════════
# PREPAID CLOSURE - MEMBER-WISE
# ═══════════════════════════════════════════════════════════════
@rec_member_bp.route("/prepaid", methods=["GET", "POST"])
def member_prepaid():
    """Member-wise prepaid/early closure."""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        branchid = session.get("branchid", 1)
        user_id = session.get("user_id", 1)

        # Get all active members
        c.execute("""
            SELECT member_code, full_name
            FROM Members 
            WHERE BranchId = ? AND status = 'ACTIVE'
            ORDER BY full_name
        """, (branchid,))
        members = c.fetchall()

        # Get prepaid types
        c.execute("""
            SELECT prepaidtypeid, prepaidtypename, haspreclosurecharges,
                   preclosurechargespercent, fullinterest, fullsavings
            FROM PrepaidType
            WHERE active = 1
        """)
        prepaid_types = c.fetchall()

        selected_member = request.args.get("member_code") or request.form.get("member_code")
        member_info = None
        active_loans = []

        if selected_member:
            # Get member details
            c.execute("""
                SELECT m.member_code, m.full_name, c.center_name
                FROM Members m
                LEFT JOIN Center c ON m.center_id = c.id
                WHERE m.member_code = ?
            """, (selected_member,))
            member_info = c.fetchone()

            # Get active loans
            c.execute("""
                SELECT 
                    l.loanid,
                    l.member_code,
                    m.full_name,
                    l.loanAmountApproved,
                    l.principaloutstanding,
                    l.interestoutstanding,
                    l.disbursementdate,
                    l.emiamount,
                    ISNULL(LP.ProductName, 'N/A'),
                    l.savingsamount
                FROM Loans l
                JOIN Members m ON l.member_code = m.member_code
                LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
                WHERE l.member_code = ?
                  AND l.loanstatus = 'Active'
                  AND l.principaloutstanding > 0
                ORDER BY l.disbursementdate DESC
            """, (selected_member,))
            active_loans = c.fetchall()

        # POST: Process prepaid
        if request.method == "POST":
            loanid = request.form.get("loanid")
            prepaid_type = request.form.get("prepaid_type")
            prepaid_amount = float(request.form.get("prepaid_amount", 0) or 0)
            preclosure_charges = float(request.form.get("preclosure_charges", 0) or 0)

            if not all([loanid, prepaid_type, prepaid_amount]):
                flash("All fields are required.", "warning")
                return redirect(url_for("rec_member.member_prepaid", member_code=selected_member))

            try:
                # Get loan details
                c.execute("""
                    SELECT member_code, principaloutstanding, interestoutstanding, savingsamount
                    FROM Loans WHERE loanid = ?
                """, (loanid,))
                loan = c.fetchone()

                if not loan:
                    flash("Loan not found.", "danger")
                    return redirect(url_for("rec_member.member_prepaid", member_code=selected_member))

                # Get prepaid type config
                c.execute("""
                    SELECT fullinterest, fullsavings
                    FROM PrepaidType WHERE prepaidtypeid = ?
                """, (prepaid_type,))
                pt_config = c.fetchone()

                full_interest = pt_config[0] if pt_config else 1
                full_savings = pt_config[1] if pt_config else 1

                # Update LoanRec - mark all unpaid as paid
                c.execute("""
                    UPDATE LoanRec
                    SET principalpaidamount = principaldueamount,
                        interestpaidamount = CASE WHEN ? = 1 THEN interestdueamount ELSE 0 END,
                        savingspaidamount = CASE WHEN ? = 1 THEN savingsdueamount ELSE 0 END,
                        paid = 1,
                        recoverydate = GETDATE(),
                        paymentmode = 'Prepaid',
                        modifiedby = ?,
                        modifieddate = GETDATE()
                    WHERE loanid = ? AND paid = 0
                """, (full_interest, full_savings, user_id, loanid))

                # Update Loans
                c.execute("""
                    UPDATE Loans
                    SET loanstatus = 'Closed',
                        principaloutstanding = 0,
                        interestoutstanding = 0,
                        prepaidamount = ?,
                        preclosurecharges = ?,
                        prepaidfullsavings = ?,
                        modifiedby = ?,
                        modifieddate = GETDATE()
                    WHERE loanid = ?
                """, (prepaid_amount, preclosure_charges, full_savings, user_id, loanid))

                conn.commit()
                flash(f"✅ Loan closed! Prepaid amount: ₹{prepaid_amount:,.2f}", "success")
                return redirect(url_for("rec_member.member_prepaid", member_code=selected_member))

            except Exception as e:
                conn.rollback()
                flash(f"Error: {str(e)}", "danger")
                return redirect(url_for("rec_member.member_prepaid", member_code=selected_member))

    except Exception as e:
        flash(f"Page error: {str(e)}", "danger")
        members = []
        prepaid_types = []
        selected_member = None
        member_info = None
        active_loans = []

    finally:
        conn.close()

    return render_template("rec_member_prepaid.html",
                          members=members,
                          prepaid_types=prepaid_types,
                          selected_member=selected_member,
                          member_info=member_info,
                          active_loans=active_loans)


# ═══════════════════════════════════════════════════════════════
# ARREARS RECOVERY - MEMBER-WISE (Interest-First Priority)
# ═══════════════════════════════════════════════════════════════
@rec_member_bp.route("/arrears", methods=["GET", "POST"])
def member_arrears():
    """Member-wise arrears recovery with interest-first priority."""
    conn = get_db_connection()
    c = conn.cursor()

    try:
        branchid = session.get("branchid", 1)
        user_id = session.get("user_id", 1)

        # Get all active members
        c.execute("""
            SELECT member_code, full_name
            FROM Members 
            WHERE BranchId = ? AND status = 'ACTIVE'
            ORDER BY full_name
        """, (branchid,))
        members = c.fetchall()

        selected_member = request.args.get("member_code") or request.form.get("member_code")
        member_info = None
        arrears_emis = []

        if selected_member:
            # Get member details
            c.execute("""
                SELECT m.member_code, m.full_name, c.center_name
                FROM Members m
                LEFT JOIN Center c ON m.center_id = c.id
                WHERE m.member_code = ?
            """, (selected_member,))
            member_info = c.fetchone()

            # Get arrears EMIs (overdue, unpaid)
            c.execute("""
                SELECT 
                    l.loanid,
                    lr.loanrecid,
                    lr.emisequence,
                    lr.duedate,
                    lr.principaldueamount,
                    lr.interestdueamount,
                    lr.savingsdueamount,
                    ISNULL(lr.principalpaidamount, 0),
                    ISNULL(lr.interestpaidamount, 0),
                    ISNULL(lr.savingspaidamount, 0),
                    DATEDIFF(day, lr.duedate, GETDATE()) AS days_overdue,
                    ISNULL(LP.ProductName, 'N/A')
                FROM Loans l
                JOIN LoanRec lr ON l.loanid = lr.loanid
                LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
                WHERE l.member_code = ?
                  AND lr.paid = 0
                  AND lr.emisequence > 0
                  AND lr.duedate < CAST(GETDATE() AS DATE)
                  AND l.loanstatus = 'Active'
                ORDER BY lr.duedate, lr.emisequence
            """, (selected_member,))
            arrears_emis = c.fetchall()

        # POST: Process arrears recovery
        if request.method == "POST":
            selected_arrears = request.form.getlist("selected_arrear")
            if not selected_arrears:
                flash("No arrears selected.", "warning")
                return redirect(url_for("rec_member.member_arrears", member_code=selected_member))

            try:
                posted_count = 0
                total_collected = Decimal("0.00")

                for lrec_id_str in selected_arrears:
                    lrec_id = int(lrec_id_str)
                    
                    # Get recovery amounts (Interest-first priority)
                    interest_paid = float(request.form.get(f"i_{lrec_id}", 0) or 0)
                    principal_paid = float(request.form.get(f"p_{lrec_id}", 0) or 0)
                    savings_paid = float(request.form.get(f"s_{lrec_id}", 0) or 0)

                    total_paid = interest_paid + principal_paid + savings_paid

                    # Get current LoanRec
                    c.execute("""
                        SELECT loanid, principaldueamount, interestdueamount, savingsdueamount,
                               principalpaidamount, interestpaidamount, savingspaidamount
                        FROM LoanRec WHERE loanrecid = ?
                    """, (lrec_id,))
                    lr = c.fetchone()
                    if not lr:
                        continue

                    loanid = lr[0]
                    principal_due = float(lr[1] or 0)
                    interest_due = float(lr[2] or 0)
                    savings_due = float(lr[3] or 0)
                    prev_principal_paid = float(lr[4] or 0)
                    prev_interest_paid = float(lr[5] or 0)
                    prev_savings_paid = float(lr[6] or 0)

                    # Calculate new totals
                    new_interest_paid = prev_interest_paid + interest_paid
                    new_principal_paid = prev_principal_paid + principal_paid
                    new_savings_paid = prev_savings_paid + savings_paid

                    # Check if fully paid
                    mark_paid = (new_principal_paid >= principal_due and
                                new_interest_paid >= interest_due and
                                new_savings_paid >= savings_due)

                    # Update LoanRec
                    c.execute("""
                        UPDATE LoanRec
                        SET principalpaidamount = ?,
                            interestpaidamount = ?,
                            savingspaidamount = ?,
                            paid = ?,
                            recoverydate = GETDATE(),
                            paymentmode = 'Arrears',
                            recordversion = recordversion + 1,
                            modifiedby = ?,
                            modifieddate = GETDATE()
                        WHERE loanrecid = ?
                    """, (new_principal_paid, new_interest_paid, new_savings_paid,
                          (1 if mark_paid else 0), user_id, lrec_id))

                    # Update Loans outstanding
                    c.execute("""
                        UPDATE Loans
                        SET principaloutstanding = principaloutstanding - ?,
                            interestoutstanding = interestoutstanding - ?,
                            modifiedby = ?,
                            modifieddate = GETDATE()
                        WHERE loanid = ?
                    """, (principal_paid, interest_paid, user_id, loanid))

                    _close_loan_if_done(c, loanid, user_id)

                    posted_count += 1
                    total_collected += Decimal(str(total_paid))

                conn.commit()
                flash(f"✅ Arrears posted! {posted_count} EMI(s) | Total: ₹{float(total_collected):,.2f}", "success")
                return redirect(url_for("rec_member.member_arrears", member_code=selected_member))

            except Exception as e:
                conn.rollback()
                flash(f"Error: {str(e)}", "danger")
                import traceback
                traceback.print_exc()
                return redirect(url_for("rec_member.member_arrears", member_code=selected_member))

    except Exception as e:
        flash(f"Page error: {str(e)}", "danger")
        members = []
        selected_member = None
        member_info = None
        arrears_emis = []

    finally:
        conn.close()

    return render_template("rec_member_arrears.html",
                          members=members,
                          selected_member=selected_member,
                          member_info=member_info,
                          arrears_emis=arrears_emis,
                          today=datetime.now().strftime('%d %b %Y'))
