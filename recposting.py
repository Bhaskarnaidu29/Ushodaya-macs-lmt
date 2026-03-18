import pyodbc
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from datetime import datetime

recposting_bp = Blueprint("recposting", __name__, template_folder="templates")


@recposting_bp.route("/recposting", methods=["GET", "POST"])
def recposting():
    conn = get_db_connection()
    cursor = conn.cursor()

    # ðŸ”¹ Centers dropdownpip install pdbpp
    cursor.execute("SELECT id, center_name FROM Center")
    centers = cursor.fetchall()

    loans = []
    selected_center = None
    now = datetime(2025, 12, 22, 0, 0, 0)  # year, month, day, hour, minute, second #datetime.now()

    if request.method == "POST":
        selected_center = request.form.get("center_id")

        # ðŸ”¹ Fetch loans for selected center
        query = """
                select l.branchid, \
                       0                                                                                 as IsArrear,
                       lr.loanrecid, \
                       l.loanid, \
                       l.member_code, \
                       m.full_name, \
                       l.loanAmountApproved                                                              AS loan_amount, \
                       lr.emisequence,
                       SUM(lr.principaldueamount)                                                        as principaldueamount, \
                       SUM(lr.interestdueamount)                                                         as interestdueamount, \
                       SUM(lr.savingsdueamount)                                                          as savingsdueamount,
                       SUM(lr.principaldueamount)                                                        as pastDuePrin, \
                       SUM(lr.interestdueamount)                                                         as pastDueInt, \
                       SUM(lr.savingsdueamount)                                                          as pastDueSavings, \
                       SUM(lr.principaldueamount) + SUM(lr.interestdueamount) + SUM(lr.savingsdueamount) AS TotalAmount
                from LoanRec lr
                         INNER JOIN Loans l ON lr.loanid = l.loanid and l.loanid not in (select l.loanid \
                                                                                         from LoanRec lr \
                                                                                                  INNER JOIN Loans l ON lr.loanid = l.loanid \
                                                                                                  INNER JOIN Members m ON l.member_code = m.member_code \
                                                                                                  INNER JOIN Center c ON m.center_id = c.id and c.id = ? \
                                                                                         where lr.principaldueamount \
                    !=0 and
                   (lr.principaldueamount+lr.interestdueamount+lr.savingsdueamount)-(lr.principalpaidamount+lr.interestpaidamount+lr.savingspaidamount) \
                   >0
                    and CONVERT (date \
                   , lr.duedate) \
                   < ?
                group by l.loanid
                    )
                    INNER JOIN Members m \
                ON l.member_code = m.member_code
                    INNER JOIN Center c ON m.center_id = c.id and c.id = ?
                where lr.principaldueamount !=0 and lr.recoverydate is null and CONVERT (date, lr.duedate)= ?
                group by l.branchid, lr.loanrecid, l.loanid, l.member_code, m.full_name, l.loanAmountApproved, lr.emisequence
                UNION ALL
                select l.branchid, \
                       1                                                                          as IsArrear,
                       0                                                                          as loanrecid, \
                       l.loanid, \
                       l.member_code, \
                       m.full_name, \
                       l.loanAmountApproved                                                       AS loan_amount, \
                       0                                                                          as emisequence,
                       0                                                                          as principaldueamount, \
                       0                                                                          as interestdueamount, \
                       0                                                                          as savingsdueamount,
                       SUM(lr.principaldueamount) - SUM(lr.principalpaidamount)                   as pastDuePrin, \
                       SUM(lr.interestdueamount) - SUM(lr.interestpaidamount)                     as pastDueInt,
                       SUM(lr.savingsdueamount) - SUM(lr.savingspaidamount)                       as pastDueSavings,
                       SUM(lr.principaldueamount + lr.interestdueamount + lr.savingsdueamount) - \
                       SUM(lr.principalpaidamount + lr.interestpaidamount + lr.savingspaidamount) AS TotalAmount
                from LoanRec lr
                         INNER JOIN Loans l ON lr.loanid = l.loanid
                         INNER JOIN Members m ON l.member_code = m.member_code
                         INNER JOIN Center c ON m.center_id = c.id and c.id = ?
                where lr.principaldueamount !=0 and 
                (lr.principaldueamount+lr.interestdueamount+lr.savingsdueamount)-(lr.principalpaidamount+lr.interestpaidamount+lr.savingspaidamount)>0
                and CONVERT(date, lr.duedate)< ?
                group by l.branchid, l.loanid, l.member_code, m.full_name, l.loanAmountApproved \
                """
        cursor.execute(query, (selected_center, now, selected_center, now, selected_center, now))
        loans = cursor.fetchall()

        # ðŸ”¹ Save recoveries
        if "save" in request.form:
            for loan in loans:
                loanid = loan.loanid
                member_code = loan.member_code

                principal_amt = float(request.form.get(f"principal_{loanid}", 0) or 0)
                interest_amt = float(request.form.get(f"interest_{loanid}", 0) or 0)
                savings_amt = float(request.form.get(f"savings_{loanid}", 0) or 0)
                addl_savings_amt = float(request.form.get(f"addlsavings_{loanid}", 0) or 0)
                adv_recovery = float(request.form.get(f"adv_{loanid}", 0) or 0)
                paid_amount = float(request.form.get(f"paidamount_{loanid}", 0) or 0)
                payment_mode = request.form.get(f"paymentmode_{loanid}", "Cash")
                prepaid_default = 1 if request.form.get(f"prepaid_{loanid}") else 0

                arrprincipal = loan.principaldueamount  # -principal_amt
                arrinterest = loan.interestdueamount  # -interest_amt

                if prepaid_default == 1:

                    # ðŸ”¹ If Advance collected â†’ update Loans.advbalance
                    if adv_recovery > 0:
                        cursor.execute("""
                                       UPDATE Loans
                                       SET advbalance = ISNULL(advbalance, 0) + ?
                                       WHERE loanid = ?
                                       """, (adv_recovery, loanid))

                        # # ðŸ”¹ Fetch loanrecid
                        # cursor.execute("""

                        # """, (selected_center,now))

                    if loan.loanrecid != 0:
                        # ðŸ”¹ Update LoanRec with paid amounts
                        cursor.execute("""
                                       UPDATE LoanRec
                                       SET principalpaidamount         = ISNULL(principalpaidamount, 0) + ?,
                                           interestpaidamount          = ISNULL(interestpaidamount, 0) + ?,
                                           savingspaidamount           = ISNULL(savingspaidamount, 0) + ?,
                                           additionalsavingspaidamount = ISNULL(additionalsavingspaidamount, 0) + ?,
                                           paid                        = 1,
                                           modifiedby                  = ?,
                                           modifieddate                = GETDATE(),
                                           recoverydate                = GETDATE(),
                                           paymentmode                 = ?,
                                           preemideducted              = ?,
                                           arrprincipaldue             = ?,
                                           arrinterestdue              = ?
                                       WHERE loanrecid = ?
                                       """, (
                                           principal_amt, interest_amt, savings_amt, addl_savings_amt,
                                           session.get("username", "system"), payment_mode, prepaid_default,
                                           arrprincipal, arrinterest, loan.loanrecid
                                       ))
                    else:
                        if paid_amount < interest_amt:
                            # All goes to interest
                            interest_amt = paid_amount
                            principal_amt = 0
                            savings_amt = 0
                        else:
                            # First cover interest fully
                            remaining = paid_amount - interest_amt

                            if remaining < principal_amt:
                                # Only part of principal can be covered
                                principal_amt = remaining
                                savings_amt = 0
                            else:
                                # Principal fully covered
                                remaining -= principal_amt

                                if remaining < savings_amt:
                                    savings_amt = remaining
                                else:
                                    # All savings covered (or capped)
                                    # If savings_amt should never increase, keep it unchanged
                                    # If it can take extra, assign remaining instead
                                    savings_amt = savings_amt

                        # One header record (emisequence=0)
                        cursor.execute("""
                                       INSERT INTO LoanRec (loanid, member_code, duedate, principaldueamount,
                                                            interestdueamount,
                                                            principalpaidamount, interestpaidamount, savingsdueamount,
                                                            savingspaidamount,
                                                            additionalsavingspaidamount, paid, preemideducted,
                                                            recordversion, createdby,
                                                            createddate, emisequence, recoverydate, paymentmode)
                                       VALUES (?, ?, GETDATE(), 0, 0, ?, ?, 0, ?, ?, 0, 0, 1, ?, GETDATE(), 0,
                                               GETDATE(), ?)
                                       """,
                                       (loanid, member_code, principal_amt, interest_amt, savings_amt, addl_savings_amt,
                                        session.get("user_id"), payment_mode))  # âœ… use user_id

                    # ðŸ”¹ Insert savings (General + Additional)
                    if savings_amt > 0:
                        cursor.execute("""
                                       INSERT INTO savings (member_code, loanrecid, amount, credit_debit, savingtype,
                                                            createdby, createddate, modifiedby, modifieddate,
                                                            transactiondate, loanid, paymentid, Branchid)
                                       VALUES (?, ?, ?, 'Credit', 'GENERAL', ?, GETDATE(), ?, GETDATE(), GETDATE(), ?,
                                               ?, ?)
                                       """,
                                       (member_code, loan.loanrecid, savings_amt, session.get("username", "system"),
                                        session.get("username", "system"), loanid, payment_mode, loan.branchid))

                    if addl_savings_amt > 0:
                        cursor.execute("""
                                       INSERT INTO savings (member_code, loanrecid, amount, credit_debit, savingtype,
                                                            createdby, createddate, modifiedby, modifieddate,
                                                            transactiondate, loanid, paymentid, Branchid)
                                       VALUES (?, ?, ?, 'Credit', 'ADDITIONAL', ?, GETDATE(), ?, GETDATE(), GETDATE(),
                                               ?, ?, ?)
                                       """, (member_code, loan.loanrecid, addl_savings_amt,
                                             session.get("username", "system"), session.get("username", "system"),
                                             loanid, payment_mode, loan.branchid))

            conn.commit()
            flash("âœ… Recovery Posting Saved Successfully!", "success")
            return redirect(url_for("recposting.recposting"))

    return render_template("recposting.html", centers=centers, loans=loans, selected_center=selected_center)


