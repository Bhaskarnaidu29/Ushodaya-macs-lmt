# reports.py
# ═══════════════════════════════════════════════════════════════════
# COMPLETE PROFESSIONAL REPORTS MODULE
# All 22 Reports for UDLMS - Matches Latest_Db.sql Schema
# ═══════════════════════════════════════════════════════════════════

from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for, session
from db import get_db_connection
from datetime import datetime
import pandas as pd
import io
import logging
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from datetime import datetime

from db import get_db_connection

logger = logging.getLogger(__name__)

reports_bp = Blueprint("reports", __name__, template_folder="templates")

# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def fetch_data(query, params=None):
    """Execute query and return results as list of dicts"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        
        result = [dict(zip(columns, row)) for row in rows]
        return result
    finally:
        conn.close()


def get_branch_id():
    """Get current user's branch ID from session"""
    return session.get("branchid", 1)


# ═══════════════════════════════════════════════════════════════════
# REPORTS HOME PAGE
# ═══════════════════════════════════════════════════════════════════

@reports_bp.route("/reports")
def reports_home():
    """Main reports dashboard"""
    return render_template("/reports_home.html")


# ═══════════════════════════════════════════════════════════════════
# MEMBER REPORTS (3)
# ═══════════════════════════════════════════════════════════════════

@reports_bp.route("/member_joining", methods=["GET", "POST"])
def member_joining():
    """Member Joining Report"""
    rows = []
    from_date = request.form.get("from_date") or request.args.get("from_date")
    to_date = request.form.get("to_date") or request.args.get("to_date")
    branch_id = get_branch_id()
    
    if from_date and to_date:
        query = """
            SELECT 
                m.member_code,
                m.full_name,
                m.phone1,
                m.email,
                c.center_name,
                m.join_date,
                m.aadhaar,
                m.status
            FROM Members m
            LEFT JOIN Center c ON m.center_id = c.id
            WHERE CAST(m.join_date AS DATE) BETWEEN ? AND ?
              AND m.BranchId = ?
            ORDER BY m.join_date DESC
        """
        rows = fetch_data(query, (from_date, to_date, branch_id))
    
    return render_template("reports/member_joining.html", rows=rows, from_date=from_date, to_date=to_date)


@reports_bp.route("/member_withdraw", methods=["GET", "POST"])
def member_withdraw():
    """Member Withdraw Report"""
    rows = []
    from_date = request.form.get("from_date") or request.args.get("from_date")
    to_date = request.form.get("to_date") or request.args.get("to_date")
    branch_id = get_branch_id()
    
    if from_date and to_date:
        query = """
            SELECT 
                m.member_code,
                m.full_name,
                m.phone1,
                c.center_name,
                m.status
            FROM Members m
            LEFT JOIN Center c ON m.center_id = c.id
            WHERE m.BranchId = ?
              AND m.status = 'INACTIVE'
            ORDER BY m.member_code
        """
        rows = fetch_data(query, [branch_id])
    
    return render_template("reports/member_withdraw.html", rows=rows, from_date=from_date, to_date=to_date)


@reports_bp.route("/member_details", methods=["GET", "POST"])
def member_details():
    """Member Details Report"""
    branch_id = get_branch_id()
    
    query = """
        SELECT 
            m.member_code,
            m.full_name,
            m.phone1,
            m.email,
            c.center_name,
            m.join_date,
            m.status
        FROM Members m
        LEFT JOIN Center c ON m.center_id = c.id
        WHERE m.BranchId = ? AND m.status = 'ACTIVE'
        ORDER BY c.center_name, m.full_name
    """
    rows = fetch_data(query, [branch_id])
    
    return render_template("reports/member_details.html", rows=rows)


# ═══════════════════════════════════════════════════════════════════
# LOAN REPORTS (5)
# ═══════════════════════════════════════════════════════════════════

