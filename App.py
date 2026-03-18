"""
UDLMS - Ushodaya MACS Ltd Loan Management System
Main Application File - FIXED VERSION
"""
from flask import Flask, render_template, redirect, url_for, session, request, flash
import sys
import os
import pyodbc
import pandas as pd
import datetime
import logging
from logging.handlers import RotatingFileHandler
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ---------- PyInstaller Path Handling ----------
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# ---------- App Init ----------
app = Flask(
    __name__,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR
)

# Secure secret key from environment
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    import warnings
    warnings.warn('SECRET_KEY not set in environment. Sessions will be lost on restart!', RuntimeWarning)
    _secret_key = os.urandom(24)
app.secret_key = _secret_key
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(
    minutes=int(os.environ.get('SESSION_TIMEOUT', 30))
)

# ---------- Logging Configuration ----------
if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler(
    'logs/udlms.log',
    maxBytes=10485760,  # 10MB
    backupCount=10
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('UDLMS startup')

# ---------- Import Permission Functions ----------
from permissions import (
    get_user_permissions,
    get_user_menus,
    check_permission,
    require_permission,
    is_readonly_access,
    has_any_permission,
    get_menu_permissions,
    get_current_user_role
)

# ---------- Make Permission Functions Available to Templates ----------
@app.context_processor
def inject_permissions():
    """Make permission checking functions available in all templates"""
    return dict(
        check_permission=check_permission,
        is_readonly_access=is_readonly_access,
        has_any_permission=has_any_permission,
        get_menu_permissions=get_menu_permissions,
        get_user_permissions=get_user_permissions,
        get_user_menus=get_user_menus,
        get_current_user_role=get_current_user_role
    )

# ---------- Imports (Blueprints) ----------
from db import get_db_connection
from login import login_bp, login_required
from center import center_bp
from members import members_bp
from employee import employee_bp
from product import product_bp
from loans import loans_bp
from savings import savings_bp
from loanapplication import loanapplication_bp
from recposting import recposting_bp
from rec_posting_memberwise import rec_member_bp
from recurringdeposit import recurringdeposit_bp
from rdcollections import rdcollections_bp
from settings import settings_bp
from dayend import dayend_bp
from fixeddeposit import fixeddeposit_bp
from fdcollections import fdcollections_bp
from reports import reports_bp
from advance import advance_bp
from loanrec import loanrec_bp
from security_deposit import security_deposit_bp
from help import help_bp
from collection_reports import collection_reports_bp
from SecurityDepositWithdraw import sd_withdraw_bp
# ---------- Register Blueprints ----------
app.register_blueprint(login_bp, url_prefix="/login")
app.register_blueprint(center_bp, url_prefix="/center")
app.register_blueprint(members_bp, url_prefix="/members")
app.register_blueprint(employee_bp, url_prefix="/employee")
app.register_blueprint(product_bp, url_prefix="/product")
app.register_blueprint(loans_bp, url_prefix="/loans")
app.register_blueprint(savings_bp, url_prefix="/savings")
app.register_blueprint(loanapplication_bp, url_prefix="/loanapplication")
app.register_blueprint(recposting_bp, url_prefix="/recposting")
app.register_blueprint(rec_member_bp, url_prefix="/rec_member")
app.register_blueprint(recurringdeposit_bp, url_prefix="/recurringdeposit")
app.register_blueprint(rdcollections_bp, url_prefix="/rdcollections")
app.register_blueprint(settings_bp, url_prefix="/settings")
app.register_blueprint(dayend_bp, url_prefix="/dayend")
app.register_blueprint(fixeddeposit_bp, url_prefix="/fixeddeposit")
app.register_blueprint(fdcollections_bp, url_prefix="/fdcollections")
app.register_blueprint(reports_bp, url_prefix="/reports")
app.register_blueprint(advance_bp, url_prefix="/advance")
app.register_blueprint(loanrec_bp, url_prefix="/loanrec")
app.register_blueprint(security_deposit_bp, url_prefix="/security_deposit")
app.register_blueprint(help_bp, url_prefix="/help")
app.register_blueprint(collection_reports_bp)
app.register_blueprint(sd_withdraw_bp, url_prefix="/sd_withdraw")

# ---------- Error Handlers ----------
@app.errorhandler(404)
def not_found_error(error):
    app.logger.error(f'Page not found: {request.url}')
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f'Server Error: {error}')
    return render_template('500.html'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f'Unhandled Exception: {str(e)}', exc_info=True)
    flash('An unexpected error occurred. Please try again.', 'danger')
    return redirect(url_for('home'))

# ---------- Root ----------
@app.route("/")
def root():
    if "user_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("login.login"))

