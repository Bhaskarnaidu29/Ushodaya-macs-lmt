"""
Members Management Module
Handles member CRUD operations with auto-generated member codes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, date
from db import get_db_connection
from login import login_required
import logging

logger = logging.getLogger(__name__)

members_bp = Blueprint("members_bp", __name__, template_folder="templates")

def generate_member_code(cursor, branch_id):
    """Generate next member code (BranchID + sequential number)
    Example: If BranchID=1, generates 10001, 10002, 10003...
             If BranchID=2, generates 20001, 20002, 20003...
    """
    try:
        # Get the last member code for this branch
        cursor.execute("""
            SELECT TOP 1 member_code 
            FROM Members 
            WHERE BranchId = ? 
            AND member_code LIKE ?
            ORDER BY member_code DESC
        """, (branch_id, str(branch_id) + '%'))
        
        result = cursor.fetchone()
        if result and result[0]:
            last_code = result[0]
            try:
                # Extract number and increment
                num = int(last_code) + 1
                return str(num)
            except:
                # Fallback if parsing fails
                return str('UD') + str(branch_id) + "0001"
        else:
            # First member for this branch
            return str(branch_id) + "0001"
    except Exception as e:
        logger.error(f"Error generating member code: {e}")
        return str(branch_id) + "0001"

@members_bp.route("/", methods=["GET"])
@login_required
def index():
    """Display all members"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                m.id, m.member_code, m.full_name, m.phone1, m.email,
                m.status, m.join_date, m.city, m.district,
                c.center_name, c.center_no
            FROM Members m
            LEFT JOIN Center c ON m.center_id = c.id
            WHERE m.BranchId = ?
            ORDER BY m.member_code DESC
        """, (session.get('branchid', 1),))
        
        members = cursor.fetchall()
        conn.close()
        
        return render_template("members.html", members=members)
        
    except Exception as e:
        logger.error(f"Error fetching members: {e}")
        flash("Error loading members list", "danger")
        return render_template("members.html", members=[])

@members_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_member():
    """Add new member"""
    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            branch_id = session.get('branchid', 1)
            member_code = generate_member_code(cursor, branch_id)
            
            # Get form data
            data = {
                'member_code': member_code,
                'BranchId': branch_id,
                'center_id': request.form.get('center_id'),
                'group_id': request.form.get('group_id'),
                'full_name': request.form['full_name'].strip(),
                'join_date': request.form.get('join_date') or date.today(),
                'dob': request.form.get('dob', None) or None,
                'age': request.form.get('age', None) or None,
                'gender': request.form.get('gender', ''),
                'marital_status': request.form.get('marital_status', ''),
                'guardian_name': request.form.get('guardian_name', '').strip(),
                'spouse_name': request.form.get('spouse_name', '').strip(),
                'phone1': request.form.get('phone1', '').strip(),
                'phone2': request.form.get('phone2', '').strip(),
                'email': request.form.get('email', '').strip(),
                'aadhaar': request.form.get('aadhaar', '').strip(),
                'address1': request.form.get('address1', '').strip(),
                'address2': request.form.get('address2', '').strip(),
                'city': request.form.get('city', '').strip(),
                'mandal': request.form.get('mandal', '').strip(),
                'district': request.form.get('district', '').strip(),
                'state': request.form.get('state', '').strip(),
                'pincode': request.form.get('pincode', '').strip(),
                'monthly_income': request.form.get('monthly_income', 0) or 0,
                'expenditure': request.form.get('expenditure', 0) or 0,
                'status': request.form.get('status', 'ACTIVE'),
                'nominee_name': request.form.get('nominee_name', '').strip(),
                'nominee_relation': request.form.get('nominee_relation', '').strip(),
                'nominee_dob': request.form.get('nominee_dob', None) or None,
                'nominee_age': request.form.get('nominee_age', None) or None,
                'nominee_phone': request.form.get('nominee_phone', '').strip(),
                'nominee_aadhaar': request.form.get('nominee_aadhaar', '').strip(),
                'nominee_address1': request.form.get('nominee_address1', '').strip(),
                'nominee_address2': request.form.get('nominee_address2', '').strip(),
                'nominee_city': request.form.get('nominee_city', '').strip(),
                'nominee_mandal': request.form.get('nominee_mandal', '').strip(),
                'nominee_district': request.form.get('nominee_district', '').strip(),
                'nominee_state': request.form.get('nominee_state', '').strip(),
                'nominee_pincode': request.form.get('nominee_pincode', '').strip(),
                'create_staff': session.get('emp_name', '')
            }
            
            # Validate required fields
            if not data['full_name']:
                flash("Member Name is required", "warning")
                return redirect(url_for("members_bp.add_member"))
            
            if not data['center_id']:
                flash("Center is required", "warning")
                return redirect(url_for("members_bp.add_member"))
            
            # Insert member
            cursor.execute("""
                INSERT INTO Members (
                    member_code, BranchId, center_id,group_id, full_name, join_date, dob, age, 
                    gender, marital_status, guardian_name, spouse_name, phone1, phone2, 
                    email, aadhaar, address1, address2, city, mandal, district, state, 
                    pincode, monthly_income, expenditure, status, nominee_name, 
                    nominee_relation, nominee_dob, nominee_age, nominee_phone, 
                    nominee_aadhaar, nominee_address1, nominee_address2, nominee_city, 
                    nominee_mandal, nominee_district, nominee_state, nominee_pincode,
                    create_staff, created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE()
                )
            """, (
                data['member_code'], data['BranchId'], data['center_id'], data['group_id'],
                data['full_name'], data['join_date'], data['dob'], data['age'],
                data['gender'], data['marital_status'], data['guardian_name'], 
                data['spouse_name'], data['phone1'], data['phone2'], data['email'],
                data['aadhaar'], data['address1'], data['address2'], data['city'],
                data['mandal'], data['district'], data['state'], data['pincode'],
                data['monthly_income'], data['expenditure'], data['status'],
                data['nominee_name'], data['nominee_relation'], data['nominee_dob'],
                data['nominee_age'], data['nominee_phone'], data['nominee_aadhaar'],
                data['nominee_address1'], data['nominee_address2'], data['nominee_city'],
                data['nominee_mandal'], data['nominee_district'], data['nominee_state'],
                data['nominee_pincode'], data['create_staff']
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"New member added: {data['full_name']} ({member_code})")
            flash(f"Member {data['full_name']} added successfully! Member Code: {member_code}", "success")
            return redirect(url_for("members_bp.index"))
            
        except Exception as e:
            logger.error(f"Error adding member: {e}")
            flash(f"Error adding member: {str(e)}", "danger")
    
    # GET request - fetch centers
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get centers for this branch
        cursor.execute("""
            SELECT id, center_no, center_name 
            FROM Center 
            WHERE branchid = ?
            AND (close_date IS NULL OR close_date > GETDATE())
            ORDER BY center_no
        """, (session.get('branchid', 1),))
        centers = cursor.fetchall()
        
        # Generate next member code
        next_member_code = generate_member_code(cursor, session.get('branchid', 1))
        
        # Get current date
        current_date = date.today().strftime('%Y-%m-%d')
        
        conn.close()
        
        return render_template("members_add.html", 
                             centers=centers,
                             next_member_code=next_member_code,
                             current_date=current_date)
    except Exception as e:
        logger.error(f"Error loading add form: {e}")
        flash(f"Error loading form: {str(e)}", "danger")
        return render_template("members_add.html", 
                             centers=[], 
                             next_member_code="10001",
                             current_date=date.today().strftime('%Y-%m-%d'))

@members_bp.route("/edit/<int:member_id>", methods=["GET", "POST"])
@login_required
def edit_member(member_id):
    """Edit member details"""
    if session.get("role") not in ["Admin", "Manager"]:
        flash("You do not have permission to edit members", "danger")
        return redirect(url_for("members_bp.index"))


    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get form data
            data = {
                'center_id': request.form.get('center_id'),
                'group_id': request.form.get('group_id'),
                'full_name': request.form['full_name'].strip(),
                'join_date': request.form.get('join_date'),
                'dob': request.form.get('dob', None) or None,
                'age': request.form.get('age', None) or None,
                'gender': request.form.get('gender', ''),
                'marital_status': request.form.get('marital_status', ''),
                'guardian_name': request.form.get('guardian_name', '').strip(),
                'spouse_name': request.form.get('spouse_name', '').strip(),
                'phone1': request.form.get('phone1', '').strip(),
                'phone2': request.form.get('phone2', '').strip(),
                'email': request.form.get('email', '').strip(),
                'aadhaar': request.form.get('aadhaar', '').strip(),
                'address1': request.form.get('address1', '').strip(),
                'address2': request.form.get('address2', '').strip(),
                'city': request.form.get('city', '').strip(),
                'mandal': request.form.get('mandal', '').strip(),
                'district': request.form.get('district', '').strip(),
                'state': request.form.get('state', '').strip(),
                'pincode': request.form.get('pincode', '').strip(),
                'monthly_income': request.form.get('monthly_income', 0) or 0,
                'expenditure': request.form.get('expenditure', 0) or 0,
                'status': request.form.get('status', 'ACTIVE'),
                'nominee_name': request.form.get('nominee_name', '').strip(),
                'nominee_relation': request.form.get('nominee_relation', '').strip(),
                'nominee_dob': request.form.get('nominee_dob', None) or None,
                'nominee_age': request.form.get('nominee_age', None) or None,
                'nominee_phone': request.form.get('nominee_phone', '').strip(),
                'nominee_aadhaar': request.form.get('nominee_aadhaar', '').strip(),
                'nominee_address1': request.form.get('nominee_address1', '').strip(),
                'nominee_address2': request.form.get('nominee_address2', '').strip(),
                'nominee_city': request.form.get('nominee_city', '').strip(),
                'nominee_mandal': request.form.get('nominee_mandal', '').strip(),
                'nominee_district': request.form.get('nominee_district', '').strip(),
                'nominee_state': request.form.get('nominee_state', '').strip(),
                'nominee_pincode': request.form.get('nominee_pincode', '').strip()
            }
            
            # Update member
            cursor.execute("""
                UPDATE Members SET
                    center_id=?,group_id=?, full_name=?, join_date=?, dob=?, age=?, gender=?,
                    marital_status=?, guardian_name=?, spouse_name=?, phone1=?, phone2=?,
                    email=?, aadhaar=?, address1=?, address2=?, city=?, mandal=?,
                    district=?, state=?, pincode=?, monthly_income=?, expenditure=?,
                    status=?, nominee_name=?, nominee_relation=?, nominee_dob=?,
                    nominee_age=?, nominee_phone=?, nominee_aadhaar=?, nominee_address1=?,
                    nominee_address2=?, nominee_city=?, nominee_mandal=?, nominee_district=?,
                    nominee_state=?, nominee_pincode=?, updated_at=GETDATE()
                WHERE id=?
            """, (
                data['center_id'],data['group_id'],data['full_name'], data['join_date'], data['dob'],
                data['age'], data['gender'], data['marital_status'], data['guardian_name'],
                data['spouse_name'], data['phone1'], data['phone2'], data['email'],
                data['aadhaar'], data['address1'], data['address2'], data['city'],
                data['mandal'], data['district'], data['state'], data['pincode'],
                data['monthly_income'], data['expenditure'], data['status'],
                data['nominee_name'], data['nominee_relation'], data['nominee_dob'],
                data['nominee_age'], data['nominee_phone'], data['nominee_aadhaar'],
                data['nominee_address1'], data['nominee_address2'], data['nominee_city'],
                data['nominee_mandal'], data['nominee_district'], data['nominee_state'],
                data['nominee_pincode'], member_id
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Member updated: {member_id}")
            flash("Member updated successfully!", "success")
            return redirect(url_for("members_bp.index"))
            
        except Exception as e:
            logger.error(f"Error updating member: {e}")
            flash(f"Error updating member: {str(e)}", "danger")
    
    # GET request
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get member details
        cursor.execute("SELECT * FROM Members WHERE id = ?", (member_id,))
        member = cursor.fetchone()
        
        if not member:
            flash("Member not found", "warning")
            return redirect(url_for("members_bp.index"))
        
        # Get centers for this branch
        cursor.execute("""
            SELECT id, center_no, center_name 
            FROM Center 
            WHERE branchid = ?
            ORDER BY center_no
        """, (session.get('branchid', 1),))
        centers = cursor.fetchall()
        
        conn.close()
        
        return render_template("members_edit.html", member=member, centers=centers)
        
    except Exception as e:
        logger.error(f"Error loading member: {e}")
        flash(f"Error loading member details: {str(e)}", "danger")
        return redirect(url_for("members_bp.index"))

@members_bp.route("/delete/<int:member_id>", methods=["POST"])
@login_required
def delete_member(member_id):
    """Deactivate member (only if balances are zero)"""
    # 1️⃣ ROLE PERMISSION CHECK
    if session.get("role") not in ["Admin", "Manager"]:
        flash("You do not have permission to deactivate members", "danger")
        return redirect(url_for("members_bp.index"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get member_code
        cursor.execute("SELECT member_code FROM Members WHERE id = ?", (member_id,))
        row = cursor.fetchone()

        if not row:
            flash("Member not found", "danger")
            return redirect(url_for("members_bp.index"))

        member_code = row[0]

        # Loan Outstanding
        cursor.execute("""
            SELECT ISNULL(SUM(principaloutstanding + interestoutstanding),0)
            FROM Loans
            WHERE member_code=? AND loanstatus <> 'Closed'
        """, (member_code,))
        loan_balance = cursor.fetchone()[0]

        # Savings Balance
        cursor.execute("""
        SELECT ISNULL(SUM(
            CASE 
                WHEN credit_debit='Credit' THEN amount
                WHEN credit_debit='Debit' THEN -amount
            END
        ),0)
        FROM savings
        WHERE member_code=?
        """, (member_code,))
        savings_balance = cursor.fetchone()[0]

        # Security Deposit Balance
        cursor.execute("""
            SELECT ISNULL(SUM(securitydepositamount - securitydepositwithdrawn),0)
            FROM Loans
            WHERE member_code=?
        """, (member_code,))
        deposit_balance = cursor.fetchone()[0]

        # Advance Balance
        cursor.execute("""
            SELECT ISNULL(SUM(advbalance),0)
            FROM Loans
            WHERE member_code=?
        """, (member_code,))
        advance_balance = cursor.fetchone()[0]

        # Validation
        if loan_balance > 0 or savings_balance > 0 or deposit_balance > 0 or advance_balance > 0:

            flash(
                f"Member cannot be deactivated. "
                f"Loan:{loan_balance} Savings:{savings_balance} "
                f"Deposit:{deposit_balance} Advance:{advance_balance}",
                "warning"
            )
            conn.close()
            return redirect(url_for("members_bp.index"))

        # Deactivate member
        cursor.execute("""
            UPDATE Members
            SET status='INACTIVE', updated_at=GETDATE()
            WHERE id=?
        """, (member_id,))

        conn.commit()
        conn.close()

        logger.info(f"Member deactivated: {member_id}")
        flash("Member deactivated successfully!", "success")

    except Exception as e:
        logger.error(f"Error deactivating member: {e}")
        flash(f"Error deactivating member: {str(e)}", "danger")
        if session.get("role") not in ["Admin", "Manager"]:
            flash("You do not have permission to deactivate members", "danger")




    return redirect(url_for("members_bp.index"))

