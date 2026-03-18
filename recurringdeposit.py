# recurringdeposit.py - Fixed to match actual RecurringDeposit table structure
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from datetime import datetime
from dateutil.relativedelta import relativedelta
from db import get_db_connection
import traceback

recurringdeposit_bp = Blueprint(
    "recurringdeposit_bp",
    __name__,
    template_folder="templates"
)

# ═══════════════════════════════════════════════════════════════
#  HELPER: Generate RD Number
# ═══════════════════════════════════════════════════════════════
def generate_rd_number(branchid):
    """Generate RD number like RD{BranchCode}{SequenceNo}"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get branch code
        cursor.execute("SELECT Code FROM Branches WHERE Id = ?", (branchid,))
        branch = cursor.fetchone()
        if not branch:
            return None
        code = branch[0]

        # Get next sequence number
        prefix = f"RD{code}"
        cursor.execute("""
            SELECT ISNULL(MAX(CAST(SUBSTRING(RDNumber, LEN(?) + 1, 10) AS INT)), 0) + 1
            FROM RecurringDeposit
            WHERE BranchId = ? AND RDNumber LIKE ?
        """, (prefix, branchid, f"{prefix}%"))
        seq = cursor.fetchone()[0]

        rd_number = f"{prefix}{seq:04d}"
        return rd_number

    except Exception:
        print(traceback.format_exc())
        return None
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  HELPER: Calculate RD Maturity Value
# ═══════════════════════════════════════════════════════════════
def calculate_rd_maturity(monthly_deposit, tenure, interest_rate):
    """
    Calculate RD maturity value using compound interest formula.
    Formula: M = P × n × (n + 1) / 2 × (1 + r/400)
    Where:
    - P = Monthly deposit
    - n = Tenure (months)
    - r = Interest rate per annum
    """
    P = float(monthly_deposit)
    n = int(tenure)
    r = float(interest_rate)
    
    # Total principal deposited
    total_principal = P * n
    
    # Interest calculation
    # Using: Interest = P × n × (n + 1) / 2 × (r / 1200)
    total_interest = P * n * (n + 1) / 2 * (r / 1200)
    
    # Maturity value = Principal + Interest
    maturity_value = total_principal + total_interest
    
    return round(maturity_value, 2)


# ═══════════════════════════════════════════════════════════════
#  API: Generate RD Number (uses session branchid)
# ═══════════════════════════════════════════════════════════════
@recurringdeposit_bp.route("/generate-rdnumber-auto")
def generate_rdnumber_auto():
    branchid = session.get("branchid")
    if not branchid:
        return jsonify({"error": "Branch not in session"}), 400
    rd_number = generate_rd_number(int(branchid))
    if rd_number is None:
        return jsonify({"error": "Branch not found"}), 404
    return jsonify({"rdnumber": rd_number})



@recurringdeposit_bp.route("/generate-rdnumber")
def generate_rdnumber_api():
    branchid = request.args.get("branchid", type=int)
    if not branchid:
        return jsonify({"error": "Branch ID required"}), 400
    rd_number = generate_rd_number(branchid)
    if rd_number is None:
        return jsonify({"error": "Branch not found"}), 404
    return jsonify({"rdnumber": rd_number})


# ═══════════════════════════════════════════════════════════════
#  API: Member Autocomplete
# ═══════════════════════════════════════════════════════════════
@recurringdeposit_bp.route("/members")
def members_api():
    term = request.args.get("term", "").strip()
    if len(term) < 2:
        return jsonify([])
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 10 member_code, full_name, phone1
            FROM Members
            WHERE member_code LIKE ? OR full_name LIKE ?
            ORDER BY full_name
        """, (f"%{term}%", f"%{term}%"))
        rows = cursor.fetchall()

        members = []
        for r in rows:
            members.append({
                "MemberCode": r[0] or "",
                "MemberName": r[1] or "",
                "Phone": r[2] or ""
            })
        return jsonify(members)
    
    except Exception:
        print(traceback.format_exc())
        return jsonify([]), 500
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  ROUTE: Redirect root to add form
# ═══════════════════════════════════════════════════════════════
@recurringdeposit_bp.route("/")
def rd_index():
    return redirect(url_for("recurringdeposit_bp.add_rd"))