# ðŸ”¹ Undo Recovery (Admin Only)
@recposting_bp.route("/recposting/undo/<int:loanrecid>", methods=["POST"])
def undo_recovery(loanrecid):
    if session.get("role") != "admin":
        flash("âŒ Only Admin can undo recoveries!", "danger")
        return redirect(url_for("recposting.recposting"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ðŸ”¹ Get loanrec details before undo
    cursor.execute(
        "SELECT loanid, member_code, savingspaidamount, additionalsavingspaidamount FROM LoanRec WHERE loanrecid=?",
        (loanrecid,))
    row = cursor.fetchone()

    if not row:
        flash("âŒ Record not found!", "danger")
        return redirect(url_for("recposting.recposting"))

    loanid, member_code, gen_sav, addl_sav = row

    # ðŸ”¹ Reverse LoanRec
    cursor.execute("""
                   UPDATE LoanRec
                   SET principalpaidamount         = 0,
                       interestpaidamount          = 0,
                       savingspaidamount           = 0,
                       additionalsavingspaidamount = 0,
                       paid                        = 0,
                       modifiedby                  = ?,
                       modifieddate                = GETDATE(),
                       recoverydate                = NULL,
                       paymentmode                 = NULL,
                       preemideducted              = 0
                   WHERE loanrecid = ?
                   """, (session.get("username", "system"), loanrecid))

    # ðŸ”¹ Delete related savings records
    cursor.execute("DELETE FROM savings WHERE loanrecid=?", (loanrecid,))

    conn.commit()
    flash("âª Recovery successfully undone!", "warning")
    return redirect(url_for("recposting.recposting"))
