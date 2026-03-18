# fdcollections.py - WITH CORRECT PRECLOSURE CALCULATION
# Interest calculated ONLY from last paid date to pre-close date

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta
import traceback

fdcollections_bp = Blueprint("fdcollections_bp", __name__, template_folder="templates")


def calculate_interest_for_period(principal: Decimal, roi: float, payment_frequency: int) -> Decimal:
    """Calculate interest for ONE period based on payment frequency"""
    
    if payment_frequency == 1:  # Monthly
        interest = (Decimal(str(principal)) * Decimal(str(roi))) / (Decimal("12") * Decimal("100"))
    elif payment_frequency == 3:  # Quarterly
        interest = (Decimal(str(principal)) * Decimal(str(roi))) / (Decimal("4") * Decimal("100"))
    elif payment_frequency == 6:  # Half-Yearly
        interest = (Decimal(str(principal)) * Decimal(str(roi))) / (Decimal("2") * Decimal("100"))
    elif payment_frequency == 12:  # Yearly
        interest = (Decimal(str(principal)) * Decimal(str(roi))) / Decimal("100")
    elif payment_frequency == 24:  # 2-Yearly
        interest = (Decimal(str(principal)) * Decimal(str(roi)) * Decimal("2")) / Decimal("100")
    else:
        interest = (Decimal(str(principal)) * Decimal(str(roi))) / (Decimal("12") * Decimal("100"))
    
    return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_prorata_interest(principal: Decimal, roi: float, start_date, end_date) -> Decimal:
    """
    Calculate pro-rata interest for exact number of days
    Formula: Principal × Rate × Days / (365 × 100)
    """
    days = (end_date - start_date).days
    
    if days <= 0:
        return Decimal("0.00")
    
    # Pro-rata calculation
    interest = (Decimal(str(principal)) * Decimal(str(roi)) * Decimal(str(days))) / (Decimal("365") * Decimal("100"))
    
    return interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@fdcollections_bp.route("/", methods=["GET", "POST"])