@reports_bp.route("/loan_ledger", methods=["GET", "POST"])
def loan_ledger():
    """Loan Ledger"""
    rows = []
    loanid = request.form.get("loanid") or request.args.get("loanid")
    
    if loanid:
        query = """
            SELECT
                lr.duedate,
                lr.principaldueamount,
                lr.principalpaidamount,
                lr.interestdueamount,
                lr.interestpaidamount,
                lr.savingsdueamount,
                lr.savingspaidamount,
                CASE WHEN lr.paid = 1 THEN 'Paid' ELSE 'Pending' END AS status
            FROM LoanRec lr
            WHERE lr.loanid = ?
            ORDER BY lr.duedate
        """
        rows = fetch_data(query, [loanid])
    
    return render_template("reports/loan_ledger.html", rows=rows, loanid=loanid)


@reports_bp.route("/member_loan_ledger", methods=["GET", "POST"])
def member_loan_ledger():
    """Member Loan Ledger"""
    rows = []
    member_code = request.form.get("member_code") or request.args.get("member_code")
    
    if member_code:
        query = """
            SELECT
                l.loanid,
                l.loanamount,
                l.disbursementdate AS loandate,
                l.tenure,
                l.loanstatus,
                l.principaloutstanding,
                l.interestoutstanding
            FROM Loans l
            WHERE l.member_code = ?
            ORDER BY l.disbursementdate DESC
        """
        rows = fetch_data(query, [member_code])
    
    return render_template("reports/member_loan_ledger.html", rows=rows, member_code=member_code)


@reports_bp.route("/arrear_details", methods=["GET", "POST"])
def arrear_details():
    """Arrear Details"""
    branch_id = get_branch_id()
    
    query = """
        SELECT
            m.member_code,
            m.full_name,
            c.center_name,
            l.loanid,
            lr.duedate,
            DATEDIFF(DAY, lr.duedate, GETDATE()) AS days_overdue,
            (ISNULL(lr.principaldueamount, 0) - ISNULL(lr.principalpaidamount, 0)) AS principal_arrear,
            (ISNULL(lr.interestdueamount, 0) - ISNULL(lr.interestpaidamount, 0)) AS interest_arrear,
            (ISNULL(lr.principaldueamount, 0) + ISNULL(lr.interestdueamount, 0) 
             - ISNULL(lr.principalpaidamount, 0) - ISNULL(lr.interestpaidamount, 0)) AS total_arrear
        FROM LoanRec lr
        JOIN Loans l ON lr.loanid = l.loanid
        JOIN Members m ON l.member_code = m.member_code
        LEFT JOIN Center c ON m.center_id = c.id
        WHERE lr.paid = 0
          AND lr.duedate < CAST(GETDATE() AS DATE)
          AND l.branchid = ?
          AND l.loanstatus = 'Active'
        ORDER BY lr.duedate, c.center_name
    """
    rows = fetch_data(query, [branch_id])
    
    return render_template("reports/arrear_details.html", rows=rows)


@reports_bp.route("/member_outstanding", methods=["GET", "POST"])
def member_outstanding():
    """Member Outstanding"""
    branch_id = get_branch_id()
    
    query = """
        SELECT
            m.member_code,
            m.full_name,
            c.center_name,
            SUM(l.principaloutstanding) AS principal_outstanding,
            SUM(l.interestoutstanding) AS interest_outstanding,
            SUM(l.principaloutstanding + l.interestoutstanding) AS total_outstanding
        FROM Members m
        LEFT JOIN Center c ON m.center_id = c.id
        LEFT JOIN Loans l ON m.member_code = l.member_code AND l.loanstatus = 'Active'
        WHERE m.BranchId = ? AND m.status = 'ACTIVE'
        GROUP BY m.member_code, m.full_name, c.center_name
        HAVING SUM(l.principaloutstanding) > 0
        ORDER BY c.center_name, m.full_name
    """
    rows = fetch_data(query, [branch_id])
    
    return render_template("reports/member_outstanding.html", rows=rows)


