"""
Employee Management Module
Handles employee CRUD operations with Employee, Users, and Roles tables
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, date
import calendar
from db import get_db_connection
from login import login_required
import logging
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

employee_bp = Blueprint("employee", __name__, template_folder="templates")

def hash_password(password):
    """Hash using werkzeug pbkdf2 — same format login.py already verifies"""
    return generate_password_hash(password)

def add_months(src_date, months):
    """Add N months to a date (no external libraries needed)"""
    month = src_date.month - 1 + months
    year  = src_date.year + month // 12
    month = month % 12 + 1
    day   = min(src_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def generate_emp_code(cursor, branch_id):
    cursor.execute("""
        SELECT MAX(CAST(SUBSTRING(EmpCode, 4, 10) AS INT))
        FROM Employee
        WHERE EmpCode LIKE 'UDE%'
    """)

    result = cursor.fetchone()

    if result and result[0]:
        next_num = result[0] + 1
    else:
        next_num = 1

    return f"UDE{next_num:03d}"

@employee_bp.route("/", methods=["GET"])
@login_required
def index():
    """Display all employees"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                e.EmpID, e.EmpCode, e.EmpName, e.Designation, e.Department, 
                e.MobileNo, e.Email, e.Role, e.DOJ, e.Salary, e.WithdrawDate,
                u.username, u.expire
            FROM Employee e
            LEFT JOIN Users u ON e.EmpCode = u.emp_code
            WHERE e.BranchId = ?
            ORDER BY e.EmpName
        """, (session.get('branchid', 1),))
        
        employees = cursor.fetchall()
        conn.close()
        
        return render_template("employee.html", employees=employees)
        
    except Exception as e:
        logger.error(f"Error fetching employees: {e}")
        flash("Error loading employees list", "danger")
        return render_template("employee.html", employees=[])

@employee_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_employee():
    """Add new employee"""
    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            branch_id = session.get('branchid', 1)
            emp_code = generate_emp_code(cursor, branch_id)

            # Username auto = EmpCode lowercase
            auto_username = emp_code.lower()

            # Expire = DOJ + 6 months
            doj_str = request.form.get('doj', '').strip() or None
            if doj_str:
                try:
                    doj_date   = datetime.strptime(doj_str, '%Y-%m-%d').date()
                    expire_val = add_months(doj_date, 6).strftime('%Y-%m-%d')
                except Exception:
                    expire_val = request.form.get('expire', None) or None
            else:
                expire_val = request.form.get('expire', None) or None

            data = {
                'emp_code':      emp_code,
                'username':      auto_username,
                'emp_name':      request.form['emp_name'].strip(),
                'father_name':   request.form.get('father_name', '').strip(),
                'gender':        request.form.get('gender', ''),
                'dob':           request.form.get('dob', None) or None,
                'doj':           doj_str,
                'designation':   request.form.get('designation', '').strip(),
                'department':    request.form.get('department', '').strip(),
                'qualification': request.form.get('qualification', '').strip(),
                'experience':    request.form.get('experience', '').strip(),
                'address':       request.form.get('address', '').strip(),
                'mobile_no':     request.form.get('mobile_no', '').strip(),
                'email':         request.form.get('email', '').strip(),
                'aadhar_no':     request.form.get('aadhar_no', '').strip(),
                'pan_no':        request.form.get('pan_no', '').strip(),
                'bank_name':     request.form.get('bank_name', '').strip(),
                'account_no':    request.form.get('account_no', '').strip(),
                'ifsc_code':     request.form.get('ifsc_code', '').strip(),
                'salary':        request.form.get('salary', 0) or 0,
                'password':      request.form.get('password', '').strip(),
                'role_id':       request.form.get('role_id', 2),
                'expire':        expire_val,
                'branch_id':     branch_id,
            }
            
            if not data['emp_name']:
                flash("Employee Name is required", "warning")
                return redirect(url_for("employee.add_employee"))

            if not data['password']:
                flash("Password is required", "warning")
                return redirect(url_for("employee.add_employee"))
            
            cursor.execute("SELECT id FROM Users WHERE username = ?", (data['username'],))
            if cursor.fetchone():
                flash("Username already exists", "warning")
                conn.close()
                return redirect(url_for("employee.add_employee"))
            
            cursor.execute("SELECT RoleName FROM Roles WHERE RoleID = ?", (data['role_id'],))
            role_row = cursor.fetchone()
            role_name = role_row[0] if role_row else 'Employee'
            
            hashed_password = hash_password(data['password'])
            
            cursor.execute("""
                INSERT INTO Employee (
                    EmpCode, EmpName, FatherName, Gender, DOB, DOJ, Designation, Department,
                    Qualification, Experience, Address, MobileNo, Email, AadharNo, PANNo,
                    BankName, AccountNo, IFSCCode, Salary, Password, Role, CreatedAt, BranchId
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)
            """, (
                data['emp_code'], data['emp_name'], data['father_name'], data['gender'],
                data['dob'], data['doj'], data['designation'], data['department'],
                data['qualification'], data['experience'], data['address'], data['mobile_no'],
                data['email'], data['aadhar_no'], data['pan_no'], data['bank_name'],
                data['account_no'], data['ifsc_code'], data['salary'], hashed_password,
                role_name, data['branch_id']
            ))
            
            cursor.execute("""
                INSERT INTO Users (
                    username, password, emp_code, emp_name, address, 
                    role, RoleID, expire, created_at, BranchId
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?)
            """, (
                data['username'], hashed_password, data['emp_code'], data['emp_name'],
                data['address'], role_name, data['role_id'], data['expire'], 
                data['branch_id']
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"New employee added: {data['emp_name']} ({emp_code})")
            flash(f"Employee {data['emp_name']} added successfully! Code: {emp_code}", "success")
            return redirect(url_for("employee.index"))
            
        except Exception as e:
            logger.error(f"Error adding employee: {e}")
            flash(f"Error adding employee: {str(e)}", "danger")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Fetch roles - using actual column names
        cursor.execute("SELECT RoleID, RoleName, Description FROM Roles WHERE IsActive = 1 ORDER BY RoleName")
        roles = cursor.fetchall()
        
        # Generate next emp code
        next_emp_code = generate_emp_code(cursor, session.get('branchid', 1))
        
        conn.close()
        
        # If no roles found, create default ones or show error
        if not roles:
            logger.warning("No active roles found in database")
            flash("Warning: No roles configured. Please add roles first.", "warning")
        
        today_str      = date.today().strftime('%Y-%m-%d')
        expire_default = add_months(date.today(), 6).strftime('%Y-%m-%d')
        return render_template("employee_add.html", roles=roles, next_emp_code=next_emp_code,
                               today=today_str, expire_default=expire_default)
    except Exception as e:
        logger.error(f"Error loading add form: {e}")
        flash(f"Error loading form: {str(e)}", "danger")
        return render_template("employee_add.html", roles=[], next_emp_code="UDE001", today=date.today().strftime("%Y-%m-%d"), expire_default=add_months(date.today(), 6).strftime("%Y-%m-%d"))

@employee_bp.route("/edit/<int:emp_id>", methods=["GET", "POST"])
@login_required
def edit_employee(emp_id):
    """Edit employee details"""
    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            data = {
                'emp_name': request.form['emp_name'].strip(),
                'father_name': request.form.get('father_name', '').strip(),
                'gender': request.form.get('gender', ''),
                'dob': request.form.get('dob', None) or None,
                'doj': request.form.get('doj', None) or None,
                'designation': request.form.get('designation', '').strip(),
                'department': request.form.get('department', '').strip(),
                'qualification': request.form.get('qualification', '').strip(),
                'experience': request.form.get('experience', '').strip(),
                'address': request.form.get('address', '').strip(),
                'mobile_no': request.form.get('mobile_no', '').strip(),
                'email': request.form.get('email', '').strip(),
                'aadhar_no': request.form.get('aadhar_no', '').strip(),
                'pan_no': request.form.get('pan_no', '').strip(),
                'bank_name': request.form.get('bank_name', '').strip(),
                'account_no': request.form.get('account_no', '').strip(),
                'ifsc_code': request.form.get('ifsc_code', '').strip(),
                'salary': request.form.get('salary', 0) or 0,
                'password': request.form.get('password', '').strip(),
                'role_id': request.form.get('role_id', 2),
                'username': request.form.get('username', '').strip(),
                'expire': request.form.get('expire', None) or None,
                'modified_by': session.get('empid'),
            }
            
            cursor.execute("SELECT EmpCode FROM Employee WHERE EmpID = ?", (emp_id,))
            emp_row = cursor.fetchone()
            if not emp_row:
                flash("Employee not found", "warning")
                return redirect(url_for("employee.index"))
            emp_code = emp_row[0]
            
            cursor.execute("SELECT RoleName FROM Roles WHERE RoleID = ?", (data['role_id'],))
            role_row = cursor.fetchone()
            role_name = role_row[0] if role_row else 'Employee'
            
            if data['password']:
                hashed_password = hash_password(data['password'])
                cursor.execute("""
                    UPDATE Employee SET
                        EmpName = ?, FatherName = ?, Gender = ?, DOB = ?, DOJ = ?,
                        Designation = ?, Department = ?, Qualification = ?, Experience = ?,
                        Address = ?, MobileNo = ?, Email = ?, AadharNo = ?, PANNo = ?,
                        BankName = ?, AccountNo = ?, IFSCCode = ?, Salary = ?, Password = ?,
                        Role = ?, ModifiedBy = ?, ModifiedDate = GETDATE()
                    WHERE EmpID = ?
                """, (
                    data['emp_name'], data['father_name'], data['gender'],
                    data['dob'], data['doj'], data['designation'], data['department'],
                    data['qualification'], data['experience'], data['address'], data['mobile_no'],
                    data['email'], data['aadhar_no'], data['pan_no'], data['bank_name'],
                    data['account_no'], data['ifsc_code'], data['salary'], hashed_password,
                    role_name, data['modified_by'], emp_id
                ))
                
                cursor.execute("""
                    UPDATE Users SET
                        username = ?, password = ?, emp_name = ?, address = ?,
                        role = ?, RoleID = ?, expire = ?,
                        ModifiedBy = ?, ModifiedDate = GETDATE()
                    WHERE emp_code = ?
                """, (
                    data['username'], hashed_password, data['emp_name'], data['address'],
                    role_name, data['role_id'], data['expire'],
                    data['modified_by'], emp_code
                ))
            else:
                cursor.execute("""
                    UPDATE Employee SET
                        EmpName = ?, FatherName = ?, Gender = ?, DOB = ?, DOJ = ?,
                        Designation = ?, Department = ?, Qualification = ?, Experience = ?,
                        Address = ?, MobileNo = ?, Email = ?, AadharNo = ?, PANNo = ?,
                        BankName = ?, AccountNo = ?, IFSCCode = ?, Salary = ?,
                        Role = ?, ModifiedBy = ?, ModifiedDate = GETDATE()
                    WHERE EmpID = ?
                """, (
                    data['emp_name'], data['father_name'], data['gender'],
                    data['dob'], data['doj'], data['designation'], data['department'],
                    data['qualification'], data['experience'], data['address'], data['mobile_no'],
                    data['email'], data['aadhar_no'], data['pan_no'], data['bank_name'],
                    data['account_no'], data['ifsc_code'], data['salary'],
                    role_name, data['modified_by'], emp_id
                ))
                
                cursor.execute("""
                    UPDATE Users SET
                        username = ?, emp_name = ?, address = ?,
                        role = ?, RoleID = ?, expire = ?,
                        ModifiedBy = ?, ModifiedDate = GETDATE()
                    WHERE emp_code = ?
                """, (
                    data['username'], data['emp_name'], data['address'],
                    role_name, data['role_id'], data['expire'],
                    data['modified_by'], emp_code
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Employee updated: {emp_id}")
            flash("Employee updated successfully!", "success")
            return redirect(url_for("employee.index"))
            
        except Exception as e:
            logger.error(f"Error updating employee: {e}")
            flash(f"Error updating employee: {str(e)}", "danger")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get employee details with all columns explicitly named
        cursor.execute("""
            SELECT 
                e.EmpID, e.EmpCode, e.EmpName, e.FatherName, e.Gender, 
                e.DOB, e.DOJ, e.Designation, e.Department, e.Qualification, 
                e.Experience, e.Address, e.MobileNo, e.Email, e.AadharNo, 
                e.PANNo, e.BankName, e.AccountNo, e.IFSCCode, e.Salary, 
                e.Password, e.Role, e.CreatedAt, e.WithdrawDate, e.BranchId,
                u.username, u.expire, u.RoleID
            FROM Employee e
            LEFT JOIN Users u ON e.EmpCode = u.emp_code
            WHERE e.EmpID = ?
        """, (emp_id,))
        
        employee_row = cursor.fetchone()
        
        if not employee_row:
            flash("Employee not found", "warning")
            conn.close()
            return redirect(url_for("employee.index"))
        
        # Convert to dictionary for easier template access
        columns = [
            'EmpID', 'EmpCode', 'EmpName', 'FatherName', 'Gender',
            'DOB', 'DOJ', 'Designation', 'Department', 'Qualification',
            'Experience', 'Address', 'MobileNo', 'Email', 'AadharNo',
            'PANNo', 'BankName', 'AccountNo', 'IFSCCode', 'Salary',
            'Password', 'Role', 'CreatedAt', 'WithdrawDate', 'BranchId',
            'username', 'expire', 'RoleID'
        ]
        
        # Convert to dictionary-like object for easier template access
        class EmployeeData:
            def __init__(self, row, columns):
                for i, col in enumerate(columns):
                    setattr(self, col, row[i] if i < len(row) else None)
            
            def __getitem__(self, key):
                return getattr(self, key, None)
            
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        employee = EmployeeData(employee_row, columns)
        
        # Get available roles
        cursor.execute("SELECT RoleID, RoleName, Description FROM Roles WHERE IsActive = 1 ORDER BY RoleName")
        roles = cursor.fetchall()
        
        conn.close()
        
        return render_template("employee_edit.html", employee=employee, roles=roles)
        
    except Exception as e:
        logger.error(f"Error loading employee for edit: {e}")
        flash(f"Error loading employee details: {str(e)}", "danger")
        return redirect(url_for("employee.index"))

@employee_bp.route("/delete/<int:emp_id>", methods=["POST"])
@login_required
def delete_employee(emp_id):
    """Mark employee as withdrawn"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT EmpCode FROM Employee WHERE EmpID = ?", (emp_id,))
        emp_row = cursor.fetchone()
        if not emp_row:
            flash("Employee not found", "warning")
            return redirect(url_for("employee.index"))
        
        emp_code = emp_row[0]
        
        cursor.execute("""
            UPDATE Employee 
            SET WithdrawDate = GETDATE(), ModifiedBy = ?, ModifiedDate = GETDATE()
            WHERE EmpID = ?
        """, (session.get('empid'), emp_id))
        
        cursor.execute("""
            UPDATE Users 
            SET expire = CAST(GETDATE() AS DATE), ModifiedBy = ?, ModifiedDate = GETDATE()
            WHERE emp_code = ?
        """, (session.get('empid'), emp_code))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Employee withdrawn: {emp_id}")
        flash("Employee marked as withdrawn!", "success")
        
    except Exception as e:
        logger.error(f"Error withdrawing employee: {e}")
        flash(f"Error: {str(e)}", "danger")
    
    return redirect(url_for("employee.index"))