# ---------- Context Processor (Footer Data) ----------
@app.context_processor
def inject_footer_data():
    staff_name = session.get("emp_name", "Guest")
    login_time = session.get("login_time")
    idle_time = None

    if login_time:
        try:
            login_dt = datetime.datetime.strptime(login_time, "%Y-%m-%d %H:%M:%S")
            idle_time = str(datetime.datetime.now() - login_dt).split(".")[0]
        except Exception as e:
            app.logger.error(f'Error calculating idle time: {e}')
            idle_time = None

    last_dayend_date = None
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 1 DayendDate FROM Dayend ORDER BY DayendDate DESC"
        )
        row = cursor.fetchone()
        if row:
            last_dayend_date = row[0].strftime("%Y-%m-%d")
    except Exception as e:
        app.logger.error(f'Error fetching dayend date: {e}')
    finally:
        try:
            if conn:
                conn.close()
        except:
            pass

    return {
        "staff_name": staff_name,
        "idle_time": idle_time,
        "last_dayend_date": last_dayend_date,
        "current_year": datetime.datetime.now().year,
        "role": session.get("role", ""),
        "branch_id": session.get("branchid")
    }


@app.route("/dashboard")
@login_required
def home():
    """Dashboard with statistics and dayend info."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ✅ FIX: Get branchid from session (not using id() function!)
        branchid = session.get("branchid", 1)

        # ✅ FIX: Use correct table and column names
        # Your schema: Branches.Id, Branches.Name (not Branch.BranchId, Branch.BranchName)
        cursor.execute("SELECT Name FROM Branches WHERE Id = ?", (branchid,))
        branch_row = cursor.fetchone()
        branch_name = branch_row[0] if branch_row else "Unknown Branch"

        # Get last dayend date
        cursor.execute("""
            SELECT TOP 1 DayendDate
            FROM Dayend
            WHERE BranchId = ?
            ORDER BY DayendDate DESC
        """, (branchid,))
        dayend_row = cursor.fetchone()
        last_dayend_date = dayend_row[0] if dayend_row else None

        # Get dashboard statistics
        stats = {}

        # Total members
        cursor.execute("SELECT COUNT(*) FROM Members WHERE status = 'ACTIVE'")
        stats['total_members'] = cursor.fetchone()[0]

        # Active loans
        cursor.execute("SELECT COUNT(*) FROM Loans WHERE loanstatus = 'Active'")
        stats['active_loans'] = cursor.fetchone()[0]

        # Total loan amount outstanding
        cursor.execute("""
            SELECT ISNULL(SUM(principaloutstanding), 0) 
            FROM Loans 
            WHERE loanstatus = 'Active'
        """)
        stats['total_outstanding'] = cursor.fetchone()[0]

        # Today's collection
        cursor.execute("""
            SELECT ISNULL(SUM(principalpaidamount + interestpaidamount), 0)
            FROM LoanRec
            WHERE CAST(createddate AS DATE) = CAST(GETDATE() AS DATE)
        """)
        stats['today_collection'] = cursor.fetchone()[0]

        # Pending loan applications
        cursor.execute("""
            SELECT COUNT(*) FROM LoanApplication 
            WHERE ApplicationStatus = 'Pending'
        """)
        stats['pending_applications'] = cursor.fetchone()[0]

        # Active FDs
        cursor.execute("""
            SELECT COUNT(*) FROM FDDetails 
            WHERE WithdrawDate IS NULL
        """)
        stats['active_fds'] = cursor.fetchone()[0]

        # Active RDs
        cursor.execute("""
            SELECT COUNT(*) FROM RecurringDeposit 
            WHERE Status = 'Active'
        """)
        stats['active_rds'] = cursor.fetchone()[0]

        conn.close()

        # ✅ FIX: Return branch_name and last_dayend_date to template
        return render_template(
            "dashboard.html",
            username=session.get("emp_name"),
            role=session.get("role"),
            branch_name=branch_name,
            last_dayend_date=last_dayend_date,
            stats=stats
        )

    except Exception as e:
        app.logger.error(f'Dashboard error: {e}')
        import traceback
        traceback.print_exc()
        flash('Error loading dashboard data', 'danger')
        return render_template(
            "dashboard.html",
            username=session.get("emp_name"),
            role=session.get("role"),
            branch_name="Unknown",
            last_dayend_date=None,
            stats={}
        )


# ═══════════════════════════════════════════════════════════════
# ALSO ADD THESE TO APP.PY:
# ═══════════════════════════════════════════════════════════════

# At line ~130 (with other imports), ADD:
from user_management import user_mgmt_bp

# At line ~150 (with other blueprint registrations), ADD:
app.register_blueprint(user_mgmt_bp, url_prefix="/users")


# ---------- Logout ----------
@app.route("/logout")
def logout():
    username = session.get("emp_name", "User")
    session.clear()
    app.logger.info(f'User logged out: {username}')
    flash("Logged out successfully!", "info")
    return redirect(url_for("login.login"))

# ---------- Health Check ----------
@app.route("/health")
def health_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return {"status": "healthy", "database": "connected"}, 200
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500

# ---------- Run ----------
if __name__ == "__main__":
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    app.logger.info(f'Starting UDLMS on {host}:{port}')
    app.run(host=host, port=port, debug=debug)