# ═══════════════════════════════════════════════════════════════
#  ROUTE: Add New RD (GET + POST)
# ═══════════════════════════════════════════════════════════════
@recurringdeposit_bp.route("/add", methods=["GET", "POST"])
def add_rd():
    if request.method == "POST":
        conn = None
        try:
            # ── Validate and parse form inputs ──────────────────
            branchid = session.get("branchid")
            if not branchid:
                branchid = request.form.get("BranchId")
                if not branchid:
                    flash("Branch is required", "danger")
                    return redirect(url_for("recurringdeposit_bp.add_rd"))
            branchid = int(branchid)

            # Generate or use provided RD number
            rd_number = request.form.get("RDNumber", "").strip()
            if not rd_number:
                rd_number = generate_rd_number(branchid)
                if not rd_number:
                    flash("Could not generate RD number", "danger")
                    return redirect(url_for("recurringdeposit_bp.add_rd"))

            member_code = request.form.get("MemberCode", "").strip()
            if not member_code:
                flash("Member code is required", "danger")
                return redirect(url_for("recurringdeposit_bp.add_rd"))

            member_name = request.form.get("MemberName", "").strip()
            if not member_name:
                flash("Member name is required", "danger")
                return redirect(url_for("recurringdeposit_bp.add_rd"))

            # StartDate (not DueDate!)
            start_date_str = request.form.get("StartDate")
            if not start_date_str:
                flash("Start date is required", "danger")
                return redirect(url_for("recurringdeposit_bp.add_rd"))
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")

            # Tenure
            tenure_raw = request.form.get("Tenure", "0")
            try:
                tenure = int(tenure_raw)
                if tenure <= 0:
                    raise ValueError("Tenure must be positive")
            except ValueError:
                flash("Tenure must be a positive integer", "danger")
                return redirect(url_for("recurringdeposit_bp.add_rd"))

            # MonthlyDeposit (not DepositAmount!)
            monthly_deposit_raw = request.form.get("MonthlyDeposit", "0")
            try:
                monthly_deposit = float(monthly_deposit_raw)
                if monthly_deposit <= 0:
                    raise ValueError("Monthly deposit must be positive")
            except ValueError:
                flash("Monthly deposit must be a positive number", "danger")
                return redirect(url_for("recurringdeposit_bp.add_rd"))

            # InterestRate (not Interest!)
            interest_rate_raw = request.form.get("InterestRate", "0")
            try:
                interest_rate = float(interest_rate_raw)
            except ValueError:
                interest_rate = 0.0

            # Calculate maturity date and value
            maturity_date = start_date + relativedelta(months=tenure)
            
            # Status (Active by default)
            status = "Active"

            # Created by
            create_staff = session.get("emp_name", "System")
            modified_by = int(session.get("user_id", 1))

            # ── Insert into RecurringDeposit table ──────────────
            conn = get_db_connection()
            cursor = conn.cursor()

            # TABLE COLUMNS (exact match):
            # RDId, RDNumber, MemberCode, MemberName, MonthlyDeposit, Tenure,
            # InterestRate, StartDate, MaturityDate, Status, BranchId,
            # CreatedAt, CreateStaff, ModifiedBy, ModifiedDate
            cursor.execute("""
                INSERT INTO RecurringDeposit (
                    RDNumber, MemberCode, MemberName, MonthlyDeposit, Tenure,
                    InterestRate, StartDate, MaturityDate, Status, BranchId,
                    CreatedAt, CreateStaff, ModifiedBy, ModifiedDate
                )
                OUTPUT INSERTED.RDId
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?, GETDATE())
            """, (
                rd_number, member_code, member_name, monthly_deposit, tenure,
                interest_rate, start_date, maturity_date, status, branchid,
                create_staff, modified_by
            ))

            row = cursor.fetchone()
            if not row:
                raise Exception("Failed to insert RD record")
            
            rd_id = row[0]

            # ── Create installment schedule in RDCollections ────
            # TABLE COLUMNS: Id, RDId, DueDate, PaidDate, AmountDue, AmountPaid,
            #                Status, BranchId, CreatedAt, ModifiedBy, ModifiedDate
            for i in range(tenure):
                due_date = start_date + relativedelta(months=i)
                cursor.execute("""
                    INSERT INTO RDCollections (
                        RDId, DueDate, AmountDue, Status, BranchId,
                        CreatedAt, ModifiedBy, ModifiedDate
                    )
                    VALUES (?, ?, ?, ?, ?, GETDATE(), ?, GETDATE())
                """, (rd_id, due_date.date(), monthly_deposit, "Pending", branchid, modified_by))

            conn.commit()
            
            # Calculate maturity value for display
            maturity_value = calculate_rd_maturity(monthly_deposit, tenure, interest_rate)
            
            flash(
                f"✅ RD {rd_number} created successfully! "
                f"Monthly: ₹{monthly_deposit:,.0f} | "
                f"Tenure: {tenure} months | "
                f"Maturity: ₹{maturity_value:,.2f}",
                "success"
            )
            return redirect(url_for("recurringdeposit_bp.rd_list"))

        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"Error creating RD: {str(e)}", "danger")
            print(traceback.format_exc())
            return redirect(url_for("recurringdeposit_bp.add_rd"))

        finally:
            if conn:
                conn.close()

    # ── GET: Show form ──────────────────────────────────────
    return render_template("recurringdeposit.html")


