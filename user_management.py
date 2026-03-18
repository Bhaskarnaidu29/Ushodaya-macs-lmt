# user_management.py - CORRECTED FOR YOUR DATABASE SCHEMA
# Updated to use: username, password, BranchId, RoleID, active, etc.

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from datetime import datetime

user_mgmt_bp = Blueprint("user_mgmt", __name__, template_folder="templates")


def superadmin_required(f):
    """Decorator to require SuperAdmin access."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login.login"))
        
        if not session.get("is_superadmin", False):
            flash("Access denied. SuperAdmin privileges required.", "danger")
            return redirect(url_for("home"))
        
        return f(*args, **kwargs)
    return decorated_function


@user_mgmt_bp.route("/", methods=["GET"])
@superadmin_required
def user_list():
    """List all users - CORRECTED SCHEMA."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # ✅ CORRECTED: Use actual column names
        cursor.execute("""
            SELECT 
                u.id,                                   -- User ID
                u.username,                             -- Username
                r.RoleName,                             -- Role Name
                b.Name AS branch_name,                  -- Branch Name
                u.active,                               -- Active (bit: 1/0)
                u.created_at,                           -- Created date
                u.BranchId,                             -- Branch ID
                u.RoleID,                               -- Role ID
                u.emp_name                              -- Employee name
            FROM Users u
            LEFT JOIN Roles r ON u.RoleID = r.RoleID
            LEFT JOIN Branches b ON u.BranchId = b.Id
            ORDER BY u.username
        """)
        users = cursor.fetchall()
        
        return render_template("user_management.html", users=users)
    
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return render_template("user_management.html", users=[])
    
    finally:
        conn.close()