def fdcollections():
    """FD Collections with DueDate tracking and PreClosed filter"""
    
    # Filters
    branch_filter = request.args.get("BranchId", str(session.get("branchid", ""))).strip()
    fdnumber_filter = request.args.get("FDNumber", "").strip()
    member_filter = request.args.get("MemberName", "").strip()
    status_filter = request.args.get("Status", "Unpaid").strip()
    include_preclosed = request.args.get("IncludePreClosed", "0").strip()
    
    # ========== POST: Process Payments ==========
    if request.method == "POST":
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            today = datetime.now().date()
            user_id = int(session.get('user_id', 1))
            
            form_rows = int(request.form.get("form_row_count", "0"))
            
            payment_count = 0
            errors = []
            
            for i in range(form_rows):
                if not request.form.get(f"select_{i}"):
                    continue
                
                collection_id = request.form.get(f"collection_id_{i}", "").strip()
                payment_amount_str = request.form.get(f"payment_amount_{i}", "0").strip()
                interest_due_str = request.form.get(f"interest_due_{i}", "0").strip()
                
                if not collection_id:
                    continue
                
                try:
                    payment_amount = Decimal(payment_amount_str or "0")
                    interest_due = Decimal(interest_due_str or "0")
                except:
                    errors.append(f"Row {i+1}: Invalid amount")
                    continue
                
                if payment_amount <= 0:
                    errors.append(f"Row {i+1}: Amount must be > 0")
                    continue
                
                cursor.execute("SELECT InterestPaid FROM FDCollections WHERE Id = ?", (collection_id,))
                row = cursor.fetchone()
                if not row:
                    errors.append(f"Row {i+1}: Record not found")
                    continue
                
                current_paid = Decimal(str(row[0] or 0))
                remaining = interest_due - current_paid
                
                if payment_amount > remaining:
                    errors.append(
                        f"Row {i+1}: Payment ₹{payment_amount:,.2f} exceeds "
                        f"remaining ₹{remaining:,.2f}"
                    )
                    continue
                
                new_total_paid = current_paid + payment_amount
                is_fully_paid = (new_total_paid >= interest_due)
                
                cursor.execute("""
                    UPDATE FDCollections
                    SET InterestPaid = ?,
                        IsPaid = ?,
                        PaidDate = CASE WHEN ? = 1 THEN ? ELSE PaidDate END,
                        ModifiedBy = ?,
                        ModifiedOn = GETDATE()
                    WHERE Id = ?
                """, (
                    new_total_paid,
                    1 if is_fully_paid else 0,
                    1 if is_fully_paid else 0,
                    today if is_fully_paid else None,
                    user_id,
                    collection_id
                ))
                
                payment_count += 1
            
            if errors:
                for error in errors:
                    flash(error, "warning")
            
            if payment_count > 0:
                conn.commit()
                flash(f"✅ {payment_count} payment(s) posted successfully!", "success")
            elif not errors:
                flash("No payments selected", "info")
            
            return redirect(url_for("fdcollections_bp.fdcollections"))
            
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"Error: {str(e)}", "danger")
            print(traceback.format_exc())
            return redirect(url_for("fdcollections_bp.fdcollections"))
        finally:
            if conn:
                conn.close()
    
    # ========== GET: Display Collections ==========
    collections = []
    total_interest_due = 0
    total_interest_paid = 0
    count_unpaid = 0
    count_paid = 0
    count_preclosed = 0
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        today = datetime.now().date()
        
        query = """
            SELECT 
                c.Id,
                c.FDDetailsId,
                d.FDNumber,
                d.MemberCode,
                d.MemberName,
                d.DepositAmount,
                d.ROI,
                d.PaymentFrequency,
                c.DueDate,
                c.InterestDue,
                c.InterestPaid,
                c.IsPaid,
                c.PaidDate,
                c.FromDate,
                c.ToDate,
                d.BranchId,
                d.FDStatus
            FROM FDCollections c
            JOIN FDDetails d ON c.FDDetailsId = d.Id
            WHERE 1=1
              AND c.DueDate <= CAST(GETDATE() AS DATE)
        """
        
        params = []
        
        if include_preclosed == "0":
            query += " AND (d.FDStatus IS NULL OR d.FDStatus != 'PreClosed')"
        
        if branch_filter:
            query += " AND d.BranchId = ?"
            params.append(branch_filter)
        
        if fdnumber_filter:
            query += " AND d.FDNumber LIKE ?"
            params.append(f"%{fdnumber_filter}%")
        
        if member_filter:
            query += " AND d.MemberName LIKE ?"
            params.append(f"%{member_filter}%")
        
        if status_filter == "Unpaid":
            query += " AND c.IsPaid = 0"
        elif status_filter == "Paid":
            query += " AND c.IsPaid = 1"
        
        query += " ORDER BY c.DueDate ASC, d.FDNumber ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        for row in rows:
            collection_id = row[0]
            fd_details_id = row[1]
            fd_number = row[2]
            member_code = row[3]
            member_name = row[4]
            deposit_amount = Decimal(str(row[5] or 0))
            roi = float(row[6] or 0)
            payment_frequency = int(row[7] or 1)
            due_date = row[8].date() if row[8] and isinstance(row[8], datetime) else row[8]
            interest_due = Decimal(str(row[9] or 0))
            interest_paid = Decimal(str(row[10] or 0))
            is_paid = bool(row[11])
            paid_date = row[12].date() if row[12] and isinstance(row[12], datetime) else row[12]
            from_date = row[13].date() if row[13] and isinstance(row[13], datetime) else row[13]
            to_date = row[14].date() if row[14] and isinstance(row[14], datetime) else row[14]
            branch_id = row[15]
            fd_status = row[16] if len(row) > 16 else None
            
            remaining = interest_due - interest_paid
            
            if fd_status == "PreClosed":
                status = "PreClosed"
                count_preclosed += 1
            elif is_paid:
                status = "Paid"
                count_paid += 1
            elif due_date < today:
                status = "Overdue"
                count_unpaid += 1
            else:
                status = "Due"
                count_unpaid += 1
            
            freq_map = {1: "Monthly", 3: "Quarterly", 6: "Half-Yearly", 12: "Yearly", 24: "2-Yearly"}
            frequency_name = freq_map.get(payment_frequency, "Monthly")
            
            collections.append({
                'collection_id': collection_id,
                'fd_details_id': fd_details_id,
                'fd_number': fd_number,
                'member_code': member_code,
                'member_name': member_name,
                'deposit_amount': deposit_amount,
                'roi': roi,
                'frequency_name': frequency_name,
                'due_date': due_date,
                'interest_due': interest_due,
                'interest_paid': interest_paid,
                'remaining': remaining,
                'is_paid': is_paid,
                'paid_date': paid_date,
                'status': status,
                'fd_status': fd_status,
                'can_pay': not is_paid and fd_status != 'PreClosed'
            })
            
            total_interest_due += float(interest_due)
            total_interest_paid += float(interest_paid)
        
    except Exception as e:
        flash(f"Error loading collections: {str(e)}", "danger")
        print(traceback.format_exc())
    finally:
        if conn:
            conn.close()
    
    return render_template(
        "fdcollections.html",
        collections=collections,
        branch_filter=branch_filter,
        fdnumber_filter=fdnumber_filter,
        member_filter=member_filter,
        status_filter=status_filter,
        include_preclosed=include_preclosed,
        total_interest_due=total_interest_due,
        total_interest_paid=total_interest_paid,
        count_unpaid=count_unpaid,
        count_paid=count_paid,
        count_preclosed=count_preclosed,
        today=datetime.now().date(),
        enumerate=enumerate
    )


