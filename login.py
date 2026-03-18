# login.py - CORRECTED FOR YOUR DATABASE SCHEMA
# Updated to use: username, password, BranchId, RoleID, active, etc.

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from functools import wraps
from db import get_db_connection
import datetime

login_bp = Blueprint("login", __name__, template_folder="templates")


def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("login.login"))
        return f(*args, **kwargs)
    return decorated_function


def superadmin_required(f):
    """Decorator to require SuperAdmin access."""
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


@login_bp.route("/", methods=["GET", "POST"])
def login():
    """Login page with SuperAdmin support - CORRECTED SCHEMA."""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Please enter both username and password.", "warning")
            return render_template("login.html")

        conn = get_db_connection()
        try:
            cursor = conn.cursor()

            # ✅ CORRECTED: Use actual column names
            cursor.execute("""
                SELECT 
                    u.id,                               -- User ID
                    u.username,                         -- Login username
                    u.password,                         -- Password
                    u.BranchId,                         -- Branch ID (capital B)
                    u.RoleID,                           -- Role ID (capital R, I)
                    r.RoleName,                         -- Role Name (capital R, N)
                    r.is_superadmin,                    -- SuperAdmin flag
                    r.can_access_all_branches,          -- Multi-branch access
                    b.Name AS branch_name,              -- Branch name
                    u.emp_name,                         -- Employee name
                    u.active                            -- Active status (bit)
                FROM Users u
                LEFT JOIN Roles r ON u.RoleID = r.RoleID
                LEFT JOIN Branches b ON u.BranchId = b.Id
                WHERE u.username = ? AND u.active = 1
            """, (username,))
            
            user = cursor.fetchone()

            if not user:
                flash("Invalid username or password.", "danger")
                return render_template("login.html")

            # ✅ Check password using scrypt hash verification
            stored_password_hash = user[2]
            if not check_password_hash(stored_password_hash, password):
                flash("Invalid username or password.", "danger")
                return render_template("login.html")

            # User authenticated successfully
            user_id = user[0]
            username_db = user[1]
            branchid = user[3]
            role_id = user[4]
            role_name = user[5] or "User"
            is_superadmin = bool(user[6])
            can_access_all_branches = bool(user[7])
            branch_name = user[8]
            emp_name = user[9] or username_db

            # Set session variables
            session["user_id"] = user_id
            session["username"] = username_db
            session["emp_name"] = emp_name
            session["role"] = role_name
            session["role_id"] = role_id
            session["is_superadmin"] = is_superadmin
            session["can_access_all_branches"] = can_access_all_branches
            session["login_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # If SuperAdmin, redirect to branch selection
            if is_superadmin or can_access_all_branches:
                session["requires_branch_selection"] = True
                flash(f"Welcome, {emp_name}! Please select a branch.", "info")
                return redirect(url_for("login.branch_selection"))
            
            # Regular user - set their branch
            if not branchid:
                flash("Your account is not assigned to any branch. Please contact administrator.", "danger")
                session.clear()
                return render_template("login.html")

            session["branchid"] = branchid
            session["branch_name"] = branch_name
            session["requires_branch_selection"] = False

            flash(f"Welcome back, {emp_name}!", "success")
            return redirect(url_for("home"))

        except Exception as e:
            flash(f"Login error: {str(e)}", "danger")
            import traceback
            traceback.print_exc()
            return render_template("login.html")
        
        finally:
            conn.close()

    return render_template("login.html")


@login_bp.route("/branch-selection", methods=["GET", "POST"])
@login_required
def branch_selection():
    """Branch selection page for SuperAdmin - CORRECTED SCHEMA."""
    
    # Check if user needs branch selection
    if not session.get("requires_branch_selection", False):
        # Already has branch, go to home
        return redirect(url_for("home"))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # ✅ CORRECTED: Use actual column names
        cursor.execute("""
            SELECT Id, Code, Name, Address
            FROM Branches
            ORDER BY Name
        """)
        branches = cursor.fetchall()

        if request.method == "POST":
            selected_branch = request.form.get("branch_id")
            
            if not selected_branch:
                flash("Please select a branch.", "warning")
                return render_template("branch_selection.html", branches=branches)

            # Get branch details
            cursor.execute("""
                SELECT Id, Code, Name
                FROM Branches
                WHERE Id = ?
            """, (selected_branch,))
            branch = cursor.fetchone()

            if not branch:
                flash("Invalid branch selected.", "danger")
                return render_template("branch_selection.html", branches=branches)

            # Set branch in session
            session["branchid"] = branch[0]
            session["branch_code"] = branch[1]
            session["branch_name"] = branch[2]
            session["requires_branch_selection"] = False

            flash(f"Working on: {branch[2]}", "success")
            return redirect(url_for("home"))

        return render_template("branch_selection.html", branches=branches)

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return render_template("branch_selection.html", branches=[])
    
    finally:
        conn.close()


@login_bp.route("/switch-branch", methods=["GET", "POST"])
@login_required
def switch_branch():
    """Allow SuperAdmin to switch branches - CORRECTED SCHEMA."""
    
    # Only SuperAdmin can switch branches
    if not session.get("can_access_all_branches", False):
        flash("Access denied. Only SuperAdmin can switch branches.", "danger")
        return redirect(url_for("home"))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get all branches
        cursor.execute("""
            SELECT Id, Code, Name, Address
            FROM Branches
            ORDER BY Name
        """)
        branches = cursor.fetchall()

        if request.method == "POST":
            selected_branch = request.form.get("branch_id")
            
            if not selected_branch:
                flash("Please select a branch.", "warning")
                return render_template("switch_branch.html", branches=branches)

            # Get branch details
            cursor.execute("""
                SELECT Id, Code, Name
                FROM Branches
                WHERE Id = ?
            """, (selected_branch,))
            branch = cursor.fetchone()

            if not branch:
                flash("Invalid branch selected.", "danger")
                return render_template("switch_branch.html", branches=branches)

            # Update branch in session
            session["branchid"] = branch[0]
            session["branch_code"] = branch[1]
            session["branch_name"] = branch[2]

            flash(f"Switched to: {branch[2]}", "success")
            return redirect(url_for("home"))

        return render_template("switch_branch.html", 
                             branches=branches, 
                             current_branch=session.get("branchid"))

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        import traceback
        traceback.print_exc()
        return render_template("switch_branch.html", branches=[], current_branch=None)
    
    finally:
        conn.close()


@login_bp.route("/logout")
def logout():
    """Logout and clear session."""
    username = session.get("emp_name", "User")
    session.clear()
    flash(f"Goodbye, {username}! Logged out successfully.", "info")
    return redirect(url_for("login.login"))
