"""
Security Deposit Withdrawal Module
════════════════════════════════════════════════════════════════════════════
BUSINESS RULE:
  When a loan is CLOSED, the member is entitled to receive back:
    1. Security Deposit Principal  = Loans.securitydepositamount
    2. Interest on Security Deposit = Principal × LoanProduct.IntSecurityDeposit%
                                       × (loan tenure in years)

  Total Payout = Principal + Interest

  On withdrawal:
    - Loans.securitydepositwithdrawn  is updated to the principal amount
    - A Credit entry is posted to Savings for the total payout
    - A Debit entry is posted to SecurityDepositLedger for audit trail

ELIGIBILITY:
  - Loan status must be 'Closed', 'Prepaid', or 'Settled'
  - securitydepositamount > 0
  - securitydepositwithdrawn must be 0 (not already withdrawn)

TABLES USED:
  Loans             - securitydepositamount, securitydepositwithdrawn,
                      disbursementdate, productid, loanstatus, tenure
  LoanProduct       - IntSecurityDeposit (% per annum)
  Savings           - credit entry for member payout
  SecurityDepositLedger - audit / debit entry (created if not exists)
════════════════════════════════════════════════════════════════════════════
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from db import get_db_connection
from login import login_required
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)

sd_withdraw_bp = Blueprint("sd_withdraw", __name__, template_folder="templates")


# ════════════════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════════════════

def _calc_sd_interest(principal: Decimal, int_rate: Decimal,
                      disbursement_date, close_date=None) -> Decimal:
    """
    Calculate interest on security deposit.
    Interest = Principal × Rate% × (days held / 365)
    Uses actual days from disbursement to today (or close_date).
    """
    if not disbursement_date or int_rate <= 0 or principal <= 0:
        return Decimal('0')

    if close_date is None:
        close_date = date.today()

    if hasattr(disbursement_date, 'date'):
        disbursement_date = disbursement_date.date()

    days = (close_date - disbursement_date).days
    if days <= 0:
        return Decimal('0')

    interest = principal * int_rate / Decimal('100') * Decimal(str(days)) / Decimal('365')
    return interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _get_eligible_loans(member_code: str):
    """
    Fetch all loans eligible for security deposit withdrawal for a member.
    Returns list of dicts.
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
                ISNULL(l.securitydepositamount, 0)   AS sd_principal,
                ISNULL(l.securitydepositwithdrawn, 0) AS sd_withdrawn,
                l.loanstatus,
                l.disbursementdate,
                l.tenure,
                ISNULL(LP.IntSecurityDeposit, 0)      AS int_sd_rate,
                ISNULL(LP.ProductName, 'N/A')          AS product_name,
                m.full_name
            FROM Loans l
            JOIN Members m ON l.member_code = m.member_code
            LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
            WHERE l.member_code = ?
              AND l.loanstatus IN ('Closed', 'Prepaid', 'Settled')
              AND ISNULL(l.securitydepositamount, 0) > 0
              AND ISNULL(l.securitydepositwithdrawn, 0) = 0
            ORDER BY l.loanid DESC
        """, (member_code,))

        rows = cursor.fetchall()
        loans = []
        for r in rows:
            principal  = Decimal(str(r[3] or 0))
            int_rate   = Decimal(str(r[8] or 0))
            disb_date  = r[6]
            interest   = _calc_sd_interest(principal, int_rate, disb_date)
            total      = principal + interest

            loans.append({
                'loanid':        r[0],
                'member_code':   r[1],
                'loanamount':    float(r[2] or 0),
                'sd_principal':  float(principal),
                'sd_withdrawn':  float(r[4] or 0),
                'loanstatus':    r[5],
                'disbursement':  disb_date,
                'tenure':        r[7],
                'int_rate':      float(int_rate),
                'sd_interest':   float(interest),
                'sd_total':      float(total),
                'product_name':  r[9],
                'member_name':   r[10],
            })
        return loans

    except Exception as e:
        logger.error(f"Error fetching eligible SD loans: {e}")
        return []
    finally:
        if conn:
            conn.close()


def _ensure_ledger_table(cursor):
    """
    Ensure SecurityDepositLedger table exists.
    Creates it silently if absent — safe to call on every withdrawal.
    """
    cursor.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'SecurityDepositLedger'
        )
        CREATE TABLE SecurityDepositLedger (
            id               INT IDENTITY(1,1) PRIMARY KEY,
            loanid           INT           NOT NULL,
            member_code      VARCHAR(20)   NOT NULL,
            sd_principal     DECIMAL(12,2) NOT NULL,
            sd_interest      DECIMAL(12,2) NOT NULL DEFAULT 0,
            total_paid       DECIMAL(12,2) NOT NULL,
            int_rate         DECIMAL(5,2)  NOT NULL DEFAULT 0,
            withdrawal_date  DATE          NOT NULL,
            createdby        INT           NOT NULL,
            createddate      DATETIME      NOT NULL DEFAULT GETDATE(),
            remarks          VARCHAR(200)
        )
    """)