@fdcollections_bp.route("/preclose/<int:fd_id>", methods=["GET", "POST"])
def fd_preclose(fd_id):
    """
    Pre-close an FD with CORRECT interest calculation:
    Interest = From (Last Paid Date OR Deposit Date) TO Pre-Close Date ONLY
    """
    conn = None
    
    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            preclose_date_str = request.form.get("preclose_date")
            penalty_amount = Decimal(request.form.get("penalty_amount", "0") or "0")
            remarks = request.form.get("remarks", "").strip()
            user_id = int(session.get('user_id', 1))
            
            if not preclose_date_str:
                flash("Pre-close date is required", "danger")
                return redirect(url_for("fdcollections_bp.fd_preclose", fd_id=fd_id))
            
            preclose_date = datetime.strptime(preclose_date_str, '%Y-%m-%d').date()
            
            # Get FD details
            cursor.execute("""
                SELECT Id, FDNumber, DepositAmount, ROI, DepositDate, WithdrawDate, 
                       PaymentFrequency, FDStatus
                FROM FDDetails
                WHERE Id = ?
            """, (fd_id,))
            
            fd_row = cursor.fetchone()
            if not fd_row:
                flash("FD not found", "danger")
                return redirect(url_for("fdcollections_bp.fdcollections"))
            
            fd_id_val = fd_row[0]
            fd_number = fd_row[1]
            deposit_amount = Decimal(str(fd_row[2] or 0))
            roi = float(fd_row[3] or 0)
            deposit_date = fd_row[4].date() if fd_row[4] and isinstance(fd_row[4], datetime) else fd_row[4]
            maturity_date = fd_row[5].date() if fd_row[5] and isinstance(fd_row[5], datetime) else fd_row[5]
            payment_frequency = int(fd_row[6] or 1)
            current_status = fd_row[7]
            
            if current_status == 'PreClosed':
                flash("FD is already pre-closed", "info")
                return redirect(url_for("fixeddeposit_bp.fd_view", fd_id=fd_id))
            
            # CRITICAL: Find last interest paid date
            cursor.execute("""
                SELECT MAX(PaidDate)
                FROM FDCollections
                WHERE FDDetailsId = ?
                  AND IsPaid = 1
                  AND PaidDate IS NOT NULL
            """, (fd_id_val,))
            
            last_paid_row = cursor.fetchone()
            last_paid_date = None
            
            if last_paid_row and last_paid_row[0]:
                last_paid_date = last_paid_row[0].date() if isinstance(last_paid_row[0], datetime) else last_paid_row[0]
            
            # Determine start date for interest calculation
            # Start = MAX(Last Paid Date, Deposit Date)
            if last_paid_date:
                interest_start_date = max(last_paid_date, deposit_date)
            else:
                interest_start_date = deposit_date
            
            # Calculate pro-rata interest from interest_start_date to preclose_date
            accrued_interest = calculate_prorata_interest(
                deposit_amount, 
                roi, 
                interest_start_date, 
                preclose_date
            )
            
            # Final settlement
            settlement_amount = deposit_amount + accrued_interest - penalty_amount
            
            # Update FDDetails
            cursor.execute("""
                UPDATE FDDetails
                SET FDStatus = 'PreClosed',
                    PreCloseDate = ?,
                    PreClosePenalty = ?,
                    PreCloseRemarks = ?,
                    PreCloseAccruedInterest = ?,
                    PreCloseSettlementAmount = ?,
                    PreCloseInterestStartDate = ?,
                    ModifiedBy = ?,
                    ModifiedOn = GETDATE()
                WHERE Id = ?
            """, (
                preclose_date, 
                penalty_amount, 
                remarks,
                accrued_interest,
                settlement_amount,
                interest_start_date,
                user_id, 
                fd_id_val
            ))
            
            # Mark ONLY unpaid collections as paid (don't touch already paid ones)
            cursor.execute("""
                UPDATE FDCollections
                SET IsPaid = 1,
                    PaidDate = ?,
                    InterestPaid = 0,
                    ModifiedBy = ?,
                    ModifiedOn = GETDATE()
                WHERE FDDetailsId = ?
                  AND IsPaid = 0
            """, (preclose_date, user_id, fd_id_val))
            
            conn.commit()
            
            flash(
                f"✅ FD {fd_number} pre-closed successfully! "
                f"Interest Period: {interest_start_date.strftime('%d-%b-%Y')} to {preclose_date.strftime('%d-%b-%Y')} "
                f"({(preclose_date - interest_start_date).days} days) | "
                f"Accrued Interest: ₹{accrued_interest:,.2f} | "
                f"Penalty: ₹{penalty_amount:,.2f} | "
                f"Settlement: ₹{settlement_amount:,.2f}",
                "success"
            )
            
            return redirect(url_for("fixeddeposit_bp.fd_view", fd_id=fd_id))
            
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"Error: {str(e)}", "danger")
            print(traceback.format_exc())
            return redirect(url_for("fdcollections_bp.fd_preclose", fd_id=fd_id))
        finally:
            if conn:
                conn.close()
    
    # GET: Show pre-close form
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT Id, FDNumber, MemberName, DepositAmount, ROI, 
                   DepositDate, WithdrawDate, FDStatus
            FROM FDDetails
            WHERE Id = ?
        """, (fd_id,))
        
        fd = cursor.fetchone()
        
        if not fd:
            flash("FD not found", "danger")
            return redirect(url_for("fdcollections_bp.fdcollections"))
        
        if fd[7] == 'PreClosed':
            flash("FD is already pre-closed", "info")
            return redirect(url_for("fixeddeposit_bp.fd_view", fd_id=fd_id))
        
        # Get last paid date for display
        cursor.execute("""
            SELECT MAX(PaidDate)
            FROM FDCollections
            WHERE FDDetailsId = ?
              AND IsPaid = 1
              AND PaidDate IS NOT NULL
        """, (fd_id,))
        
        last_paid_row = cursor.fetchone()
        last_paid_date = None
        
        if last_paid_row and last_paid_row[0]:
            last_paid_date = last_paid_row[0].date() if isinstance(last_paid_row[0], datetime) else last_paid_row[0]
        
        return render_template(
            "fd_preclose.html", 
            fd=fd, 
            last_paid_date=last_paid_date,
            today=datetime.now().date()
        )
        
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        print(traceback.format_exc())
        return redirect(url_for("fdcollections_bp.fdcollections"))
    finally:
        if conn:
            conn.close()
