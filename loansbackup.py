"""
Loans Management Module
─────────────────────────────────────────────────────────────────────────────
EMI ROUNDING RULES:
  • Raw EMI → round to nearest ₹5  (e.g. ₹1043.20 → ₹1045)
  • If rounded EMI ends in 5 → keep; if ends in 0 → keep
  • Last EMI = remaining principal + interest on that period
    (absorbs all rounding differences so loan closes exactly)

CHARGE CALCULATION (stored in Loans table):
  processingfee     = loanamount × LP.ProcessingFee / 100
  memberinsurancefee= loanamount × LP.MemberInsurance / 100
  nomineeinsurancefee= loanamount × LP.NomineeInsurance / 100
  savingsdueamount  = loanamount × LP.Savings / 100
  securitydepositamount = loanamount × LP.SecurityDeposit / 100

LOANREC RECORDS:
  Weekly  : tenure EMI rows (EMI #1 … EMI #tenure)
  Monthly : tenure EMI rows (EMI #1 … EMI #tenure)
  (No extra row needed; total = tenure rows)

COLLECTION DAY:
  Weekly  : next occurrence of center's weekly_collection_day after disburse,
            then every +7 days
  Monthly : center's collection_day of month, starting next month
─────────────────────────────────────────────────────────────────────────────
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta, date
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from db import get_db_connection
from login import login_required
import logging
import calendar
import math

logger = logging.getLogger(__name__)

loans_bp = Blueprint("loans", __name__, template_folder="templates")


# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def round_to_nearest_5(amount: Decimal) -> Decimal:
    """
    Round amount to nearest ₹5.
    Examples: 1043 → 1045, 1042 → 1040, 1047.50 → 1050, 1042.50 → 1040
    """
    # Divide by 5, round to integer (ROUND_HALF_UP), multiply by 5
    units = (amount / Decimal('5')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return units * Decimal('5')


def round_to_nearest_10(amount: Decimal) -> Decimal:
    """Round amount to nearest ₹10."""
    units = (amount / Decimal('10')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return units * Decimal('10')


def get_next_weekday(start_date, target_weekday):
    """
    Get next occurrence of target_weekday strictly AFTER start_date.
    target_weekday: 0=Monday … 6=Sunday
    """
    days_ahead = target_weekday - start_date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return start_date + timedelta(days=days_ahead)


def add_months(source_date, months, target_day=None):
    """
    Add months to source_date.
    If target_day is given, set day to that (clamped to month-end).
    """
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    if target_day:
        day = min(target_day, calendar.monthrange(year, month)[1])
    else:
        day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_emi_raw(principal: Decimal, annual_rate: Decimal,
                      tenure: int, is_weekly: bool = False) -> Decimal:
    """
    Reducing-balance EMI (exact, before rounding).
    Weekly  : period rate = annual_rate / 52 / 100
    Monthly : period rate = annual_rate / 12 / 100
    """
    if annual_rate == 0 or annual_rate is None:
        return (principal / Decimal(tenure)).quantize(Decimal('0.01'), ROUND_HALF_UP)

    r = (annual_rate / Decimal(100) /
         (Decimal('52') if is_weekly else Decimal('12')))
    p = principal
    n = Decimal(tenure)
    power = (1 + r) ** n
    emi = (p * r * power) / (power - 1)
    return emi.quantize(Decimal('0.01'), ROUND_HALF_UP)


def calculate_emi_rounded(principal: Decimal, annual_rate: Decimal,
                           tenure: int, is_weekly: bool = False) -> Decimal:
    """
    EMI rounded to nearest ₹5.
    Last EMI will be adjusted separately at schedule-generation time.
    """
    raw = calculate_emi_raw(principal, annual_rate, tenure, is_weekly)
    return round_to_nearest_5(raw)


def compute_charges(loan_amount: Decimal, lp_processing: Decimal,
                    lp_member_ins: Decimal, lp_nominee_ins: Decimal,
                    lp_savings: Decimal, lp_security: Decimal) -> dict:
    """
    Compute actual ₹ charge amounts from product percentage fields.
    Formula: charge = loanamount × rate / 100
    """
    def pct(rate):
        return (loan_amount * Decimal(str(rate or 0)) / Decimal('100')).quantize(
            Decimal('0.01'), ROUND_HALF_UP)

    return {
        'processingfee':      pct(lp_processing),
        'memberinsurancefee': pct(lp_member_ins),
        'nomineeinsurancefee':pct(lp_nominee_ins),
        'savingsdueamount':   pct(lp_savings),
        'securitydepositamount': pct(lp_security),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@loans_bp.route("/", methods=["GET"])
@login_required
def index():
    """Display approved applications (pending disbursement) and existing loans."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Approved applications not yet disbursed
        cursor.execute("""
            SELECT
                LA.LoanApplicationID,               -- [0]
                LA.MemberCode,                      -- [1]
                M.full_name  AS MemberName,         -- [2]
                C.center_name AS CenterName,        -- [3]
                LA.LoanAmountApproved,              -- [4]
                LP.ProductName,                     -- [5]
                LP.InterestRate,                    -- [6]
                LA.Tenure,                          -- [7]
                LA.ApprovedOn,                      -- [8]
                LP.ProcessingFee,                   -- [9]  (% rate)
                LP.MemberInsurance,                 -- [10] (% rate)
                LP.NomineeInsurance,                -- [11] (% rate)
                LP.Savings,                         -- [12] (% rate)
                LP.AdditionalSavings,               -- [13] (% rate)
                LP.SecurityDeposit,                 -- [14] (% rate)
                LP.PaymentFrequency                 -- [15]
            FROM LoanApplication LA
            LEFT JOIN Members M  ON LA.MemberCode = M.member_code
            LEFT JOIN Center  C  ON C.center_name  = LA.CenterName
            LEFT JOIN LoanProduct LP ON LA.LoanTypeID = LP.ProductID
            WHERE LA.ApplicationStatus = 'Approved'
              AND LA.branchid = ?
              AND NOT EXISTS (
                  SELECT 1 FROM Loans L
                  WHERE L.loanapplicationid = LA.LoanApplicationID
              )
            ORDER BY LA.ApprovedOn DESC
        """, (session.get('branchid', 1),))
        approved_apps = cursor.fetchall()

        # Existing loans
        cursor.execute("""
            SELECT
                L.loanid,                           -- [0]
                L.member_code,                      -- [1]
                M.full_name  AS MemberName,         -- [2]
                C.center_name AS CenterName,        -- [3]
                L.loanamount,                       -- [4]
                L.interestrate,                     -- [5]
                L.tenure,                           -- [6]
                L.emi,                              -- [7]
                L.principaloutstanding,             -- [8]
                L.loanstatus,                       -- [9]
                L.disbursementdate,                 -- [10]
                LP.ProductName,                     -- [11]
                LP.PaymentFrequency                 -- [12]
            FROM Loans L
            LEFT JOIN Members M  ON L.member_code = M.member_code
            LEFT JOIN Center  C  ON M.center_id   = C.id
            LEFT JOIN LoanProduct LP ON L.productid = LP.ProductID
            WHERE L.branchid = ?
            ORDER BY L.disbursementdate DESC
        """, (session.get('branchid', 1),))
        loans = cursor.fetchall()
        conn.close()

        return render_template("loans.html",
                               approved_apps=approved_apps,
                               loans=loans)

    except Exception as e:
        logger.error(f"Error loading loans: {e}")
        flash(f"Error loading loans: {str(e)}", "danger")
        return render_template("loans.html", approved_apps=[], loans=[])


