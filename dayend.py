# dayend.py - Day End Module with Pending Recovery Check
# ✅ CORRECTED VERSION - Uses Branches table (not Branch)

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from datetime import datetime
from decimal import Decimal

dayend_bp = Blueprint("dayend", __name__, template_folder="templates")


def get_last_dayend(branchid):
    """Get last dayend date for branch."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 1 DayendDate, Id
            FROM Dayend
            WHERE BranchId = ?
            ORDER BY DayendDate DESC
        """, (branchid,))
        row = cursor.fetchone()
        return row if row else None
    finally:
        conn.close()


def get_pending_recoveries(branchid):
    """
    Get all pending recoveries that block dayend.
    Returns list of (center_name, member_code, member_name, emi#, due_date, amounts)
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Get last dayend date
        last_dayend = get_last_dayend(branchid)
        check_date = last_dayend[0] if last_dayend else datetime(2020, 1, 1)
        
        # Get all unpaid EMIs with duedate <= today
        cursor.execute("""
            SELECT 
                c.center_name,                          -- [0]
                c.center_no,                            -- [1]
                m.member_code,                          -- [2]
                m.full_name,                            -- [3]
                l.loanid,                               -- [4]
                lr.loanrecid,                           -- [5]
                lr.emisequence,                         -- [6]
                lr.duedate,                             -- [7]
                lr.principaldueamount,                  -- [8]
                lr.interestdueamount,                   -- [9]
                lr.savingsdueamount,                    -- [10]
                ISNULL(lr.principalpaidamount, 0),      -- [11]
                ISNULL(lr.interestpaidamount, 0),       -- [12]
                ISNULL(lr.savingspaidamount, 0),        -- [13]
                ISNULL(LP.ProductName, 'N/A')           -- [14]
            FROM Members m
            JOIN Center c ON m.center_id = c.id
            JOIN Loans l ON m.member_code = l.member_code
            JOIN LoanRec lr ON l.loanid = lr.loanid
            LEFT JOIN LoanProduct LP ON l.productid = LP.ProductID
            WHERE c.branchid = ?
              AND lr.paid = 0
              AND lr.emisequence > 0
              AND lr.duedate <= CAST(GETDATE() AS DATE)
              AND l.loanstatus = 'Active'
            ORDER BY c.center_name, m.full_name, lr.emisequence
        """, (branchid,))
        
        return cursor.fetchall()
    finally:
        conn.close()


@dayend_bp.route("/", methods=["GET"])
def dayend_check():
    """
    Day End Check Page
    - Shows last dayend date
    - Checks for pending recoveries
    - Blocks dayend if any pending
    """
    conn = get_db_connection()
    try:
        branchid = session.get("branchid", 1)
        user_id = session.get("user_id", 1)
        
        cursor = conn.cursor()
        
        # ✅ CORRECTED: Table is "Branches", column is "Name"
        cursor.execute("SELECT Name FROM Branches WHERE Id = ?", (branchid,))
        branch_row = cursor.fetchone()
        branch_name = branch_row[0] if branch_row else "Unknown Branch"
        
        # Get last dayend
        last_dayend = get_last_dayend(branchid)
        last_dayend_date = last_dayend[0] if last_dayend else None
        
        # Get pending recoveries
        pending_recoveries = get_pending_recoveries(branchid)
        
        # Group by center for better display
        centers_pending = {}
        total_pending_amount = Decimal("0.00")
        
        for rec in pending_recoveries:
            center_name = rec[0]
            principal_pending = Decimal(str(rec[8] or 0)) - Decimal(str(rec[11] or 0))
            interest_pending = Decimal(str(rec[9] or 0)) - Decimal(str(rec[12] or 0))
            savings_pending = Decimal(str(rec[10] or 0)) - Decimal(str(rec[13] or 0))
            total = principal_pending + interest_pending + savings_pending
            
            if center_name not in centers_pending:
                centers_pending[center_name] = {
                    'center_no': rec[1],
                    'members': [],
                    'total_amount': Decimal("0.00"),
                    'count': 0
                }
            
            centers_pending[center_name]['members'].append({
                'member_code': rec[2],
                'member_name': rec[3],
                'emi_sequence': rec[6],
                'due_date': rec[7],
                'principal': principal_pending,
                'interest': interest_pending,
                'savings': savings_pending,
                'total': total,
                'product': rec[14]
            })
            
            centers_pending[center_name]['total_amount'] += total
            centers_pending[center_name]['count'] += 1
            total_pending_amount += total
        
        # Can proceed with dayend?
        can_proceed = len(pending_recoveries) == 0
        
        return render_template("dayend_check.html",
                             branch_name=branch_name,
                             last_dayend_date=last_dayend_date,
                             pending_recoveries=pending_recoveries,
                             centers_pending=centers_pending,
                             total_pending_amount=total_pending_amount,
                             can_proceed=can_proceed,
                             today=datetime.now().strftime('%d %b %Y'))
    
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return render_template("dayend_check.html",
                             branch_name="Unknown",
                             last_dayend_date=None,
                             pending_recoveries=[],
                             centers_pending={},
                             total_pending_amount=0,
                             can_proceed=False,
                             today=datetime.now().strftime('%d %b %Y'))
    finally:
        conn.close()


@dayend_bp.route("/process", methods=["POST"])
def dayend_process():
    """
    Process Day End
    - Final check for pending recoveries
    - Insert dayend record
    - Show confirmation
    """
    conn = get_db_connection()
    try:
        branchid = session.get("branchid", 1)
        user_id = session.get("user_id", 1)
        
        cursor = conn.cursor()
        
        # CRITICAL: Final check for pending recoveries
        pending = get_pending_recoveries(branchid)
        
        if len(pending) > 0:
            flash(f"❌ Cannot proceed! {len(pending)} pending recovery(ies) found. Please post all recoveries first.", "danger")
            return redirect(url_for("dayend.dayend_check"))
        
        # Get current date
        today = datetime.now()
        
        # Check if dayend already done for today
        cursor.execute("""
            SELECT Id FROM Dayend
            WHERE BranchId = ?
              AND CAST(DayendDate AS DATE) = CAST(? AS DATE)
        """, (branchid, today))
        
        existing = cursor.fetchone()
        if existing:
            flash("⚠️ Day End already completed for today!", "warning")
            return redirect(url_for("dayend.dayend_check"))
        
        # Insert dayend record
        cursor.execute("""
            INSERT INTO Dayend (DayendDate, BranchId, CreatedBy, ModifiedBy, ModifiedDate)
            VALUES (?, ?, ?, ?, GETDATE())
        """, (today, branchid, user_id, user_id))
        
        conn.commit()
        
        flash(f"✅ Day End completed successfully for {today.strftime('%d-%b-%Y')}!", "success")
        return redirect(url_for("dayend.dayend_check"))
    
    except Exception as e:
        conn.rollback()
        flash(f"Error processing dayend: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return redirect(url_for("dayend.dayend_check"))
    
    finally:
        conn.close()


@dayend_bp.route("/history", methods=["GET"])
def dayend_history():
    """Show dayend history for branch."""
    conn = get_db_connection()
    try:
        branchid = session.get("branchid", 1)
        
        cursor = conn.cursor()
        
        # ✅ CORRECTED: Table is "Branches", column is "Name"
        cursor.execute("SELECT Name FROM Branches WHERE Id = ?", (branchid,))
        branch_row = cursor.fetchone()
        branch_name = branch_row[0] if branch_row else "Unknown Branch"
        
        # Get dayend history (last 30 days)
        cursor.execute("""
            SELECT 
                d.Id,
                d.DayendDate,
                ISNULL(u.emp_name, 'Unknown') AS processed_by
            FROM Dayend d
            LEFT JOIN Users u ON d.CreatedBy = u.user_id
            WHERE d.BranchId = ?
            ORDER BY d.DayendDate DESC
        """, (branchid,))
        
        history = cursor.fetchall()
        
        return render_template("dayend_history.html",
                             branch_name=branch_name,
                             history=history)
    
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return render_template("dayend_history.html",
                             branch_name="Unknown",
                             history=[])
    finally:
        conn.close()