# ═══════════════════════════════════════════════════════════════
#  ROUTE: List All RDs
# ═══════════════════════════════════════════════════════════════
@recurringdeposit_bp.route("/list")
def rd_list():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Filter by session branch if available
        branchid = session.get("branchid")
        
        if branchid:
            cursor.execute("""
                SELECT 
                    RDId, RDNumber, MemberCode, MemberName,
                    MonthlyDeposit, Tenure, InterestRate,
                    StartDate, MaturityDate, Status
                FROM RecurringDeposit
                WHERE BranchId = ?
                ORDER BY CreatedAt DESC
            """, (branchid,))
        else:
            cursor.execute("""
                SELECT 
                    RDId, RDNumber, MemberCode, MemberName,
                    MonthlyDeposit, Tenure, InterestRate,
                    StartDate, MaturityDate, Status
                FROM RecurringDeposit
                ORDER BY CreatedAt DESC
            """)
        
        rows = cursor.fetchall()
        
        # Calculate maturity values for display
        deposits = []
        for r in rows:
            maturity_value = calculate_rd_maturity(r[4], r[5], r[6])
            deposits.append({
                'RDId': r[0],
                'RDNumber': r[1],
                'MemberCode': r[2],
                'MemberName': r[3],
                'MonthlyDeposit': r[4],
                'Tenure': r[5],
                'InterestRate': r[6],
                'StartDate': r[7],
                'MaturityDate': r[8],
                'Status': r[9],
                'MaturityValue': maturity_value
            })
        
        # Calculate totals
        total_monthly = sum(d['MonthlyDeposit'] for d in deposits)
        total_maturity = sum(d['MaturityValue'] for d in deposits)
        
        return render_template("rd_list.html", 
                             deposits=deposits,
                             total_monthly=total_monthly,
                             total_maturity=total_maturity)
    
    except Exception:
        flash("Error loading RD list", "danger")
        print(traceback.format_exc())
        return render_template("rd_list.html", 
                             deposits=[],
                             total_monthly=0,
                             total_maturity=0)
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  ROUTE: View RD Details + Collection Schedule
# ═══════════════════════════════════════════════════════════════
@recurringdeposit_bp.route("/view/<int:rd_id>")
def rd_view(rd_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get RD details
        cursor.execute("""
            SELECT 
                RDId, RDNumber, MemberCode, MemberName,
                MonthlyDeposit, Tenure, InterestRate,
                StartDate, MaturityDate, Status, BranchId
            FROM RecurringDeposit
            WHERE RDId = ?
        """, (rd_id,))
        
        rd = cursor.fetchone()
        if not rd:
            flash("RD not found", "warning")
            return redirect(url_for("recurringdeposit_bp.rd_list"))
        
        # Get collection schedule
        cursor.execute("""
            SELECT 
                Id, InstallmentNo, DueDate, Amount, Status,
                PaidDate, PaidAmount
            FROM RDCollections
            WHERE RDID = ?
            ORDER BY InstallmentNo
        """, (rd_id,))
        
        collections = cursor.fetchall()
        
        # Calculate maturity value
        maturity_value = calculate_rd_maturity(rd[4], rd[5], rd[6])
        
        return render_template(
            "rd_view.html",
            rd=rd,
            collections=collections,
            maturity_value=maturity_value,
            today=datetime.now().date()
        )
    
    except Exception:
        flash("Error loading RD details", "danger")
        print(traceback.format_exc())
        return redirect(url_for("recurringdeposit_bp.rd_list"))
    finally:
        if conn:
            conn.close()
