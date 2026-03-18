"""
PDF Report Generators - UDLMS
All PDF generation functions in one place
"""
import pyodbc
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from datetime import datetime

from db import get_db_connection


# ==========================================================
# Helper: Build standardized PDF
# ==========================================================
def build_pdf(filename, title, headers, table_rows):
    """Standard PDF builder with headers and data rows."""
    doc = SimpleDocTemplate(filename, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    title_para = Paragraph(f"<b>{title}</b>", styles["Title"])
    elements.append(title_para)
    elements.append(Spacer(1, 12))

    data = [headers] + table_rows
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(table)
    doc.build(elements)


def run_query(cursor, query, params=()):
    """Execute query and return rows as list of dicts."""
    cursor.execute(query, params)
    cols = [col[0] for col in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append(dict(zip(cols, row)))
    return rows


# ==========================================================
# 1. FD COLLECTIONS REPORT
# ==========================================================
def generate_fdcollections(start_date, end_date, filename):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT d.FDNumber, d.MemberName, d.DepositAmount,
               c.InterestDue, c.InterestPaid, c.DepositPaid,
               c.PaidDate
        FROM FDCollections c
        JOIN FDDetails d ON c.FDDetailsId = d.Id
        WHERE CAST(c.PaidDate AS DATE) BETWEEN ? AND ?
        ORDER BY c.PaidDate
    """

    rows = run_query(cursor, query, (start_date, end_date))
    conn.close()

    headers = ["FD Number", "Member", "Deposit", "Int. Due", "Int. Paid", "Dep. Paid", "Date"]

    table_rows = [
        [
            r["FDNumber"],
            r["MemberName"],
            f"{r['DepositAmount']:.2f}",
            f"{r['InterestDue']:.2f}",
            f"{r['InterestPaid']:.2f}",
            f"{r['DepositPaid']:.2f}",
            r["PaidDate"].strftime("%Y-%m-%d") if r["PaidDate"] else "",
        ]
        for r in rows
    ]

    title = f"FD Collections Report ({start_date} → {end_date})"
    build_pdf(filename, title, headers, table_rows)


# ==========================================================
# 2. RD REPORT
# ==========================================================
def generate_rd_report(start_date, end_date, filename):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT c.RecoveryDate, m.full_name AS Member,
               c.Amount, ISNULL(c.Penalty, 0) AS Penalty,
               (c.Amount + ISNULL(c.Penalty, 0)) AS TotalPaid
        FROM RDCollections c
        JOIN Members m ON c.MemberID = m.id
        WHERE CAST(c.RecoveryDate AS DATE) BETWEEN ? AND ?
        ORDER BY c.RecoveryDate
    """

    rows = run_query(cursor, query, (start_date, end_date))
    conn.close()

    headers = ["Date", "Member", "Amount", "Penalty", "Total Paid"]

    table_rows = [
        [
            r["RecoveryDate"].strftime("%Y-%m-%d"),
            r["Member"],
            f"{r['Amount']:.2f}",
            f"{r['Penalty']:.2f}",
            f"{r['TotalPaid']:.2f}",
        ]
        for r in rows
    ]

    title = f"RD Collections Report ({start_date} → {end_date})"
    build_pdf(filename, title, headers, table_rows)


# ==========================================================
# 3. DAILY COLLECTION REPORT
# ==========================================================
def generate_daily_report(start_date, end_date, filename):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT lr.createddate AS CollectionDate,
               m.full_name AS Member,
               lr.principalpaidamount AS Principal,
               lr.interestpaidamount AS Interest,
               lr.savingspaidamount AS Savings,
               (lr.principalpaidamount + lr.interestpaidamount + lr.savingspaidamount) AS TotalPaid
        FROM LoanRec lr
        JOIN Members m ON lr.member_code = m.member_code
        WHERE CAST(lr.createddate AS DATE) BETWEEN ? AND ?
          AND (lr.principalpaidamount > 0 OR lr.interestpaidamount > 0)
        ORDER BY lr.createddate
    """

    rows = run_query(cursor, query, (start_date, end_date))
    conn.close()

    headers = ["Date", "Member", "Principal", "Interest", "Savings", "Total Paid"]

    table_rows = [
        [
            r["CollectionDate"].strftime("%Y-%m-%d") if r["CollectionDate"] else "",
            r["Member"],
            f"{r['Principal']:.2f}",
            f"{r['Interest']:.2f}",
            f"{r['Savings']:.2f}",
            f"{r['TotalPaid']:.2f}",
        ]
        for r in rows
    ]

    title = f"Daily Collection Report ({start_date} → {end_date})"
    build_pdf(filename, title, headers, table_rows)


# ==========================================================
# 4. FD ACCOUNTS REPORT
# ==========================================================
def generate_fd_report(start_date, end_date, filename):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT m.full_name AS Member, f.FDNumber,
               f.DepositAmount, f.InterestRate, f.PaymentDate,
               f.MaturityDate, f.MaturityValue
        FROM FDDetails f
        JOIN Members m ON f.MemberCode = m.member_code
        WHERE CAST(f.PaymentDate AS DATE) BETWEEN ? AND ?
        ORDER BY f.PaymentDate
    """

    rows = run_query(cursor, query, (start_date, end_date))
    conn.close()

    headers = ["Member", "FD Number", "Deposit", "Rate %", "Start Date", "Maturity Date", "Maturity Value"]

    table_rows = [
        [
            r["Member"],
            r["FDNumber"],
            f"{r['DepositAmount']:.2f}",
            f"{r['InterestRate']:.2f}",
            r["PaymentDate"].strftime("%Y-%m-%d") if r["PaymentDate"] else "",
            r["MaturityDate"].strftime("%Y-%m-%d") if r["MaturityDate"] else "",
            f"{r['MaturityValue']:.2f}",
        ]
        for r in rows
    ]

    title = f"FD Accounts Report ({start_date} → {end_date})"
    build_pdf(filename, title, headers, table_rows)


# ==========================================================
# 5. RD MONTHLY REPORT
# ==========================================================
def generate_rd_monthly_report(start_date, end_date, filename):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT c.RecoveryDate, m.full_name AS Member,
               c.Amount, ISNULL(c.Penalty,0) AS Penalty,
               (c.Amount + ISNULL(c.Penalty,0)) AS TotalPaid
        FROM RDCollections c
        JOIN Members m ON c.MemberID = m.id
        WHERE CAST(c.RecoveryDate AS DATE) BETWEEN ? AND ?
        ORDER BY c.RecoveryDate
    """

    rows = run_query(cursor, query, (start_date, end_date))
    conn.close()

    headers = ["Date", "Member", "Amount", "Penalty", "Total Paid"]

    total = sum(r["TotalPaid"] for r in rows)

    table_rows = [
        [
            r["RecoveryDate"].strftime("%Y-%m-%d"),
            r["Member"],
            f"{r['Amount']:.2f}",
            f"{r['Penalty']:.2f}",
            f"{r['TotalPaid']:.2f}",
        ]
        for r in rows
    ]

    table_rows.append(["", "", "", "Grand Total", f"{total:.2f}"])

    title = f"RD Monthly Report ({start_date} → {end_date})"
    build_pdf(filename, title, headers, table_rows)


# ==========================================================
# 6. FD INTEREST PAID REPORT
# ==========================================================
def generate_fd_interest_report(start_date, end_date, filename):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT c.PaidDate, m.full_name AS Member,
               d.FDNumber, c.InterestDue, c.InterestPaid
        FROM FDCollections c
        JOIN FDDetails d ON c.FDDetailsId = d.Id
        JOIN Members m ON d.MemberCode = m.member_code
        WHERE CAST(c.PaidDate AS DATE) BETWEEN ? AND ?
          AND c.InterestPaid > 0
        ORDER BY c.PaidDate
    """

    rows = run_query(cursor, query, (start_date, end_date))
    conn.close()

    headers = ["Payment Date", "Member", "FD Number", "Interest Due", "Interest Paid"]

    total = sum(r["InterestPaid"] for r in rows)

    table_rows = [
        [
            r["PaidDate"].strftime("%Y-%m-%d") if r["PaidDate"] else "",
            r["Member"],
            r["FDNumber"],
            f"{r['InterestDue']:.2f}",
            f"{r['InterestPaid']:.2f}",
        ]
        for r in rows
    ]

    table_rows.append(["", "", "", "Total", f"{total:.2f}"])

    title = f"FD Interest Paid Report ({start_date} → {end_date})"
    build_pdf(filename, title, headers, table_rows)


# ==========================================================
# 7. GLANCE SUMMARY REPORT
# ==========================================================
def generate_glance_report(start_date, end_date, filename):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            CAST(d.DayendDate AS DATE)   AS ReportDate,
            (SELECT COUNT(*) FROM Members
             WHERE status = 'ACTIVE')    AS TotalMembers,
            (SELECT COUNT(*) FROM Loans
             WHERE loanstatus = 'Active') AS ActiveLoans,
            (SELECT COUNT(*) FROM RecurringDeposit
             WHERE Status = 'Active')    AS ActiveRDs,
            (SELECT COUNT(*) FROM FDDetails
             WHERE WithdrawDate IS NULL)  AS ActiveFDs
        FROM Dayend d
        WHERE CAST(d.DayendDate AS DATE) BETWEEN ? AND ?
        ORDER BY d.DayendDate
    """

    rows = run_query(cursor, query, (start_date, end_date))
    conn.close()

    headers = ["Date", "Members", "Loans", "RD", "FD"]

    table_rows = [
        [
            r["ReportDate"].strftime("%Y-%m-%d") if r["ReportDate"] else "",
            str(r["TotalMembers"]),
            str(r["ActiveLoans"]),
            str(r["ActiveRDs"]),
            str(r["ActiveFDs"]),
        ]
        for r in rows
    ]

    title = f"Glance Summary ({start_date} → {end_date})"
    build_pdf(filename, title, headers, table_rows)


# ==========================================================
# 8. MEMBERWISE REPORT
# ==========================================================
def generate_memberwise_report(start_date, end_date, member_id, filename):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT lr.duedate AS DueDate,
               lr.principaldueamount AS PrincipalDue,
               lr.principalpaidamount AS PrincipalPaid,
               lr.interestdueamount AS InterestDue,
               lr.interestpaidamount AS InterestPaid,
               lr.savingspaidamount AS SavingsPaid,
               CASE WHEN lr.paid = 1 THEN 'Paid' ELSE 'Pending' END AS Status
        FROM LoanRec lr
        WHERE lr.member_code = ?
          AND CAST(lr.duedate AS DATE) BETWEEN ? AND ?
        ORDER BY lr.duedate
    """

    rows = run_query(cursor, query, (member_id, start_date, end_date))
    conn.close()

    headers = ["Due Date", "Principal Due", "Principal Paid", "Interest Due", "Interest Paid", "Savings Paid", "Status"]

    table_rows = [
        [
            r["DueDate"].strftime("%Y-%m-%d") if r["DueDate"] else "",
            f"{r['PrincipalDue']:.2f}",
            f"{r['PrincipalPaid']:.2f}",
            f"{r['InterestDue']:.2f}",
            f"{r['InterestPaid']:.2f}",
            f"{r['SavingsPaid']:.2f}",
            r["Status"],
        ]
        for r in rows
    ]

    title = f"Memberwise Report (Member: {member_id}) - {start_date} → {end_date}"
    build_pdf(filename, title, headers, table_rows)


# ==========================================================
# 9. MONTHLY COLLECTION SHEET PDF - BLUE THEME
# ==========================================================
def generate_monthly_collection_pdf(due_date, branch_name, center_name, data, filename):
    """Generate PDF for monthly collection sheet - BLUE color scheme."""
    
    doc = SimpleDocTemplate(filename, pagesize=landscape(A4),
                           topMargin=0.8*cm, bottomMargin=0.8*cm,
                           leftMargin=0.8*cm, rightMargin=0.8*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=14,
                                  textColor=colors.HexColor('#0c2a78'), spaceAfter=6,
                                  alignment=TA_CENTER, fontName='Helvetica-Bold')
    
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10,
                                    alignment=TA_CENTER, spaceAfter=4)
    
    elements.append(Paragraph(f"<b>{branch_name}</b>", title_style))
    elements.append(Paragraph(f"<b>MONTHLY COLLECTION SHEET</b>", title_style))
    elements.append(Paragraph(f"Due Date: <b>{datetime.strptime(due_date, '%Y-%m-%d').strftime('%d-%b-%Y')}</b> | Center: <b>{center_name}</b>", subtitle_style))
    elements.append(Spacer(1, 0.3*cm))
    
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
            totals[i] += float(row[6+i])
    
    table_data.append(['', '', '', '', '', 'TOTAL'] + 
                     [f"₹{t:,.0f}" for t in totals] + [''])
    
    table = Table(table_data, colWidths=[0.8*cm, 2*cm, 1.5*cm, 2.5*cm, 1.8*cm, 1.2*cm,
                                         1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm,
                                         1.5*cm, 1.5*cm, 1.2*cm])
    
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
    elements.append(Spacer(1, 0.3*cm))
    
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER)
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}", footer_style))
    
    doc.build(elements)