@reports_bp.route("/center_outstanding", methods=["GET", "POST"])
def center_outstanding():
    """Center Outstanding"""
    branch_id = get_branch_id()
    
    query = """
        SELECT
            c.center_name,
            COUNT(DISTINCT m.member_code) AS total_members,
            SUM(l.principaloutstanding) AS principal_outstanding,
            SUM(l.interestoutstanding) AS interest_outstanding,
            SUM(l.principaloutstanding + l.interestoutstanding) AS total_outstanding
        FROM Center c
        LEFT JOIN Members m ON c.id = m.center_id AND m.status = 'ACTIVE'
        LEFT JOIN Loans l ON m.member_code = l.member_code AND l.loanstatus = 'Active'
        WHERE c.branchid = ?
        GROUP BY c.center_name
        ORDER BY c.center_name
    """
    rows = fetch_data(query, [branch_id])
    
    return render_template("reports/center_outstanding.html", rows=rows)


# ═══════════════════════════════════════════════════════════════════
# COLLECTION REPORTS (4)
# ═══════════════════════════════════════════════════════════════════

@reports_bp.route("/daily_collection", methods=["GET", "POST"])
def daily_collection():
    """Daily Collection"""
    rows = []
    from_date = request.form.get("from_date") or request.args.get("from_date")
    to_date = request.form.get("to_date") or request.args.get("to_date")
    branch_id = get_branch_id()
    
    if from_date and to_date:
        query = """
            SELECT
                lr.createddate,
                m.full_name,
                c.center_name,
                l.loanid,
                lr.principalpaidamount,
                lr.interestpaidamount,
                lr.savingspaidamount,
                (lr.principalpaidamount + lr.interestpaidamount + lr.savingspaidamount) AS total
            FROM LoanRec lr
            JOIN Loans l ON lr.loanid = l.loanid
            JOIN Members m ON l.member_code = m.member_code
            LEFT JOIN Center c ON m.center_id = c.id
            WHERE CAST(lr.createddate AS DATE) BETWEEN ? AND ?
              AND (lr.principalpaidamount > 0 OR lr.interestpaidamount > 0 OR lr.savingspaidamount > 0)
              AND l.branchid = ?
            ORDER BY lr.createddate, c.center_name
        """
        rows = fetch_data(query, (from_date, to_date, branch_id))
    
    return render_template("reports/daily_collection.html", rows=rows, from_date=from_date, to_date=to_date)


@reports_bp.route("/weekly_collection", methods=["GET", "POST"])
def weekly_collection():
    """Weekly Collection"""
    rows = []
    due_date = request.form.get("due_date") or request.args.get("due_date")
    branch_id = get_branch_id()
    
    if due_date:
        query = """
            SELECT
                m.member_code,
                m.full_name,
                c.center_name,
                l.loanid,
                lr.principaldueamount,
                lr.principalpaidamount,
                lr.interestdueamount,
                lr.interestpaidamount,
                lr.savingsdueamount,
                lr.savingspaidamount,
                CASE WHEN lr.paid = 1 THEN 'Paid' ELSE 'Pending' END AS status
            FROM LoanRec lr
            JOIN Loans l ON lr.loanid = l.loanid
            JOIN Members m ON l.member_code = m.member_code
            LEFT JOIN Center c ON m.center_id = c.id
            JOIN LoanProduct lp ON l.productid = lp.ProductID
            WHERE CAST(lr.duedate AS DATE) = ?
              AND lp.PaymentFrequency = 'Weekly'
              AND l.branchid = ?
            ORDER BY c.center_name, m.full_name
        """
        rows = fetch_data(query, (due_date, branch_id))
    
    return render_template("reports/weekly_collection.html", rows=rows, due_date=due_date)


