"""
Security Deposit Module
Handles withdrawal of security deposits from closed/prepaid/settled loans.
Security deposits are credited back to the member's savings account.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from db import get_db_connection
from login import login_required
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

security_deposit_bp = Blueprint("security_deposit", __name__, template_folder="templates")


# ─────────────────────────────────────────────────────────────
# Helper: Get loans with available security deposits for member
# ─────────────────────────────────────────────────────────────
def get_loans_with_security_deposit(member_code):
    """
    Returns loans that are Closed/Prepaid/Settled and have
    security deposit balance remaining for withdrawal.
    Columns: loanid, member_code, loanamount, securitydepositamount, withdrawn, loanstatus
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                l.loanid,
                l.member_code,
                l.loanamount,
                ISNULL(l.securitydepositamount, 0) AS securitydepositamount,
                ISNULL(
                    (SELECT SUM(amount) FROM SecurityDepositWithdrawals sdw
                     WHERE sdw.loanid = l.loanid), 0
                ) AS withdrawn,
                l.loanstatus
            FROM Loans l
            WHERE l.member_code = ?
              AND l.loanstatus IN ('Closed', 'Prepaid', 'Settled')
              AND ISNULL(l.securitydepositamount, 0) > 0
            ORDER BY l.loanid DESC
        """, (member_code,))
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error fetching security deposit loans: {e}")
        return []
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────
# Helper: Member search API (reused by autocomplete)
# ─────────────────────────────────────────────────────────────
def search_members_api(term):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 10 member_code, full_name
            FROM Members
            WHERE (member_code LIKE ? OR full_name LIKE ?)
              AND status = 'ACTIVE'
            ORDER BY member_code
        """, (f"%{term}%", f"%{term}%"))
        return [{"member_code": r[0], "full_name": r[1]} for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Member search error: {e}")
        return []
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────
# Route: Main Security Deposit Page (GET = search, POST = withdraw)
# ─────────────────────────────────────────────────────────────
@security_deposit_bp.route("/", methods=["GET", "POST"])
@login_required
def security_deposit():
    member_code = request.args.get("member_code", "").strip()
    loans = []

    if member_code:
        loans = get_loans_with_security_deposit(member_code)

    if request.method == "POST":
        loan_id      = request.form.get("loan_id")
        mem_code     = request.form.get("member_code", "").strip()
        amount_str   = request.form.get("amount", "0")
        created_by   = session.get("username", "system")

        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError("Amount must be positive")
        except ValueError as e:
            flash(f"Invalid amount: {e}", "danger")
            return redirect(url_for("security_deposit.security_deposit", member_code=mem_code))

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Verify available balance
            cursor.execute("""
                SELECT
                    ISNULL(l.securitydepositamount, 0),
                    ISNULL(
                        (SELECT SUM(amount) FROM SecurityDepositWithdrawals
                         WHERE loanid = l.loanid), 0
                    )
                FROM Loans l
                WHERE l.loanid = ? AND l.member_code = ?
            """, (loan_id, mem_code))
            row = cursor.fetchone()

            if not row:
                flash("Loan not found for this member.", "danger")
                return redirect(url_for("security_deposit.security_deposit", member_code=mem_code))

            total_deposit, already_withdrawn = float(row[0]), float(row[1])
            available = total_deposit - already_withdrawn

            if amount > available:
                flash(f"Withdrawal amount ₹{amount:,.2f} exceeds available ₹{available:,.2f}.", "danger")
                return redirect(url_for("security_deposit.security_deposit", member_code=mem_code))

            # 1. Record withdrawal
            cursor.execute("""
                INSERT INTO SecurityDepositWithdrawals
                    (loanid, member_code, amount, withdrawal_date, created_by, created_date)
                VALUES (?, ?, ?, CAST(GETDATE() AS DATE), ?, GETDATE())
            """, (loan_id, mem_code, amount, created_by))

            # 2. Credit to member savings
            cursor.execute("""
                INSERT INTO Savings
                    (member_code, credit_debit, amount, narration, transactiondate,
                     Branchid, createdby, createddate)
                VALUES (?, 'Credit', ?, ?, CAST(GETDATE() AS DATE), ?, ?, GETDATE())
            """, (mem_code, amount,
                  f"Security Deposit Withdrawal - Loan {loan_id}",
                  session.get("branchid", 1), created_by))

            conn.commit()
            logger.info(f"Security deposit withdrawal: LoanID={loan_id}, Member={mem_code}, "
                        f"Amount={amount}, By={created_by}")
            flash(f"₹{amount:,.2f} security deposit withdrawn and credited to savings account.", "success")

        except Exception as e:
            if conn:
                try: conn.rollback()
                except: pass
            logger.error(f"Security deposit withdrawal error: {e}")
            flash(f"Error processing withdrawal: {e}", "danger")
        finally:
            if conn:
                conn.close()

        return redirect(url_for("security_deposit.security_deposit", member_code=mem_code))

    return render_template(
        "security_deposit.html",
        loans=loans,
        member_code=member_code
    )


# ─────────────────────────────────────────────────────────────
# API: Member Autocomplete
# ─────────────────────────────────────────────────────────────
@security_deposit_bp.route("/api/members")
@login_required
def members_api():
    term = request.args.get("term", "").strip()
    if len(term) < 2:
        return jsonify([])
    return jsonify(search_members_api(term))


# ─────────────────────────────────────────────────────────────
# Route: Withdrawal History
# ─────────────────────────────────────────────────────────────
@security_deposit_bp.route("/history")
@login_required
def withdrawal_history():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                sdw.id, sdw.loanid, sdw.member_code,
                m.full_name, sdw.amount,
                sdw.withdrawal_date, sdw.created_by
            FROM SecurityDepositWithdrawals sdw
            LEFT JOIN Members m ON sdw.member_code = m.member_code
            ORDER BY sdw.created_date DESC
        """)
        records = cursor.fetchall()
        return render_template("security_deposit_history.html", records=records)
    except Exception as e:
        logger.error(f"Error fetching withdrawal history: {e}")
        flash("Error loading withdrawal history.", "danger")
        return redirect(url_for("security_deposit.security_deposit"))
    finally:
        if conn:
            conn.close()