# ==========================================================
# 10. WEEKLY COLLECTION SHEET PDF - GREEN THEME
# ==========================================================
def generate_weekly_collection_pdf(due_date, branch_name, center_name, data, filename):
    """Generate PDF for weekly collection sheet - GREEN color scheme."""
    
    doc = SimpleDocTemplate(filename, pagesize=landscape(A4),
                           topMargin=0.8*cm, bottomMargin=0.8*cm,
                           leftMargin=0.8*cm, rightMargin=0.8*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # GREEN color scheme
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=14,
                                  textColor=colors.HexColor('#059669'), spaceAfter=6,
                                  alignment=TA_CENTER, fontName='Helvetica-Bold')
    
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10,
                                    alignment=TA_CENTER, spaceAfter=4)
    
    elements.append(Paragraph(f"<b>{branch_name}</b>", title_style))
    elements.append(Paragraph(f"<b>WEEKLY COLLECTION SHEET</b>", title_style))
    elements.append(Paragraph(f"Due Date: <b>{datetime.strptime(due_date, '%Y-%m-%d').strftime('%d-%b-%Y')}</b> | Center: <b>{center_name}</b>", subtitle_style))
    elements.append(Spacer(1, 0.3*cm))
    
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
            totals[i] += float(row[6+i])
    
    table_data.append(['', '', '', '', '', 'TOTAL'] + 
                     [f"₹{t:,.0f}" for t in totals] + [''])
    
    table = Table(table_data, colWidths=[0.8*cm, 2*cm, 1.5*cm, 2.5*cm, 1.8*cm, 1.2*cm,
                                         1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm, 1.5*cm,
                                         1.5*cm, 1.5*cm, 1.2*cm])
    
    # GREEN color scheme
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 6),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (6, 1), (-2, -1), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d1fae5')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 7),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#059669')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 0.3*cm))
    
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER)
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}", footer_style))
    
    doc.build(elements)


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
# 10. WEEKLY COLLECTION SHEET PDF - GREEN THEME
# ==========================================================
def generate_weekly_collection_pdf(due_date, branch_name, center_name, data, filename):
    """Generate PDF for weekly collection sheet - GREEN color scheme."""

    doc = SimpleDocTemplate(filename, pagesize=landscape(A4),
                            topMargin=0.8 * cm, bottomMargin=0.8 * cm,
                            leftMargin=0.8 * cm, rightMargin=0.8 * cm)

    elements = []
    styles = getSampleStyleSheet()

    # GREEN color scheme
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=14,
                                 textColor=colors.HexColor('#059669'), spaceAfter=6,
                                 alignment=TA_CENTER, fontName='Helvetica-Bold')

    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10,
                                    alignment=TA_CENTER, spaceAfter=4)

    elements.append(Paragraph(f"<b>{branch_name}</b>", title_style))
    elements.append(Paragraph(f"<b>WEEKLY COLLECTION SHEET</b>", title_style))
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

    # GREEN color scheme
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 6),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (6, 1), (-2, -1), 'RIGHT'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d1fae5')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 7),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#059669')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 0.3 * cm))

    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER)
    elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%d-%b-%Y %I:%M %p')}", footer_style))

    doc.build(elements)