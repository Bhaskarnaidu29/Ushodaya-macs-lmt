# rdcollections.py - Fixed to match actual RDCollections table structure
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from datetime import datetime, date
from decimal import Decimal
import traceback

rdcollections_bp = Blueprint(
    "rdcollections_bp",
    __name__,
    template_folder="templates"
)

# ═══════════════════════════════════════════════════════════════
#  HELPER: Get Dayend Date
# ═══════════════════════════════════════════════════════════════
def get_dayend_date(branchid):
    """Get latest dayend date for validation"""
    if not branchid:
        return None
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(DayendDate) FROM Dayend WHERE BranchId = ?
        """, (branchid,))
        row = cursor.fetchone()
        if row and row[0]:
            return row[0] if isinstance(row[0], date) else row[0].date()
        return None
    except Exception:
        print(traceback.format_exc())
        return None
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  ROUTE: List RD Collections (GET + POST for bulk payment)
# ═══════════════════════════════════════════════════════════════
@rdcollections_bp.route("/", methods=["GET", "POST"])
def rd_collections():
    """
    Display and manage RD collections.
    GET: Show list of collections with filters
    POST: Process bulk payments
    """
    
    # ── Filters ────────────────────────────────────────────────
    branch_filter = request.args.get("BranchId", session.get("branchid", ""))
    rd_number_filter = request.args.get("RDNumber", "").strip()
    member_filter = request.args.get("MemberName", "").strip()
    status_filter = request.args.get("Status", "Pending").strip()  # All | Pending | Paid
    show_all = request.args.get("ShowAll", "0").strip()  # 0=only today/past, 1=all
    
    # Initialize variables
    collections = []
    dayend_date = ""
    total_due = 0
    total_paid = 0
    count_paid = 0
    count_pending = 0
    
    # ══════════════════════════════════════════════════════════
    #  POST ─ BULK PAYMENT
    # ══════════════════════════════════════════════════════════
    if request.method == "POST" and request.form.get("bulk_update"):
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get dayend date for validation
            try:
                branch_value = int(branch_filter) if branch_filter else None
            except:
                branch_value = None
            
            dayend_dt = get_dayend_date(branch_value)
            
            form_rows = int(request.form.get("form_row_count", "0"))
            updated_count = 0
            errors = []
            any_selected = False
            
            for i in range(form_rows):
                collection_id = request.form.get(f"CollectionId_{i}", "").strip()
                if not collection_id or not request.form.get(f"update_{i}"):
                    continue
                
                any_selected = True
                
                # Parse inputs
                amount_paid_raw = request.form.get(f"AmountPaid_{i}", "0").strip()
                paid_date_raw = request.form.get(f"PaidDate_{i}", "").strip()
                
                try:
                    amount_paid = Decimal(amount_paid_raw or "0")
                except:
                    errors.append(f"Row {i+1}: Invalid amount")
                    continue
                
                if paid_date_raw:
                    try:
                        paid_date = datetime.strptime(paid_date_raw, "%Y-%m-%d")
                    except:
                        errors.append(f"Row {i+1}: Invalid date")
                        continue
                else:
                    paid_date = datetime.now()
                
                # Dayend validation
                if dayend_dt and paid_date.date() > dayend_dt:
                    errors.append(f"Row {i+1}: Date exceeds dayend date")
                    continue
                
                modified_by = int(session.get("user_id", 1))
                
                try:
                    # TABLE COLUMNS: Id, RDId, DueDate, PaidDate, AmountDue, 
                    #                AmountPaid, Status, BranchId, CreatedAt, 
                    #                ModifiedBy, ModifiedDate
                    cursor.execute("""
                        UPDATE RDCollections
                        SET PaidDate = ?,
                            AmountPaid = ?,
                            Status = 'Paid',
                            ModifiedBy = ?,
                            ModifiedDate = GETDATE()
                        WHERE Id = ?
                    """, (paid_date, str(amount_paid), modified_by, collection_id))
                    
                    updated_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {i+1}: {str(e)}")
                    print(traceback.format_exc())
                    continue
            
            if any_selected:
                conn.commit()
                if updated_count:
                    flash(f"✅ {updated_count} payment(s) recorded successfully!", "success")
            else:
                conn.rollback()
                flash("⚠️ No rows selected", "warning")
            
            if errors:
                flash("Errors: " + " | ".join(errors[:5]), "danger")
        
        except Exception:
            if conn:
                conn.rollback()
            flash("Error processing payments", "danger")
            print(traceback.format_exc())
        finally:
            if conn:
                conn.close()
        
        return redirect(url_for(
            "rdcollections_bp.rd_collections",
            BranchId=branch_filter,
            RDNumber=rd_number_filter,
            MemberName=member_filter,
            Status=status_filter,
            ShowAll=show_all
        ))
    
    # ══════════════════════════════════════════════════════════
    #  GET ─ LIST VIEW
    # ══════════════════════════════════════════════════════════
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query
        query = """
            SELECT 
                c.Id,
                c.RDId,
                rd.RDNumber,
                rd.MemberCode,
                rd.MemberName,
                c.DueDate,
                c.AmountDue,
                c.AmountPaid,
                c.PaidDate,
                c.Status,
                c.BranchId,
                CASE
                    WHEN c.PaidDate IS NOT NULL THEN 'Paid'
                    WHEN c.DueDate < CAST(GETDATE() AS DATE) THEN 'Overdue'
                    ELSE 'Pending'
                END AS PayStatus
            FROM RDCollections c
            JOIN RecurringDeposit rd ON c.RDId = rd.RDId
            WHERE 1=1
        """
        params = []
        
        # Date filter (only if show_all is OFF)
        if show_all != "1":
            query += """
                AND (
                    c.DueDate <= CAST(GETDATE() AS DATE)
                    OR c.PaidDate IS NOT NULL
                )
            """
        
        # Branch filter
        if branch_filter:
            query += " AND c.BranchId = ?"
            params.append(branch_filter)
        
        # RD Number filter
        if rd_number_filter:
            query += " AND rd.RDNumber LIKE ?"
            params.append(f"%{rd_number_filter}%")
        
        # Member filter
        if member_filter:
            query += " AND rd.MemberName LIKE ?"
            params.append(f"%{member_filter}%")
        
        # Status filter
        if status_filter == "Pending":
            query += " AND c.PaidDate IS NULL AND c.DueDate <= CAST(GETDATE() AS DATE)"
        elif status_filter == "Paid":
            query += " AND c.PaidDate IS NOT NULL"
        elif status_filter == "Overdue":
            query += " AND c.PaidDate IS NULL AND c.DueDate < CAST(GETDATE() AS DATE)"
        
        query += " ORDER BY c.DueDate ASC, rd.MemberName ASC"
        
        cursor.execute(query, params)
        collections = cursor.fetchall()
        
        # Get dayend date
        if branch_filter:
            branch_for_dayend = branch_filter
        elif collections:
            branch_for_dayend = collections[0][10]  # BranchId at index 10
        else:
            branch_for_dayend = None
        
        dayend_date_obj = get_dayend_date(branch_for_dayend)
        dayend_date = dayend_date_obj.strftime("%Y-%m-%d") if dayend_date_obj else ""
        
        # Calculate totals
        total_due = sum(float(r[6] or 0) for r in collections)
        total_paid = sum(float(r[7] or 0) for r in collections)
        count_paid = sum(1 for r in collections if r[8] is not None)
        count_pending = len(collections) - count_paid
    
    except Exception:
        flash("Error loading collections", "danger")
        print(traceback.format_exc())
    finally:
        if conn:
            conn.close()
    
    today_obj = datetime.now().date()
    
    return render_template(
        "rdcollections.html",
        collections=collections,
        branch_filter=branch_filter,
        rd_number_filter=rd_number_filter,
        member_filter=member_filter,
        status_filter=status_filter,
        show_all=show_all,
        dayend_date=dayend_date,
        total_due=total_due,
        total_paid=total_paid,
        count_paid=count_paid,
        count_pending=count_pending,
        today=today_obj,
        today_str=today_obj.strftime("%Y-%m-%d"),
        enumerate=enumerate
    )


# ═══════════════════════════════════════════════════════════════
#  ROUTE: Single Payment (Individual collection update)
# ═══════════════════════════════════════════════════════════════
@rdcollections_bp.route("/pay/<int:collection_id>", methods=["POST"])
def rd_collection_pay(collection_id):
    """Record payment for a single RD collection"""
    conn = None
    try:
        paid_date_str = request.form.get("PaidDate")
        amount_paid = request.form.get("AmountPaid")
        
        if not amount_paid:
            flash("Amount is required", "danger")
            return redirect(url_for("rdcollections_bp.rd_collections"))
        
        try:
            amount_paid = Decimal(amount_paid)
        except:
            flash("Invalid amount", "danger")
            return redirect(url_for("rdcollections_bp.rd_collections"))
        
        if paid_date_str:
            try:
                paid_date = datetime.strptime(paid_date_str, "%Y-%m-%d")
            except:
                paid_date = datetime.now()
        else:
            paid_date = datetime.now()
        
        modified_by = int(session.get("user_id", 1))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE RDCollections
            SET PaidDate = ?,
                AmountPaid = ?,
                Status = 'Paid',
                ModifiedBy = ?,
                ModifiedDate = GETDATE()
            WHERE Id = ?
        """, (paid_date, str(amount_paid), modified_by, collection_id))
        
        conn.commit()
        flash("✅ Payment recorded successfully!", "success")
    
    except Exception as e:
        if conn:
            conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        print(traceback.format_exc())
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("rdcollections_bp.rd_collections"))
