"""
Help Menu Module
Handles backup, restore, about, and updates pages.
All paths are resolved dynamically — no hardcoded drive letters or folder names.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime
from functools import wraps
import logging
import os
import sys
import zipfile
import json
from pathlib import Path
import pyodbc

logger = logging.getLogger(__name__)

help_bp = Blueprint('help', __name__, template_folder='templates')

# ------------------------------------------------------------------
# Resolve the application's base directory at runtime.
# Works correctly both when run as a plain Python script AND
# when bundled into a single-file EXE by PyInstaller.
# ------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # Running inside a PyInstaller EXE
    # _MEIPASS is the temp folder where the EXE extracts itself.
    # The .env and writable folders (backups, uploads) must live
    # next to the EXE, not inside _MEIPASS (which is read-only).
    APP_DIR = Path(sys.executable).parent
else:
    # Running as a normal Python script
    APP_DIR = Path(__file__).resolve().parent

# Writable data directories — created automatically if missing
BACKUP_DIR  = APP_DIR / 'backups'
UPLOADS_DIR = APP_DIR / 'uploads'

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------
# DB credentials — read from environment / .env (same as db.py)
# ------------------------------------------------------------------
def _get_db_name():
    return os.getenv('SQL_DATABASE', 'udlms')

def get_db_connection_for_backup():
    """
    Autocommit connection required for BACKUP / RESTORE DATABASE
    commands — they cannot run inside a regular transaction.
    Credentials come from .env via environment variables.
    """
    from db import build_connection_string
    conn_str = build_connection_string()
    return pyodbc.connect(conn_str, autocommit=True, timeout=10)

def get_regular_db_connection():
    from db import get_db_connection
    return get_db_connection()

# ------------------------------------------------------------------
# Decorators
# ------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page", "warning")
            return redirect(url_for('login.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page", "warning")
            return redirect(url_for('login.login'))
        user_role = session.get('role', '').lower()
        if user_role not in ['admin', 'administrator']:
            flash("Admin access required.", "danger")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@help_bp.route('/about')
@login_required
def about():
    """About System — available to all logged-in users."""
    try:
        conn = get_regular_db_connection()
        cursor = conn.cursor()

        def safe_query(query, default=0):
            try:
                cursor.execute(query)
                result = cursor.fetchone()
                return result[0] if result and result[0] is not None else default
            except Exception as e:
                logger.error(f"Query error: {e}")
                return default

        total_members    = safe_query("SELECT COUNT(*) FROM Members")
        total_centers    = safe_query("SELECT COUNT(*) FROM Centers")
        active_loans     = safe_query("SELECT COUNT(*) FROM Loans WHERE loanstatus = 'Active'")
        total_employees  = safe_query("SELECT COUNT(*) FROM Employee WHERE WithdrawDate IS NULL")
        total_outstanding = safe_query("SELECT SUM(loanamount) FROM Loans WHERE loanstatus = 'Active'")

        try:
            cursor.execute("SELECT @@VERSION")
            sql_version = cursor.fetchone()[0].split('\n')[0]
        except Exception:
            sql_version = "SQL Server"

        try:
            cursor.execute("""
                SELECT SUM(size) * 8 / 1024.0 AS SizeMB
                FROM sys.master_files
                WHERE database_id = DB_ID()
            """)
            row = cursor.fetchone()
            db_size = f"{row[0]:.2f} MB" if row and row[0] else "N/A"
        except Exception:
            db_size = "N/A"

        conn.close()

        system_info = {
            'app_name':       'Ushodaya MACS Ltd - Loan Management System',
            'version':        '2.0.0',
            'release_date':   '15-Feb-2025',
            'developer':      'Custom Software Solutions',
            'support_email':  'support@ushodaya.com',
            'support_phone':  '+91-1234567890',
            'sql_version':    sql_version,
            'db_size':        db_size,
            'total_members':  total_members,
            'total_centers':  total_centers,
            'active_loans':   active_loans,
            'total_employees': total_employees,
            'total_outstanding': total_outstanding,
            'license':        'Licensed to Ushodaya MACS Ltd',
            'license_expiry': '31-Dec-2025',
        }

        return render_template('help_about.html', info=system_info)

    except Exception as e:
        logger.error(f"Error in about: {e}", exc_info=True)
        flash(f"Error loading system information: {str(e)}", "danger")
        return redirect(url_for('home'))


@help_bp.route('/backup', methods=['GET', 'POST'])
@login_required
@admin_required
def backup():
    """Database Backup — Admin Only."""
    if request.method == 'POST':
        try:
            backup_type     = request.form.get('backup_type', 'full')
            include_uploads = request.form.get('include_uploads', 'off') == 'on'
            db_name         = _get_db_name()

            timestamp   = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"backup_{timestamp}"
            backup_path = BACKUP_DIR / backup_name
            backup_path.mkdir(parents=True, exist_ok=True)

            db_backup_file = backup_path / f"{db_name}.bak"

            logger.info(f"Creating database backup: {db_backup_file}")

            conn   = get_db_connection_for_backup()
            cursor = conn.cursor()

            backup_sql = f"""
                BACKUP DATABASE [{db_name}]
                TO DISK = N'{db_backup_file}'
                WITH FORMAT, INIT,
                NAME = N'{db_name}-Full Database Backup',
                SKIP, NOREWIND, NOUNLOAD, STATS = 10
            """
            cursor.execute(backup_sql)
            conn.close()

            if not db_backup_file.exists():
                raise Exception("Backup file was not created by SQL Server.")

            metadata = {
                'backup_date':     datetime.now().isoformat(),
                'backup_type':     backup_type,
                'database':        db_name,
                'created_by':      session.get('emp_name', 'unknown'),
                'size':            os.path.getsize(db_backup_file),
                'include_uploads': include_uploads,
            }
            with open(backup_path / 'backup_info.json', 'w') as f:
                json.dump(metadata, f, indent=2)

            if include_uploads and UPLOADS_DIR.exists():
                logger.info("Backing up uploads folder...")
                uploads_zip = backup_path / "uploads.zip"
                with zipfile.ZipFile(uploads_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file in UPLOADS_DIR.rglob('*'):
                        if file.is_file():
                            try:
                                zipf.write(file, file.relative_to(UPLOADS_DIR.parent))
                            except Exception as ex:
                                logger.warning(f"Could not backup file {file}: {ex}")

            # Bundle everything into a single zip
            zip_file = BACKUP_DIR / f"{backup_name}.zip"
            with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in backup_path.rglob('*'):
                    if file.is_file():
                        zipf.write(file, file.relative_to(backup_path.parent))

            import shutil
            shutil.rmtree(backup_path)

            backup_size_mb = os.path.getsize(zip_file) / (1024 * 1024)
            logger.info(f"Backup completed: {zip_file} ({backup_size_mb:.2f} MB)")
            flash(
                f"Backup created successfully!  File: {backup_name}.zip  "
                f"Size: {backup_size_mb:.2f} MB  Location: {BACKUP_DIR}",
                "success"
            )
            return redirect(url_for('help.backup'))

        except Exception as e:
            logger.error(f"Backup error: {e}", exc_info=True)
            flash(f"Backup failed: {str(e)}", "danger")

    # GET — list existing backups
    try:
        backups = []
        if BACKUP_DIR.exists():
            for bf in sorted(BACKUP_DIR.glob('*.zip'), reverse=True):
                try:
                    stat = bf.stat()
                    backups.append({
                        'name':     bf.name,
                        'path':     bf,
                        'size':     stat.st_size / (1024 * 1024),
                        'date':     datetime.fromtimestamp(stat.st_mtime),
                        'age_days': (datetime.now() - datetime.fromtimestamp(stat.st_mtime)).days,
                    })
                except Exception as ex:
                    logger.warning(f"Could not read backup file {bf}: {ex}")

        return render_template('help_backup.html', backups=backups, backup_dir=BACKUP_DIR)

    except Exception as e:
        logger.error(f"Error loading backup page: {e}", exc_info=True)
        flash("Error loading backup page", "danger")
        return redirect(url_for('home'))


@help_bp.route('/backup/download/<filename>')
@login_required
@admin_required
def download_backup(filename):
    """Download a backup zip."""
    try:
        backup_file = BACKUP_DIR / filename
        if backup_file.exists():
            return send_file(backup_file, as_attachment=True, download_name=filename)
        flash("Backup file not found", "danger")
    except Exception as e:
        logger.error(f"Error downloading backup: {e}")
        flash("Error downloading backup", "danger")
    return redirect(url_for('help.backup'))


@help_bp.route('/backup/delete/<filename>', methods=['POST'])
@login_required
@admin_required
def delete_backup(filename):
    """Delete a backup zip."""
    try:
        backup_file = BACKUP_DIR / filename
        if backup_file.exists():
            os.remove(backup_file)
            logger.info(f"Backup deleted: {filename} by {session.get('emp_name')}")
            flash(f"Backup deleted: {filename}", "success")
        else:
            flash("Backup file not found", "warning")
    except Exception as e:
        logger.error(f"Error deleting backup: {e}")
        flash(f"Error deleting backup: {str(e)}", "danger")
    return redirect(url_for('help.backup'))


@help_bp.route('/restore', methods=['GET', 'POST'])
@login_required
@admin_required
def restore():
    """Database Restore — Admin Only."""
    if request.method == 'POST':
        try:
            backup_filename = request.form.get('backup_file')
            confirm         = request.form.get('confirm', 'off') == 'on'
            db_name         = _get_db_name()

            if not confirm:
                flash("Please confirm that you want to restore the database.", "warning")
                return redirect(url_for('help.restore'))

            if not backup_filename:
                flash("Please select a backup file.", "warning")
                return redirect(url_for('help.restore'))

            backup_path = BACKUP_DIR / backup_filename
            if not backup_path.exists():
                flash("Backup file not found.", "danger")
                return redirect(url_for('help.restore'))

            logger.info(f"Starting restore from: {backup_filename} by {session.get('emp_name')}")

            extract_dir = BACKUP_DIR / 'temp_restore'
            extract_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(extract_dir)

            bak_file = next(extract_dir.rglob('*.bak'), None)
            if not bak_file:
                flash("No .bak file found inside the archive.", "danger")
                import shutil; shutil.rmtree(extract_dir)
                return redirect(url_for('help.restore'))

            conn   = get_db_connection_for_backup()
            cursor = conn.cursor()

            cursor.execute(f"ALTER DATABASE [{db_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute(f"""
                RESTORE DATABASE [{db_name}]
                FROM DISK = N'{bak_file}'
                WITH REPLACE, RECOVERY
            """)
            cursor.execute(f"ALTER DATABASE [{db_name}] SET MULTI_USER")
            conn.close()

            import shutil
            shutil.rmtree(extract_dir)

            logger.info(f"Database restored successfully from: {backup_filename}")
            flash(
                f"Database restored successfully from {backup_filename}! "
                "All users have been logged out. Please log in again.",
                "success"
            )
            session.clear()
            return redirect(url_for('login.login'))

        except Exception as e:
            logger.error(f"Restore error: {e}", exc_info=True)
            flash(f"Restore failed: {str(e)}", "danger")

    # GET — show restore form
    try:
        backups = []
        if BACKUP_DIR.exists():
            for bf in sorted(BACKUP_DIR.glob('*.zip'), reverse=True):
                try:
                    stat = bf.stat()
                    backups.append({
                        'name': bf.name,
                        'size': stat.st_size / (1024 * 1024),
                        'date': datetime.fromtimestamp(stat.st_mtime),
                    })
                except Exception as ex:
                    logger.warning(f"Could not read backup file {bf}: {ex}")

        return render_template('help_restore.html', backups=backups)

    except Exception as e:
        logger.error(f"Error loading restore page: {e}", exc_info=True)
        flash("Error loading restore page", "danger")
        return redirect(url_for('home'))


@help_bp.route('/updates')
@login_required
def updates():
    """System Updates — available to all logged-in users."""
    try:
        current_version = '2.0.0'
        current_date    = datetime(2025, 2, 15)

        available_updates = [
            {
                'version':      '2.1.0',
                'release_date': datetime(2025, 3, 1),
                'type':         'Feature Update',
                'size':         '25 MB',
                'features': [
                    'New dashboard analytics',
                    'Improved loan calculator',
                    'Mobile app integration',
                    'Performance improvements',
                ],
                'critical': False,
            },
            {
                'version':      '2.0.1',
                'release_date': datetime(2025, 2, 20),
                'type':         'Security Patch',
                'size':         '5 MB',
                'features': [
                    'Security vulnerability fixes',
                    'Bug fixes for loan disbursement',
                    'Database optimization',
                ],
                'critical': True,
            },
        ]

        update_history = [
            {
                'version': '2.0.0',
                'date':    datetime(2025, 2, 15),
                'changes': [
                    'Complete UI redesign',
                    'Auto-generated employee credentials',
                    'Enhanced loan disbursement',
                    'Improved security',
                ],
            },
            {
                'version': '1.5.0',
                'date':    datetime(2025, 1, 10),
                'changes': [
                    'Added member management',
                    'Center tracking',
                    'Loan recovery module',
                ],
            },
        ]

        return render_template(
            'help_updates.html',
            current_version=current_version,
            current_date=current_date,
            available_updates=available_updates,
            update_history=update_history,
        )

    except Exception as e:
        logger.error(f"Error in updates: {e}")
        flash(f"Error loading updates page: {str(e)}", "danger")
        return redirect(url_for('home'))


@help_bp.route('/updates/download/<version>')
@login_required
@admin_required
def download_update(version):
    flash(
        f"Update {version} download would start here. "
        "Please contact support for manual updates.",
        "info"
    )
    return redirect(url_for('help.updates'))