@user_mgmt_bp.route("/add", methods=["GET", "POST"])
@superadmin_required
def add_user():
    """Add new user - CORRECTED SCHEMA."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # ✅ CORRECTED: Get roles
        cursor.execute("SELECT RoleID, RoleName FROM Roles WHERE IsActive = 1 ORDER BY RoleName")
        roles = cursor.fetchall()
        
        # ✅ CORRECTED: Get branches
        cursor.execute("SELECT Id, Code, Name FROM Branches ORDER BY Name")
        branches = cursor.fetchall()
        
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            emp_name = request.form.get("emp_name")
            role_id = request.form.get("role_id")
            branch_id = request.form.get("branch_id")
            active = request.form.get("active", "1")
            
            if not all([username, password, role_id]):
                flash("Username, password, and role are required.", "warning")
                return render_template("add_user.html", roles=roles, branches=branches)
            
            # Check if username exists
            cursor.execute("SELECT id FROM Users WHERE username = ?", (username,))
            if cursor.fetchone():
                flash(f"Username '{username}' already exists. Please choose another.", "danger")
                return render_template("add_user.html", roles=roles, branches=branches)
            
            # ✅ CORRECTED: Check if role is SuperAdmin
            cursor.execute("SELECT is_superadmin FROM Roles WHERE RoleID = ?", (role_id,))
            role_info = cursor.fetchone()
            is_superadmin_role = role_info[0] if role_info else False
            
            # If SuperAdmin role, set BranchId to NULL
            if is_superadmin_role:
                branch_id = None
            
            # ✅ CORRECTED: Get role name
            cursor.execute("SELECT RoleName FROM Roles WHERE RoleID = ?", (role_id,))
            role_name_row = cursor.fetchone()
            role_name = role_name_row[0] if role_name_row else ""
            
            # ✅ Hash the password before storing
            from werkzeug.security import generate_password_hash
            hashed_password = generate_password_hash(password, method='scrypt')
            
            # ✅ CORRECTED: Insert user with correct column names
            cursor.execute("""
                INSERT INTO Users (
                    username, password, emp_name, RoleID, role_id, role,
                    BranchId, active, created_at, ModifiedDate
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), GETDATE())
            """, (username, hashed_password, emp_name or username, role_id, role_id, 
                  role_name, branch_id, int(active)))
            
            conn.commit()
            flash(f"✅ User '{username}' created successfully!", "success")
            return redirect(url_for("user_mgmt.user_list"))
        
        return render_template("add_user.html", roles=roles, branches=branches)
    
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return render_template("add_user.html", roles=[], branches=[])
    
    finally:
        conn.close()


@user_mgmt_bp.route("/edit/<int:user_id>", methods=["GET", "POST"])
@superadmin_required
def edit_user(user_id):
    """Edit existing user - CORRECTED SCHEMA."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # ✅ CORRECTED: Get user details
        cursor.execute("""
            SELECT id, username, password, emp_name, RoleID, BranchId, active
            FROM Users WHERE id = ?
        """, (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("user_mgmt.user_list"))
        
        # Get roles
        cursor.execute("SELECT RoleID, RoleName FROM Roles WHERE IsActive = 1 ORDER BY RoleName")
        roles = cursor.fetchall()
        
        # Get branches
        cursor.execute("SELECT Id, Code, Name FROM Branches ORDER BY Name")
        branches = cursor.fetchall()
        
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            emp_name = request.form.get("emp_name")
            role_id = request.form.get("role_id")
            branch_id = request.form.get("branch_id")
            active = request.form.get("active")
            
            if not all([username, role_id, active is not None]):
                flash("Username, role, and status are required.", "warning")
                return render_template("edit_user.html", user=user, roles=roles, branches=branches)
            
            # Check if username exists (excluding current user)
            cursor.execute("SELECT id FROM Users WHERE username = ? AND id != ?", (username, user_id))
            if cursor.fetchone():
                flash(f"Username '{username}' already exists. Please choose another.", "danger")
                return render_template("edit_user.html", user=user, roles=roles, branches=branches)
            
            # ✅ CORRECTED: Check if role is SuperAdmin
            cursor.execute("SELECT is_superadmin FROM Roles WHERE RoleID = ?", (role_id,))
            role_info = cursor.fetchone()
            is_superadmin_role = role_info[0] if role_info else False
            
            # If SuperAdmin role, set BranchId to NULL
            if is_superadmin_role:
                branch_id = None
            
            # Get role name
            cursor.execute("SELECT RoleName FROM Roles WHERE RoleID = ?", (role_id,))
            role_name_row = cursor.fetchone()
            role_name = role_name_row[0] if role_name_row else ""
            
            # ✅ CORRECTED: Update user
            if password:
                # Password provided, hash it before updating
                from werkzeug.security import generate_password_hash
                hashed_password = generate_password_hash(password, method='scrypt')
                
                cursor.execute("""
                    UPDATE Users
                    SET username = ?, password = ?, emp_name = ?, 
                        RoleID = ?, role_id = ?, role = ?,
                        BranchId = ?, active = ?, ModifiedDate = GETDATE()
                    WHERE id = ?
                """, (username, hashed_password, emp_name or username, 
                      role_id, role_id, role_name, branch_id, int(active), user_id))
            else:
                # No password, don't update it
                cursor.execute("""
                    UPDATE Users
                    SET username = ?, emp_name = ?, 
                        RoleID = ?, role_id = ?, role = ?,
                        BranchId = ?, active = ?, ModifiedDate = GETDATE()
                    WHERE id = ?
                """, (username, emp_name or username, 
                      role_id, role_id, role_name, branch_id, int(active), user_id))
            
            conn.commit()
            flash(f"✅ User '{username}' updated successfully!", "success")
            return redirect(url_for("user_mgmt.user_list"))
        
        return render_template("edit_user.html", user=user, roles=roles, branches=branches)
    
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return redirect(url_for("user_mgmt.user_list"))
    
    finally:
        conn.close()


@user_mgmt_bp.route("/delete/<int:user_id>", methods=["POST"])
@superadmin_required
def delete_user(user_id):
    """Delete user - CORRECTED SCHEMA."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Don't allow deleting yourself
        if user_id == session.get("user_id"):
            flash("You cannot delete your own account.", "danger")
            return redirect(url_for("user_mgmt.user_list"))
        
        # Get username before deleting
        cursor.execute("SELECT username FROM Users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("user_mgmt.user_list"))
        
        username = user[0]
        
        # Delete user
        cursor.execute("DELETE FROM Users WHERE id = ?", (user_id,))
        
        conn.commit()
        flash(f"✅ User '{username}' deleted successfully!", "success")
        
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
    
    finally:
        conn.close()
    
    return redirect(url_for("user_mgmt.user_list"))