@reports_bp.route("/monthly_collection", methods=["GET", "POST"])
def monthly_collection():
    """Monthly Collection"""
    rows = []
    due_date = request.form.get("due_date") or request.args.get("due_date")
    branch_id = get_branch_id()
    
    if due_date:
        query = """
            SELECT
                m.member_code,
                m.full_name,
                c.center_name,
                l.loanid,
                lr.principaldueamount,
                lr.principalpaidamount,
                lr.interestdueamount,
                lr.interestpaidamount,
                lr.savingsdueamount,
                lr.savingspaidamount,
                CASE WHEN lr.paid = 1 THEN 'Paid' ELSE 'Pending' END AS status
            FROM LoanRec lr
            JOIN Loans l ON lr.loanid = l.loanid
            JOIN Members m ON l.member_code = m.member_code
            LEFT JOIN Center c ON m.center_id = c.id
            JOIN LoanProduct lp ON l.productid = lp.ProductID
            WHERE CAST(lr.duedate AS DATE) = ?
              AND lp.PaymentFrequency = 'Monthly'
              AND l.branchid = ?
            ORDER BY c.center_name, m.full_name
        """
        rows = fetch_data(query, (due_date, branch_id))
    
    return render_template("reports/monthly_collection.html", rows=rows, due_date=due_date)


@reports_bp.route("/arrears_collected", methods=["GET", "POST"])
def arrears_collected():
    """Arrears Collected"""
    rows = []
    from_date = request.form.get("from_date") or request.args.get("from_date")
    to_date = request.form.get("to_date") or request.args.get("to_date")
    branch_id = get_branch_id()
    
    if from_date and to_date:
        query = """
            SELECT
                lr.createddate,
                m.full_name,
                c.center_name,
                l.loanid,
                lr.duedate,
                DATEDIFF(DAY, lr.duedate, lr.createddate) AS days_late,
                lr.principalpaidamount,
                lr.interestpaidamount,
                (lr.principalpaidamount + lr.interestpaidamount) AS total
            FROM LoanRec lr
            JOIN Loans l ON lr.loanid = l.loanid
            JOIN Members m ON l.member_code = m.member_code
            LEFT JOIN Center c ON m.center_id = c.id
            WHERE CAST(lr.createddate AS DATE) BETWEEN ? AND ?
              AND lr.duedate < lr.createddate
              AND (lr.principalpaidamount > 0 OR lr.interestpaidamount > 0)
              AND l.branchid = ?
            ORDER BY lr.createddate
        """
        rows = fetch_data(query, (from_date, to_date, branch_id))
    
    return render_template("reports/arrears_collected.html", rows=rows, from_date=from_date, to_date=to_date)


# ═══════════════════════════════════════════════════════════════════
# ADVANCE REPORTS (2)
# ═══════════════════════════════════════════════════════════════════

@reports_bp.route("/advance_collected", methods=["GET", "POST"])
def advance_collected():
    """Advance Collected"""
    rows = []
    from_date = request.form.get("from_date") or request.args.get("from_date")
    to_date = request.form.get("to_date") or request.args.get("to_date")
    branch_id = get_branch_id()
    
    if from_date and to_date:
        query = """
            SELECT
                ar.transactiondate,
                m.full_name,
                ar.loanid,
                ar.amount,
                ar.notes
            FROM AdvanceRecovery ar
            JOIN Members m ON ar.member_code = m.id
            WHERE CAST(ar.transactiondate AS DATE) BETWEEN ? AND ?
              AND ar.creditdebit = 'Credit'
            ORDER BY ar.transactiondate
        """
        rows = fetch_data(query, (from_date, to_date))
    
    return render_template("reports/advance_collected.html", rows=rows, from_date=from_date, to_date=to_date)