# ════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════

@sd_withdraw_bp.route("/", methods=["GET", "POST"])
@login_required
def sd_withdraw():
    """
    Main Security Deposit Withdrawal page.
    GET  : Show eligible loans for a member (searched by member_code).
    POST : Process the withdrawal for a specific loan.
    """
    member_code = request.args.get("member_code", "").strip()
    member_name = request.args.get("member_name", "").strip()
    loans       = []

    if member_code:
        loans = _get_eligible_loans(member_code)
        if loans:
            member_name = loans[0]['member_name']

    # ── POST: Process Withdrawal ──────────────────────────────────────────
    if request.method == "POST":
        loanid      = request.form.get("loanid", "").strip()
        mem_code    = request.form.get("member_code", "").strip()
        sd_principal= request.form.get("sd_principal", "0").strip()
        sd_interest = request.form.get("sd_interest", "0").strip()
        sd_total    = request.form.get("sd_total", "0").strip()
        int_rate    = request.form.get("int_rate", "0").strip()
        user_id     = session.get("user_id", 1)
        branchid    = session.get("branchid", 1)
        emp_name    = session.get("emp_name", "system")

        try:
            principal = Decimal(sd_principal)
            interest  = Decimal(sd_interest)
            total     = Decimal(sd_total)

            if total <= 0:
                flash("Invalid withdrawal amount.", "danger")
                return redirect(url_for("sd_withdraw.sd_withdraw", member_code=mem_code))

        except Exception:
            flash("Invalid amount values in form.", "danger")
            return redirect(url_for("sd_withdraw.sd_withdraw", member_code=mem_code))

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # ── Verify loan is still eligible ────────────────────────────
            cursor.execute("""
                SELECT l.loanstatus,
                       ISNULL(l.securitydepositamount, 0),
                       ISNULL(l.securitydepositwithdrawn, 0)
                FROM Loans l
                WHERE l.loanid = ? AND l.member_code = ?
            """, (loanid, mem_code))
            row = cursor.fetchone()

            if not row:
                flash("Loan not found.", "danger")
                return redirect(url_for("sd_withdraw.sd_withdraw", member_code=mem_code))

            status, sd_amt, already_withdrawn = row[0], float(row[1]), float(row[2])

            if status not in ('Closed', 'Prepaid', 'Settled'):
                flash(f"Loan #{loanid} is not closed (status: {status}).", "danger")
                return redirect(url_for("sd_withdraw.sd_withdraw", member_code=mem_code))

            if already_withdrawn > 0:
                flash(f"Security deposit for Loan #{loanid} has already been withdrawn.", "warning")
                return redirect(url_for("sd_withdraw.sd_withdraw", member_code=mem_code))

            if sd_amt <= 0:
                flash(f"No security deposit recorded for Loan #{loanid}.", "warning")
                return redirect(url_for("sd_withdraw.sd_withdraw", member_code=mem_code))

            # ── 1. Mark loan as security deposit withdrawn ────────────────
            cursor.execute("""
                UPDATE Loans
                SET securitydepositwithdrawn = ?,
                    modifiedby   = ?,
                    modifieddate = GETDATE()
                WHERE loanid = ?
            """, (float(principal), user_id, loanid))

            # ── 2. Credit total (principal + interest) to Savings ─────────
            narration = (
                f"Security Deposit Withdrawal - Loan #{loanid} | "
                f"Principal: ₹{float(principal):,.2f} + "
                f"Interest ({float(int_rate):.2f}%): ₹{float(interest):,.2f}"
            )
            cursor.execute("""
                INSERT INTO Savings (
                    member_code, credit_debit, amount, savingtype,
                    narration, transactiondate,
                    Branchid, createdby, createddate,
                    loanid, interestcalculated
                )
                VALUES (?, 'Credit', ?, 'SecurityDeposit',
                        ?, CAST(GETDATE() AS DATE),
                        ?, ?, GETDATE(),
                        ?, 0)
            """, (mem_code, float(total), narration, branchid, user_id, loanid))

            # ── 3. Write audit ledger entry ───────────────────────────────
            _ensure_ledger_table(cursor)
            cursor.execute("""
                INSERT INTO SecurityDepositLedger (
                    loanid, member_code, sd_principal, sd_interest,
                    total_paid, int_rate, withdrawal_date,
                    createdby, createddate, remarks
                )
                VALUES (?, ?, ?, ?, ?, ?, CAST(GETDATE() AS DATE),
                        ?, GETDATE(), ?)
            """, (
                loanid, mem_code,
                float(principal), float(interest),
                float(total), float(int_rate),
                user_id,
                f"Withdrawn by {emp_name}"
            ))

            conn.commit()

            logger.info(
                f"SD Withdrawal: Loan={loanid} Member={mem_code} "
                f"Principal={principal} Interest={interest} Total={total} By={emp_name}"
            )
            flash(
                f"Security deposit withdrawn successfully! "
                f"Principal: ₹{float(principal):,.2f} + "
                f"Interest: ₹{float(interest):,.2f} = "
                f"Total ₹{float(total):,.2f} credited to savings.",
                "success"
            )

        except Exception as e:
            if conn:
                try: conn.rollback()
                except: pass
            logger.error(f"SD withdrawal error: {e}", exc_info=True)
            flash(f"Error processing withdrawal: {e}", "danger")
        finally:
            if conn:
                conn.close()

        return redirect(url_for("sd_withdraw.sd_withdraw", member_code=mem_code))

    # ── GET ──────────────────────────────────────────────────────────────
    return render_template(
        "security_deposit_withdraw.html",
        loans=loans,
        member_code=member_code,
        member_name=member_name,
        today=date.today().strftime('%d %b %Y'),
    )


