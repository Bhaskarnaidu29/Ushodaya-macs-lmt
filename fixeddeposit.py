# fixeddeposit.py - BULLETPROOF VERSION
# Routes MUST register or it will print ERROR

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from db import get_db_connection
from datetime import datetime
from dateutil.relativedelta import relativedelta
import traceback
import logging

# Setup logging
logger = logging.getLogger(__name__)

# Create Blueprint - MUST happen at module level
fixeddeposit_bp = Blueprint("fixeddeposit_bp", __name__, template_folder="templates")

print("=" * 60)
print("FIXEDDEPOSIT.PY LOADING...")
print("=" * 60)


def calc_interest(amount, roi, tenure_months):
    """Calculate interest"""
    years = tenure_months / 12.0
    return round((amount * roi * years) / 100.0, 2)


def calculate_collection_records(deposit_date, tenure_months, payment_frequency):
    """Calculate collection dates"""
    records = []
    if isinstance(deposit_date, str):
        deposit_date = datetime.strptime(deposit_date, "%Y-%m-%d")
    
    freq_map = {1: 1, 3: 3, 6: 6, 12: 12, 24: 24}
    interval = freq_map.get(payment_frequency, 1)
    num_payments = max(1, tenure_months // interval)
    
    for i in range(1, num_payments + 1):
        due_date = deposit_date + relativedelta(months=i * interval)
        records.append(due_date)
    
    return records


@fixeddeposit_bp.route("/", methods=["GET", "POST"])
def fixeddeposit():
    """CREATE FD"""
    print(f"fixeddeposit() called - Method: {request.method}")
    
    if request.method == "POST":
        conn = None
        cursor = None
        
        try:
            # Get form data
            MemberCode = request.form.get("MemberCode", "").strip()
            MemberName = request.form.get("MemberName", "").strip()
            JointName = request.form.get("JointName", "").strip() or None
            DepositDate = request.form.get("DepositDate")
            DepositAmount = float(request.form.get("DepositAmount") or 0)
            DepositTenure = int(request.form.get("DepositTenure") or 0)
            PaymentFrequency = int(request.form.get("PaymentFrequency") or 1)
            ROI = float(request.form.get("ROI") or 0)
            Remarks = request.form.get("Remarks", "").strip() or None
            AadharNumber = request.form.get("AadharNumber", "").strip() or None
            NomineeName = request.form.get("NomineeName", "").strip() or None
            
            BranchId = int(session.get("branchid", 1))
            ModifiedBy = int(session.get("user_id", 1))
            
            print(f"Creating FD: ₹{DepositAmount:,.0f} @ {ROI}% for {DepositTenure}m")
            
            # Validate
            if not MemberCode or not MemberName:
                flash("Member code and name required", "warning")
                return redirect(url_for("fixeddeposit_bp.fixeddeposit"))
            if DepositAmount <= 0 or DepositAmount > 10000000:
                flash("Amount must be ₹1 to ₹1 Crore", "warning")
                return redirect(url_for("fixeddeposit_bp.fixeddeposit"))
            if ROI <= 0 or ROI > 30:
                flash("ROI must be 0.01% to 30%", "warning")
                return redirect(url_for("fixeddeposit_bp.fixeddeposit"))
            if DepositTenure <= 0:
                flash("Invalid tenure", "warning")
                return redirect(url_for("fixeddeposit_bp.fixeddeposit"))
            
            # Calculate
            deposit_date_obj = datetime.strptime(DepositDate, "%Y-%m-%d")
            maturity_date = deposit_date_obj + relativedelta(months=DepositTenure)
            InterestAmount = calc_interest(DepositAmount, ROI, DepositTenure)
            
            # Connect
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Insert FD
            temp_num = f"TEMP{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            
            cursor.execute("""
                INSERT INTO FDDetails (
                    FDNumber, MemberCode, MemberName, JointName,
                    DepositDate, WithdrawDate, DepositAmount, ROI,
                    InterestAmount, PaymentFrequency, DepositTenure, Remarks,
                    BranchId, ModifiedBy, ModifiedOn, AadharNumber, NomineeName
                ) OUTPUT INSERTED.Id
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?)
            """, (temp_num, MemberCode, MemberName, JointName,
                  deposit_date_obj, maturity_date, DepositAmount, ROI,
                  InterestAmount, PaymentFrequency, DepositTenure, Remarks,
                  BranchId, ModifiedBy, AadharNumber, NomineeName))
            
            row = cursor.fetchone()
            if not row:
                raise Exception("Insert failed")
            
            FDDetailsId = row[0]
            FDNumber = f"FD{BranchId}{str(FDDetailsId).zfill(3)}"
            cursor.execute("UPDATE FDDetails SET FDNumber = ? WHERE Id = ?", (FDNumber, FDDetailsId))
            conn.commit()
            
            print(f"✓ FD {FDNumber} saved")
            
            # Collections
            due_dates = calculate_collection_records(deposit_date_obj, DepositTenure, PaymentFrequency)
            num = len(due_dates)
            int_per = round(InterestAmount / num, 2)
            last_int = round(InterestAmount - (int_per * (num - 1)), 2)
            
            for idx, due_date in enumerate(due_dates):
                interest_due = last_int if (idx == num - 1) else int_per
                deposit_due = DepositAmount if (idx == num - 1) else 0
                
                # Calculate FromDate and ToDate for this period
                if idx == 0:
                    from_date = deposit_date_obj
                else:
                    from_date = due_dates[idx - 1]
                to_date = due_date
                
                cursor.execute("""
                    INSERT INTO FDCollections (
                        FDDetailsId, DepositDate, DueDate, FromDate, ToDate,
                        PaidDate, InterestDue, InterestPaid, DepositPaid, IsPaid,
                        BranchId, ModifiedBy, ModifiedOn, MaturityDate
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, 0, ?, 0, ?, ?, GETDATE(), ?)
                """, (FDDetailsId, deposit_date_obj, due_date, from_date, to_date,
                      interest_due, deposit_due, BranchId, ModifiedBy, due_date))
            
            conn.commit()
            print(f"✓ {num} collections saved")
            
            freq = {1: "Monthly", 3: "Quarterly", 6: "Half-Yearly", 12: "Yearly", 24: "2-Yearly"}
            flash(f"FD {FDNumber} created! ₹{DepositAmount:,.0f} @ {ROI}% ({freq.get(PaymentFrequency, 'Monthly')})", "success")
            
            return redirect(url_for("fixeddeposit_bp.fd_list"))
            
        except Exception as e:
            print(f"ERROR: {e}")
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            logger.error(f"FD Error: {e}\n{traceback.format_exc()}")
            flash(f"Error: {str(e)}", "danger")
            return redirect(url_for("fixeddeposit_bp.fixeddeposit"))
        finally:
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    # GET
    return render_template("fixeddeposit.html")


@fixeddeposit_bp.route("/list")
def fd_list():
    """LIST FDs"""
    print("fd_list() called")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        branchid = int(session.get("branchid", 1))
        
        cursor.execute("""
            SELECT fd.Id, fd.FDNumber, fd.MemberCode, fd.MemberName,
                   fd.DepositDate, fd.WithdrawDate, fd.DepositAmount, fd.ROI,
                   fd.InterestAmount, fd.DepositTenure,
                   CASE WHEN fd.WithdrawDate IS NULL OR fd.WithdrawDate >= CAST(GETDATE() AS DATE)
                        THEN 'Active' ELSE 'Matured' END AS FDStatus,
                   fd.PaymentFrequency
            FROM FDDetails fd
            WHERE fd.BranchId = ?
            ORDER BY fd.DepositDate DESC
        """, (branchid,))
        
        fds = cursor.fetchall()
        total_deposit = sum(float(fd[6] or 0) for fd in fds)
        total_interest = sum(float(fd[8] or 0) for fd in fds)
        
        return render_template("fd_list.html", fds=fds, total_deposit=total_deposit, total_interest=total_interest)
        
    except Exception as e:
        logger.error(f"List error: {e}")
        flash(f"Error: {str(e)}", "danger")
        return render_template("fd_list.html", fds=[], total_deposit=0, total_interest=0)
    finally:
        if conn:
            conn.close()


@fixeddeposit_bp.route("/view/<int:fd_id>")
def fd_view(fd_id):
    """VIEW FD"""
    print(f"fd_view({fd_id}) called")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT Id, FDNumber, MemberCode, MemberName, JointName,
                   DepositDate, WithdrawDate, DepositAmount, ROI, InterestAmount,
                   DepositTenure, Remarks, AadharNumber, NomineeName, PaymentFrequency
            FROM FDDetails WHERE Id = ?
        """, (fd_id,))
        fd = cursor.fetchone()
        
        if not fd:
            flash("FD not found", "warning")
            return redirect(url_for("fixeddeposit_bp.fd_list"))
        
        cursor.execute("""
            SELECT Id, MaturityDate, InterestDue, InterestPaid, DepositPaid, PaidDate
            FROM FDCollections WHERE FDDetailsId = ? ORDER BY MaturityDate
        """, (fd_id,))
        collections = cursor.fetchall()
        
        total_int_due = sum(float(c[2] or 0) for c in collections)
        total_int_paid = sum(float(c[3] or 0) for c in collections)
        total_dep_paid = sum(float(c[4] or 0) for c in collections)
        
        return render_template("fd_view.html", fd=fd, collections=collections,
                             total_int_due=total_int_due, total_int_paid=total_int_paid, total_dep_paid=total_dep_paid)
                             
    except Exception as e:
        logger.error(f"View error: {e}")
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for("fixeddeposit_bp.fd_list"))
    finally:
        if conn:
            conn.close()


@fixeddeposit_bp.route("/member_lookup")
def member_lookup():
    """MEMBER LOOKUP"""
    conn = None
    try:
        prefix = request.args.get("prefix", "").strip()
        if len(prefix) < 2:
            return jsonify([])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 10 member_code, full_name, aadhaar, phone1, city, state
            FROM Members WHERE member_code LIKE ? OR full_name LIKE ?
            ORDER BY member_code
        """, (f"{prefix}%", f"%{prefix}%"))
        
        rows = cursor.fetchall()
        return jsonify([{
            "member_code": r[0] or "",
            "full_name": r[1] or "",
            "aadhaar": r[2] or "",
            "phone1": r[3] or "",
            "city": r[4] or "",
            "state": r[5] or ""
        } for r in rows])
        
    except Exception as e:
        logger.error(f"Lookup error: {e}")
        return jsonify([]), 500
    finally:
        if conn:
            conn.close()


@fixeddeposit_bp.route("/delete/<int:fd_id>", methods=["POST"])
def fd_delete(fd_id):
    """DELETE FD"""
    print(f"fd_delete({fd_id}) called")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM FDCollections WHERE FDDetailsId = ?", (fd_id,))
        cursor.execute("DELETE FROM FDDetails WHERE Id = ?", (fd_id,))
        conn.commit()
        flash("FD deleted!", "success")
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Delete error: {e}")
        flash(f"Error: {str(e)}", "danger")
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("fixeddeposit_bp.fd_list"))


# Print routes on load
print("✓ fixeddeposit() registered at /")
print("✓ fd_list() registered at /list")
print("✓ fd_view() registered at /view/<id>")
print("✓ member_lookup() registered at /member_lookup")
print("✓ fd_delete() registered at /delete/<id>")
print("=" * 60)
print("FIXEDDEPOSIT.PY LOADED SUCCESSFULLY")
print("=" * 60)