@reports_bp.route("/advance_withdraw", methods=["GET", "POST"])
def advance_withdraw():
    """Advance Withdraw"""
    rows = []
    from_date = request.form.get("from_date") or request.args.get("from_date")
    to_date = request.form.get("to_date") or request.args.get("to_date")
    
    if from_date and to_date:
        query = """
            SELECT
                ar.transactiondate,
                m.full_name,
                ar.loanid,
                ar.amount,
                ar.notes
            FROM AdvanceRecovery ar
            JOIN Members m ON ar.member_code = m.id
            WHERE CAST(ar.transactiondate AS DATE) BETWEEN ? AND ?
              AND ar.creditdebit = 'Debit'
            ORDER BY ar.transactiondate
        """
        rows = fetch_data(query, (from_date, to_date))
    
    return render_template("reports/advance_withdraw.html", rows=rows, from_date=from_date, to_date=to_date)


# ═══════════════════════════════════════════════════════════════════
# DEPOSIT REPORTS (3)
# ═══════════════════════════════════════════════════════════════════

@reports_bp.route("/security_deposit_collected", methods=["GET", "POST"])
def security_deposit_collected():
    """Security Deposit Collected"""
    rows = []
    from_date = request.form.get("from_date") or request.args.get("from_date")
    to_date = request.form.get("to_date") or request.args.get("to_date")
    branch_id = get_branch_id()
    
    if from_date and to_date:
        query = """
            SELECT
                l.disbursementdate,
                m.full_name,
                l.loanid,
                l.securitydepositamount AS amount
            FROM Loans l
            JOIN Members m ON l.member_code = m.member_code
            WHERE CAST(l.disbursementdate AS DATE) BETWEEN ? AND ?
              AND l.securitydepositamount > 0
              AND l.branchid = ?
            ORDER BY l.disbursementdate
        """
        rows = fetch_data(query, (from_date, to_date, branch_id))
    
    return render_template("reports/security_deposit_collected.html", rows=rows, from_date=from_date, to_date=to_date)


@reports_bp.route("/security_deposit_withdraw", methods=["GET", "POST"])
def security_deposit_withdraw():
    """Security Deposit Withdraw"""
    rows = []
    from_date = request.form.get("from_date") or request.args.get("from_date")
    to_date = request.form.get("to_date") or request.args.get("to_date")
    branch_id = get_branch_id()
    
    if from_date and to_date:
        query = """
            SELECT
                l.disbursementdate,
                m.full_name,
                l.loanid,
                l.securitydepositwithdrawn AS amount
            FROM Loans l
            JOIN Members m ON l.member_code = m.member_code
            WHERE l.securitydepositwithdrawn > 0
              AND l.branchid = ?
            ORDER BY l.disbursementdate DESC
        """
        rows = fetch_data(query, [branch_id])
    
    return render_template("reports/security_deposit_withdraw.html", rows=rows, from_date=from_date, to_date=to_date)


@reports_bp.route("/sd_withdraw-receipt", methods=["GET", "POST"])
def sd_withdraw_receipt():
    """SD Withdraw Receipt"""
    loanid = request.args.get("loanid")
    receipt = {}
    
    if loanid:
        query = """
            SELECT
                m.full_name,
                l.loanid,
                l.securitydepositwithdrawn AS amount,
                GETDATE() AS date
            FROM Loans l
            JOIN Members m ON l.member_code = m.member_code
            WHERE l.loanid = ?
        """
        result = fetch_data(query, [loanid])
        if result:
            receipt = result[0]
    
    return render_template("reports/sd_withdraw_receipt.html", receipt=receipt)


# ═══════════════════════════════════════════════════════════════════
# FINANCIAL REPORTS (3)
# ═══════════════════════════════════════════════════════════════════

@reports_bp.route("/center_summary", methods=["GET", "POST"])
def center_summary():
    """Center Summary"""
    rows = []
    center_id = request.form.get("center_id") or request.args.get("center_id")
    
    if center_id:
        query = """
            SELECT
                c.center_name,
                COUNT(DISTINCT m.member_code) AS total_members,
                COUNT(DISTINCT l.loanid) AS total_loans,
                SUM(l.loanamount) AS total_loan_amount,
                SUM(l.principaloutstanding) AS principal_outstanding,
                SUM(l.interestoutstanding) AS interest_outstanding
            FROM Center c
            LEFT JOIN Members m ON c.id = m.center_id
            LEFT JOIN Loans l ON m.member_code = l.member_code
            WHERE c.id = ?
            GROUP BY c.center_name
        """
        rows = fetch_data(query, [center_id])
    
    return render_template("reports/center_summary.html", rows=rows, center_id=center_id)