# ════════════════════════════════════════════════════════════════════════════
# API: Member autocomplete
# ════════════════════════════════════════════════════════════════════════════

@sd_withdraw_bp.route("/api/members")
@login_required
def members_api():
    term = request.args.get("term", "").strip()
    if len(term) < 2:
        return jsonify([])
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 10 member_code, full_name
            FROM Members
            WHERE (member_code LIKE ? OR full_name LIKE ?)
            ORDER BY member_code
        """, (f"%{term}%", f"%{term}%"))
        return jsonify([{"member_code": r[0], "full_name": r[1]}
                        for r in cursor.fetchall()])
    except Exception as e:
        logger.error(f"Member search error: {e}")
        return jsonify([])
    finally:
        if conn:
            conn.close()


# ════════════════════════════════════════════════════════════════════════════
# API: Get loan SD details (for dynamic interest preview)
# ════════════════════════════════════════════════════════════════════════════

@sd_withdraw_bp.route("/api/loan/<int:loanid>")
@login_required
def loan_sd_details(loanid):
    """Return SD principal, interest rate, calculated interest, total for a loan."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                ISNULL(l.securitydepositamount, 0),
                l.disbursementdate,
                ISNULL(LP.IntSecurityDeposit, 0)
            FROM Loans l
            LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
            WHERE l.loanid = ?
        """, (loanid,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Loan not found"}), 404

        principal = Decimal(str(row[0] or 0))
        int_rate  = Decimal(str(row[2] or 0))
        interest  = _calc_sd_interest(principal, int_rate, row[1])
        total     = principal + interest

        return jsonify({
            "sd_principal": float(principal),
            "int_rate":     float(int_rate),
            "sd_interest":  float(interest),
            "sd_total":     float(total),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# ════════════════════════════════════════════════════════════════════════════
# Route: Withdrawal History
# ════════════════════════════════════════════════════════════════════════════

@sd_withdraw_bp.route("/history")
@login_required
def history():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if ledger table exists before querying
        cursor.execute("""
            SELECT COUNT(1) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'SecurityDepositLedger'
        """)
        exists = cursor.fetchone()[0]

        records = []
        if exists:
            cursor.execute("""
                SELECT
                    sdl.id,
                    sdl.loanid,
                    sdl.member_code,
                    m.full_name,
                    sdl.sd_principal,
                    sdl.sd_interest,
                    sdl.total_paid,
                    sdl.int_rate,
                    sdl.withdrawal_date,
                    sdl.remarks
                FROM SecurityDepositLedger sdl
                LEFT JOIN Members m ON sdl.member_code = m.member_code
                ORDER BY sdl.createddate DESC
            """)
            records = cursor.fetchall()

        return render_template("security_deposit_withdraw_history.html", records=records)

    except Exception as e:
        logger.error(f"SD history error: {e}")
        flash("Error loading withdrawal history.", "danger")
        return redirect(url_for("sd_withdraw.sd_withdraw"))
    finally:
        if conn:
            conn.close()