# ─── GET: disburse form ────────────────────────────────────────────────────

@loans_bp.route("/disburse/<int:app_id>", methods=["GET"])
@login_required
def disburse_loan(app_id):
    """Show disbursement confirmation form."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                LA.LoanApplicationID,               -- [0]
                LA.MemberCode,                      -- [1]
                M.full_name  AS MemberName,         -- [2]
                M.phone1,                           -- [3]
                C.center_name AS CenterName,        -- [4]
                LA.LoanAmountApproved,              -- [5]
                LP.ProductName,                     -- [6]
                LP.InterestRate,                    -- [7]
                LA.Tenure,                          -- [8]
                LP.ProcessingFee,                   -- [9]  (%)
                LP.MemberInsurance,                 -- [10] (%)
                LP.NomineeInsurance,                -- [11] (%)
                LP.Savings,                         -- [12] (%)
                LP.AdditionalSavings,               -- [13] (%)
                LP.SecurityDeposit,                 -- [14] (%)
                LP.PaymentFrequency,                -- [15]
                C.collection_day,                   -- [16]
                C.weekly_collection_day             -- [17]
            FROM LoanApplication LA
            LEFT JOIN Members M  ON LA.MemberCode = M.member_code
            LEFT JOIN Center  C  ON C.center_name  = LA.CenterName
            LEFT JOIN LoanProduct LP ON LA.LoanTypeID = LP.ProductID
            WHERE LA.LoanApplicationID = ?
              AND LA.ApplicationStatus = 'Approved'
        """, (app_id,))

        application = cursor.fetchone()
        conn.close()

        if not application:
            flash("Application not found or not in Approved status.", "warning")
            return redirect(url_for("loans.index"))

        loan_amount      = Decimal(str(application[5] or 0))
        interest_rate    = Decimal(str(application[7] or 0))
        tenure           = int(application[8] or 0)
        payment_freq     = (application[15] or 'Monthly').strip().upper()
        is_weekly        = payment_freq in ('WEEKLY', 'WEEK')
        collection_day   = application[16]
        weekly_coll_day  = application[17]

        # Rounded EMI for display
        emi = calculate_emi_rounded(loan_amount, interest_rate, tenure, is_weekly)

        # Charge amounts (₹)
        charges = compute_charges(
            loan_amount,
            application[9], application[10], application[11],
            application[12], application[14]
        )

        # Collection schedule description
        weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        if is_weekly:
            collection_info = (weekdays[int(weekly_coll_day)]
                               if weekly_coll_day is not None else 'Monday')
        else:
            collection_info = (f"{int(collection_day)}th of every month"
                               if collection_day else "15th of every month")

        today = date.today().strftime('%Y-%m-%d')

        return render_template("loans_disburse.html",
                               application=application,
                               emi=emi,
                               charges=charges,
                               is_weekly=is_weekly,
                               collection_info=collection_info,
                               today=today)

    except Exception as e:
        logger.error(f"Error loading disburse form: {e}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("loans.index"))


# ─── POST: confirm disbursement ────────────────────────────────────────────

@loans_bp.route("/disburse/<int:app_id>/confirm", methods=["POST"])
@login_required
def confirm_disburse(app_id):
    """
    Process disbursement:
    1. Compute charges from product % rates × loan amount
    2. Insert 1 Loans row
    3. Insert tenure LoanRec rows (EMI #1 … tenure)
       – Rows #1 … (tenure-1): rounded EMI (principal = EMI − interest)
       – Row  #tenure         : principal = remaining outstanding,
                                interest  = interest on that balance
                                (last-EMI adjustment closes loan exactly)
    4. Update LoanApplication status → Disbursed
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        disbursement_date_str  = request.form.get('disbursement_date')
        payment_mode           = request.form.get('payment_mode', 'Cash')
        # Actual disbursed amount (may differ from approved; user can edit on form)
        actual_loan_amount_str = request.form.get('actual_loan_amount', '').strip()
        # Additional savings entered manually per EMI (₹ amount, not %)
        addl_sav_manual_str    = request.form.get('additional_savings_manual', '0').strip() or '0'

        # ── Fetch application + product details ──────────────────────────
        cursor.execute("""
            SELECT
                LA.LoanApplicationID,           -- [0]
                LA.MemberCode,                  -- [1]
                LA.LoanAmountApproved,          -- [2]
                LA.LoanTypeID,                  -- [3]  = ProductID
                LA.Tenure,                      -- [4]
                LA.branchid,                    -- [5]
                LP.InterestRate,                -- [6]
                LP.ProcessingFee,               -- [7]  (%)
                LP.MemberInsurance,             -- [8]  (%)
                LP.NomineeInsurance,            -- [9]  (%)
                LP.Savings,                     -- [10] (%)
                LP.AdditionalSavings,           -- [11] (%)
                LP.SecurityDeposit,             -- [12] (%)
                LP.PaymentFrequency,            -- [13]
                C.collection_day,              -- [14]
                C.weekly_collection_day,        -- [15]
                LA.CenterName                   -- [16]
            FROM LoanApplication LA
            LEFT JOIN LoanProduct LP ON LA.LoanTypeID  = LP.ProductID
            LEFT JOIN Center      C  ON C.center_name  = LA.CenterName
            WHERE LA.LoanApplicationID = ?
              AND LA.ApplicationStatus = 'Approved'
        """, (app_id,))

        app = cursor.fetchone()
        if not app:
            flash("Application not found or not in Approved status.", "warning")
            return redirect(url_for("loans.index"))

        # ── Extract fields ────────────────────────────────────────────────
        member_code      = app[1]
        approved_amount  = Decimal(str(app[2] or 0))
        # Use form-entered amount if provided and valid; else use approved amount
        try:
            loan_amount = Decimal(actual_loan_amount_str) if actual_loan_amount_str else approved_amount
            if loan_amount <= 0:
                loan_amount = approved_amount
        except Exception:
            loan_amount = approved_amount
        product_id       = app[3]
        tenure           = int(app[4] or 0)
        branch_id        = app[5]
        interest_rate    = Decimal(str(app[6] or 0))

        # Product % rates
        lp_processing    = Decimal(str(app[7]  or 0))
        lp_member_ins    = Decimal(str(app[8]  or 0))
        lp_nominee_ins   = Decimal(str(app[9]  or 0))
        lp_savings       = Decimal(str(app[10] or 0))
        lp_addl_savings  = Decimal(str(app[11] or 0))
        lp_security      = Decimal(str(app[12] or 0))

        payment_freq     = (app[13] or 'Monthly').strip().upper()
        collection_day   = app[14]
        weekly_coll_day  = app[15]
        is_weekly        = payment_freq in ('WEEKLY', 'WEEK')

        disb_date = datetime.strptime(disbursement_date_str, '%Y-%m-%d').date()

        # ── Compute actual ₹ charges (loanamount × rate%) ────────────────
        charges = compute_charges(
            loan_amount,
            lp_processing, lp_member_ins, lp_nominee_ins,
            lp_savings, lp_security
        )
        # savings_per_emi (from savings % of actual loan amount)
        savings_per_emi  = charges['savingsdueamount']   # per-EMI savings due
        # Additional savings per EMI:
        #   If user entered a manual amount → use that (₹)
        #   Else fall back to product % × loan amount
        try:
            addl_sav_manual = Decimal(addl_sav_manual_str)
        except Exception:
            addl_sav_manual = Decimal('0')

        if addl_sav_manual > 0:
            addl_savings_per_emi = addl_sav_manual
        else:
            addl_savings_per_emi = (
                loan_amount * lp_addl_savings / Decimal('100')
            ).quantize(Decimal('0.01'), ROUND_HALF_UP)

        # ── Period interest rate ──────────────────────────────────────────
        if is_weekly:
            period_rate = interest_rate / Decimal('52') / Decimal('100')
        else:
            period_rate = interest_rate / Decimal('12') / Decimal('100')

        # ── Rounded EMI (₹5 rounding) ────────────────────────────────────
        emi = calculate_emi_rounded(loan_amount, interest_rate, tenure, is_weekly)

        # ── Pre-calculate total interest for Loans.interestoutstanding ───
        op = loan_amount
        total_interest = Decimal(0)
        for period in range(1, tenure + 1):
            int_amt = (op * period_rate).quantize(Decimal('0.01'), ROUND_HALF_UP)
            if period == tenure:
                # last EMI: principal = whatever remains
                prin_amt = op
            else:
                prin_amt = emi - int_amt
                if prin_amt > op:          # safety clamp
                    prin_amt = op
            total_interest += int_amt
            op -= prin_amt

        user_id = session.get('user_id', 1)

        # ── 1. INSERT Loans row ───────────────────────────────────────────
        cursor.execute("""
            INSERT INTO Loans (
                member_code, loanamount, interestrate, tenure, emi,
                principaloutstanding, interestoutstanding,
                loanstatus, disbursementdate, productid,
                prepaidamount, preclosurecharges,
                processingfee, memberinsurancefee, nomineeinsurancefee,
                savingsdueamount, othercharges,
                usedsavingsonprepaid, usedaddlsavingsonprepaid,
                securitydepositamount, securitydepositwithdrawn,
                prepaidfullsavings, advbalance,
                branchid, loanapplicationid,
                createdby, createddate,
                modifiedby, modifieddate
            )
            OUTPUT INSERTED.loanid
            VALUES (
                ?, ?, ?, ?, ?,
                ?, ?,
                'Active', ?, ?,
                0, 0,
                ?, ?, ?,
                ?, 0,
                0, 0,
                ?, 0,
                0, 0,
                ?, ?,
                ?, GETDATE(),
                ?, GETDATE()
            )
        """, (
            member_code,
            float(loan_amount),
            float(interest_rate),
            tenure,
            float(emi),

            float(loan_amount),          # principaloutstanding = full amount at start
            float(total_interest),       # interestoutstanding  = total interest

            disb_date,
            product_id,

            float(charges['processingfee']),
            float(charges['memberinsurancefee']),
            float(charges['nomineeinsurancefee']),

            float(charges['savingsdueamount']),  # savings per EMI

            float(charges['securitydepositamount']),

            branch_id,
            app_id,               # loanapplicationid

            user_id,              # createdby
            user_id,              # modifiedby
        ))

        result  = cursor.fetchone()
        loan_id = result[0]

        # ── 2. INSERT LoanRec rows  (TOTAL = 1 + tenure) ──────────────────
        #
        # ROW  0  (emisequence=0) : LOAN-TAKEN RECORD
        #   duedate             = disbursement_date   (date loan was given)
        #   principaldueamount  = full loan amount    (total amount disbursed)
        #   interestdueamount   = 0
        #   principalpaidamount = 0   (no payment yet)
        #   paid                = 0
        #
        # ROWS 1 … tenure : REGULAR EMI ROWS
        #   Weekly  : due on disbursement + n×7 days
        #   Monthly : due on disbursement + n months at center collection_day
        #   Last EMI principal adjusted to close loan exactly
        #
        # Example: 35-week loan → 1 + 35 = 36 LoanRec rows total
        #
        outstanding = loan_amount

        # ── ROW 0: Loan-taken / disbursement record ───────────────────────
        cursor.execute("""
            INSERT INTO LoanRec (
                loanid, member_code, duedate,
                principaldueamount, interestdueamount,
                principalpaidamount, interestpaidamount,
                savingsdueamount, savingspaidamount,
                additionalsavingsdueamount, additionalsavingspaidamount,
                paid, preemideducted, recordversion,
                createdby, createddate,
                modifiedby, modifieddate,
                advancerecovery, emisequence
            )
            VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, ?, GETDATE(), ?, GETDATE(), 0, 0)
        """, (
            loan_id,
            member_code,
            disb_date,            # duedate  = loan disbursement date
            float(loan_amount),   # principaldueamount = full loan amount disbursed
            user_id,
            user_id,
        ))

        # ── ROWS 1 … tenure: EMI schedule ────────────────────────────────
        for emi_number in range(1, tenure + 1):

            # ── Due date calculation ──────────────────────────────────────
            if is_weekly:
                # Strictly: disbursal + n * 7 days
                due_date = disb_date + timedelta(days=emi_number * 7)
            else:
                # Monthly: same collection_day each month, n months ahead
                target_day = int(collection_day) if collection_day else 15
                due_date   = add_months(disb_date, emi_number, target_day)

            # ── EMI split: interest first, then principal ─────────────────
            int_amt = (outstanding * period_rate).quantize(
                Decimal('0.01'), ROUND_HALF_UP)

            if emi_number == tenure:
                # ── LAST EMI: exact closing ───────────────────────────────
                # Principal = full remaining outstanding
                # Interest  = interest on remaining balance
                # EMI for this row = principal + interest (may differ from rounded EMI)
                prin_amt    = outstanding
                # int_amt already computed above on remaining balance
                last_emi    = prin_amt + int_amt
            else:
                # Regular EMI: principal = rounded_emi − interest
                prin_amt = emi - int_amt
                if prin_amt <= Decimal('0'):
                    prin_amt = Decimal('0.01')
                if prin_amt > outstanding:
                    prin_amt = outstanding
                last_emi = emi   # not used below; just for clarity

            cursor.execute("""
                INSERT INTO LoanRec (
                    loanid, member_code, duedate,
                    principaldueamount, interestdueamount,
                    principalpaidamount, interestpaidamount,
                    savingsdueamount, savingspaidamount,
                    additionalsavingsdueamount, additionalsavingspaidamount,
                    paid, preemideducted, recordversion,
                    createdby, createddate,
                    modifiedby, modifieddate,
                    advancerecovery, emisequence
                )
                VALUES (?, ?, ?, ?, ?, 0, 0, ?, 0, ?, 0, 0, 0, 1, ?, GETDATE(), ?, GETDATE(), 0, ?)
            """, (
                loan_id,
                member_code,
                due_date,
                float(prin_amt),
                float(int_amt),
                float(savings_per_emi),          # savingsdueamount  (auto from product %)
                float(addl_savings_per_emi),      # additionalsavingsdueamount (manual ₹ entry)
                user_id,
                user_id,
                emi_number,
            ))

            outstanding -= prin_amt

        # ── 3. UPDATE LoanApplication status ─────────────────────────────
        cursor.execute("""
            UPDATE LoanApplication
            SET ApplicationStatus = 'Disbursed',
                DisbursementDate  = ?,
                ModifiedBy        = ?,
                ModifiedDate      = GETDATE()
            WHERE LoanApplicationID = ?
        """, (disb_date, str(user_id), app_id))

        conn.commit()
        conn.close()

        weekdays = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        freq_txt = "weekly" if is_weekly else "monthly"
        if is_weekly:
            # EMI #1 = disbursement + 7 days
            first_due = disb_date + timedelta(days=7)
            coll_txt  = f"every 7 days from {disb_date.strftime('%d %b %Y')} (first due {first_due.strftime('%d %b')})"
        else:
            target_day = int(collection_day) if collection_day else 15
            coll_txt   = f"{target_day}th of every month"

        logger.info(f"Loan {loan_id} disbursed ({freq_txt}) for App #{app_id}")
        flash(
            f"Loan disbursed! Loan ID: #{loan_id} | "
            f"{tenure} {freq_txt} EMIs | EMI: ₹{float(emi):,.0f} | "
            f"Collection: {coll_txt}",
            "success"
        )
        return redirect(url_for("loans.index"))

    except Exception as e:
        logger.error(f"Disbursement error: {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
        flash(f"Disbursement failed: {str(e)}", "danger")
        return redirect(url_for("loans.index"))


# ─── View loan details ─────────────────────────────────────────────────────

@loans_bp.route("/view/<int:loan_id>", methods=["GET"])
@login_required
def view_loan(loan_id):
    """View loan details and EMI schedule."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                L.loanid,               -- [0]
                L.member_code,          -- [1]
                M.full_name,            -- [2]
                M.phone1,               -- [3]
                C.center_name,          -- [4]
                L.loanamount,           -- [5]
                L.interestrate,         -- [6]
                L.tenure,               -- [7]
                L.emi,                  -- [8]
                L.principaloutstanding, -- [9]
                L.interestoutstanding,  -- [10]
                L.loanstatus,           -- [11]
                L.disbursementdate,     -- [12]
                LP.ProductName,         -- [13]
                LP.PaymentFrequency,    -- [14]
                L.processingfee,        -- [15]
                L.memberinsurancefee,   -- [16]
                L.nomineeinsurancefee,  -- [17]
                L.savingsdueamount,     -- [18]
                L.securitydepositamount -- [19]
            FROM Loans L
            LEFT JOIN Members M  ON L.member_code = M.member_code
            LEFT JOIN Center  C  ON M.center_id   = C.id
            LEFT JOIN LoanProduct LP ON L.productid = LP.ProductID
            WHERE L.loanid = ?
        """, (loan_id,))
        loan = cursor.fetchone()

        if not loan:
            flash("Loan not found.", "warning")
            return redirect(url_for("loans.index"))

        cursor.execute("""
            SELECT
                loanrecid,              -- [0]
                duedate,                -- [1]
                principaldueamount,     -- [2]
                interestdueamount,      -- [3]
                principalpaidamount,    -- [4]
                interestpaidamount,     -- [5]
                savingsdueamount,       -- [6]
                savingspaidamount,      -- [7]
                paid,                   -- [8]
                emisequence             -- [9]
            FROM LoanRec
            WHERE loanid = ?
            ORDER BY ISNULL(emisequence, 999), duedate
        """, (loan_id,))
        schedule = cursor.fetchall()
        conn.close()

        return render_template("loans_view.html", loan=loan, schedule=schedule)

    except Exception as e:
        logger.error(f"Error viewing loan {loan_id}: {e}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("loans.index"))