@reports_bp.route("/member_summary", methods=["GET", "POST"])
def member_summary():
    """Member Summary"""
    rows = []
    member_code = request.form.get("member_code") or request.args.get("member_code")
    
    if member_code:
        query = """
            SELECT
                m.member_code,
                m.full_name,
                c.center_name,
                COUNT(l.loanid) AS total_loans,
                SUM(l.loanamount) AS total_loan_amount,
                SUM(l.principaloutstanding) AS principal_outstanding,
                SUM(l.interestoutstanding) AS interest_outstanding
            FROM Members m
            LEFT JOIN Center c ON m.center_id = c.id
            LEFT JOIN Loans l ON m.member_code = l.member_code
            WHERE m.member_code = ?
            GROUP BY m.member_code, m.full_name, c.center_name
        """
        rows = fetch_data(query, [member_code])
    
    return render_template("reports/member_summary.html", rows=rows, member_code=member_code)


@reports_bp.route("/glance_report", methods=["GET", "POST"])
def glance_report():
    """Glance Report"""
    branch_id = get_branch_id()
    
    query = """
        SELECT
            (SELECT COUNT(*) FROM Members WHERE BranchId = ? AND status = 'ACTIVE') AS total_members,
            (SELECT COUNT(*) FROM Center WHERE branchid = ?) AS total_centers,
            (SELECT COUNT(*) FROM Loans WHERE branchid = ? AND loanstatus = 'Active') AS active_loans,
            (SELECT SUM(loanamount) FROM Loans WHERE branchid = ? AND loanstatus = 'Active') AS total_loan_amount,
            (SELECT SUM(principaloutstanding) FROM Loans WHERE branchid = ? AND loanstatus = 'Active') AS principal_outstanding,
            (SELECT SUM(interestoutstanding) FROM Loans WHERE branchid = ? AND loanstatus = 'Active') AS interest_outstanding
    """
    
    params = [branch_id] * 6
    rows = fetch_data(query, params)
    
    return render_template("reports/glance_report.html", rows=rows)


# ═══════════════════════════════════════════════════════════════════
# PASSBOOK REPORTS (2)
# ═══════════════════════════════════════════════════════════════════

@reports_bp.route("/loan_passbook", methods=["GET", "POST"])
def loan_passbook():
    """Loan Passbook"""
    rows = []
    loanid = request.form.get("loanid") or request.args.get("loanid")
    
    if loanid:
        query = """
            SELECT
                lr.duedate,
                lr.principaldueamount,
                lr.principalpaidamount,
                lr.interestdueamount,
                lr.interestpaidamount,
                lr.savingsdueamount,
                lr.savingspaidamount,
                (lr.principalpaidamount + lr.interestpaidamount + lr.savingspaidamount) AS total_paid,
                CASE WHEN lr.paid = 1 THEN 'Paid' ELSE 'Pending' END AS status
            FROM LoanRec lr
            WHERE lr.loanid = ?
            ORDER BY lr.duedate
        """
        rows = fetch_data(query, [loanid])
    
    return render_template("reports/loan_passbook.html", rows=rows, loanid=loanid)


@reports_bp.route("/savings_passbook", methods=["GET", "POST"])
def savings_passbook():
    """Savings Passbook"""
    rows = []
    member_code = request.form.get("member_code") or request.args.get("member_code")
    
    if member_code:
        query = """
            SELECT
                lr.duedate,
                lr.savingsdueamount,
                lr.savingspaidamount,
                lr.additionalsavingspaidamount,
                SUM(lr.savingspaidamount) OVER (ORDER BY lr.duedate) AS balance
            FROM LoanRec lr
            JOIN Loans l ON lr.loanid = l.loanid
            WHERE l.member_code = ?
            ORDER BY lr.duedate
        """
        rows = fetch_data(query, [member_code])
    
    return render_template("reports/savings_passbook.html", rows=rows, member_code=member_code)


# ==========================================================
# 9. MONTHLY COLLECTION SHEET PDF - BLUE THEME
# ==========================================================
def generate_monthly_collection_pdf(due_date, branch_name, center_name, data, filename):
    """Generate PDF for monthly collection sheet - BLUE color scheme."""

    doc = SimpleDocTemplate(filename, pagesize=landscape(A4),
                            topMargin=0.8 * cm, bottomMargin=0.8 * cm,
                            leftMargin=0.8 * cm, rightMargin=0.8 * cm)

    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=14,
                                 textColor=colors.HexColor('#0c2a78'), spaceAfter=6,
                                 alignment=TA_CENTER, fontName='Helvetica-Bold')

    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10,
                                    alignment=TA_CENTER, spaceAfter=4)

    elements.append(Paragraph(f"<b>{branch_name}</b>", title_style))
    elements.append(Paragraph(f"<b>MONTHLY COLLECTION SHEET</b>", title_style))
    elements.append(Paragraph(
        f"Due Date: <b>{datetime.strptime(due_date, '%Y-%m-%d').strftime('%d-%b-%Y')}</b> | Center: <b>{center_name}</b>",
        subtitle_style))
    elements.append(Spacer(1, 0.3 * cm))

    table_data = [
        ['S.No', 'Center', 'Member\nCode', 'Member Name', 'Mobile', 'Loan\nID',
         'Principal\nDue', 'Interest\nDue', 'Savings\nDue', 'Total\nDue',
         'Principal\nPaid', 'Interest\nPaid', 'Savings\nPaid', 'Total\nPaid', 'Status']
    ]

    totals = [0] * 8

    for row in data:
        table_data.append([
            str(row[0]),
            str(row[1])[:12],
            str(row[2]),
            str(row[3])[:18],
            str(row[4] or '')[:10],
            str(row[5]),
            f"₹{float(row[6]):,.0f}",
            f"₹{float(row[7]):,.0f}",
            f"₹{float(row[8]):,.0f}",
            f"₹{float(row[9]):,.0f}",
            f"₹{float(row[10]):,.0f}",
            f"₹{float(row[11]):,.0f}",
            f"₹{float(row[12]):,.0f}",
            f"₹{float(row[13]):,.0f}",
            str(row[14])[:7]
        ])

        for i in range(8):
            totals[i] += float(row[6 + i])

    table_data.append(['', '', '', '', '', 'TOTAL'] +
                      [f"₹{t:,.0f}" for t in totals] + [''])

    table = Table(table_data, colWidths=[0.8 * cm, 2 * cm, 1.5 * cm, 2.5 * cm, 1.8 * cm, 1.2 * cm,
                                         1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm,
                                         1.5 * cm, 1.5 * cm, 1.2 * cm])

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0c2a78')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 6),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (6, 1), (-2, -1), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f4f8')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 7),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#0c2a78')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 0.3 * cm))

    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER)
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}", footer_style))

    doc.build(elements)


# ==========================================================
# WEEKLY COLLECTION PDF - GROUP WISE (CENTER WISE)
# ==========================================================

from collections import defaultdict

def generate_weekly_collection_pdf(due_date, branch_name, center_name, data, filename):

    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from datetime import datetime

    doc = SimpleDocTemplate(filename, pagesize=landscape(A4),
                            topMargin=1*cm, bottomMargin=1*cm,
                            leftMargin=1*cm, rightMargin=1*cm)

    elements=[]
    styles=getSampleStyleSheet()

    # HEADER
    title=ParagraphStyle('title',parent=styles['Heading1'],
                         fontSize=16,
                         alignment=TA_CENTER,
                         textColor=colors.HexColor('#059669'))

    elements.append(Paragraph(branch_name,title))
    elements.append(Paragraph("WEEKLY COLLECTION SHEET",title))

    elements.append(Paragraph(
        f"Due Date: {datetime.strptime(due_date,'%Y-%m-%d').strftime('%d-%b-%Y')}",
        styles['Normal']
    ))

    elements.append(Spacer(1,0.5*cm))

    # -------------------------------------------------------
    # GROUP DATA BY CENTER
    # -------------------------------------------------------

    grouped=defaultdict(list)

    for row in data:
        grouped[row[1]].append(row)

    grand_totals=[0]*8


    # -------------------------------------------------------
    # LOOP CENTERS
    # -------------------------------------------------------

    for center,rows in grouped.items():

        elements.append(Spacer(1,0.3*cm))

        center_style=ParagraphStyle(
            'center',
            parent=styles['Heading3'],
            textColor=colors.HexColor('#065f46')
        )

        elements.append(Paragraph(f"CENTER : {center}",center_style))

        table_data=[[
            'S.No','Member Code','Member Name','Mobile','Loan ID',
            'Principal Due','Interest Due','Savings Due','Total Due',
            'Principal Paid','Interest Paid','Savings Paid','Total Paid','Status'
        ]]

        center_totals=[0]*8

        for row in rows:

            p_due=float(row[6] or 0)
            i_due=float(row[7] or 0)
            s_due=float(row[8] or 0)
            t_due=float(row[9] or 0)

            p_paid=float(row[10] or 0)
            i_paid=float(row[11] or 0)
            s_paid=float(row[12] or 0)
            t_paid=float(row[13] or 0)

            table_data.append([
                row[0],
                row[2],
                row[3],
                row[4] or '',
                row[5],
                f"{p_due:,.0f}",
                f"{i_due:,.0f}",
                f"{s_due:,.0f}",
                f"{t_due:,.0f}",
                f"{p_paid:,.0f}",
                f"{i_paid:,.0f}",
                f"{s_paid:,.0f}",
                f"{t_paid:,.0f}",
                row[14]
            ])

            values=[p_due,i_due,s_due,t_due,p_paid,i_paid,s_paid,t_paid]

            for i,v in enumerate(values):
                center_totals[i]+=v
                grand_totals[i]+=v


        # CENTER TOTAL ROW

        table_data.append([
            '','','','CENTER TOTAL','',
            f"{center_totals[0]:,.0f}",
            f"{center_totals[1]:,.0f}",
            f"{center_totals[2]:,.0f}",
            f"{center_totals[3]:,.0f}",
            f"{center_totals[4]:,.0f}",
            f"{center_totals[5]:,.0f}",
            f"{center_totals[6]:,.0f}",
            f"{center_totals[7]:,.0f}",
            ''
        ])

        table=Table(table_data,repeatRows=1)

        table.setStyle(TableStyle([

            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#059669')),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),

            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('ALIGN',(0,0),(-1,0),'CENTER'),

            ('FONTSIZE',(0,0),(-1,0),8),
            ('FONTSIZE',(0,1),(-1,-1),7),

            ('GRID',(0,0),(-1,-1),0.4,colors.grey),

            ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#d1fae5')),
            ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold')

        ]))

        elements.append(table)



    # -------------------------------------------------------
    # GRAND TOTAL
    # -------------------------------------------------------

    elements.append(Spacer(1,0.6*cm))

    total_table=Table([[
        "GRAND TOTAL",
        f"{grand_totals[0]:,.0f}",
        f"{grand_totals[1]:,.0f}",
        f"{grand_totals[2]:,.0f}",
        f"{grand_totals[3]:,.0f}",
        f"{grand_totals[4]:,.0f}",
        f"{grand_totals[5]:,.0f}",
        f"{grand_totals[6]:,.0f}",
        f"{grand_totals[7]:,.0f}"
    ]])

    total_table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#059669')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold')
    ]))

    elements.append(total_table)

    doc.build(elements)