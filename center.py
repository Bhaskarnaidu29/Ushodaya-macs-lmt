"""
Center Management Module - Enhanced Version
Handles center CRUD operations with auto-generated center_no
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, date
from db import get_db_connection
from login import login_required
import logging


logger = logging.getLogger(__name__)


center_bp = Blueprint("center", __name__, template_folder="templates")

def generate_center_no(cursor, branch_id):
    """Generate next center number (BranchID + sequential number)
    Example: If BranchID=1, generates 101, 102, 103...
             If BranchID=2, generates 201, 202, 203...
    """
    try:
        cursor.execute("""
            SELECT TOP 1 center_no 
            FROM Center 
            WHERE branchid = ?
            ORDER BY center_no DESC
        """, (branch_id,))
        
        result = cursor.fetchone()
        if result and result[0]:
            last_center_no = result[0]
            # Increment the last number
            next_no = last_center_no + 1
        else:
            # First center for this branch: BranchID * 100 + 1
            next_no = (branch_id * 100) + 1
        
        return next_no
    except Exception as e:
        logger.error(f"Error in generate_center_no: {e}")
        # Fallback: use branch_id * 100 + 1
        return (branch_id * 100) + 1

@center_bp.route("/", methods=["GET"])
@login_required
def index():
    """Display all centers"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, center_no, center_name, create_date, handling_staff, 
                   address1, city, district, max_members, loan_type, due_day
            FROM Center
            WHERE branchid = ?
            ORDER BY center_no
        """, (session.get('branchid', 1),))
        
        centers = cursor.fetchall()
        
        # Get count of members per center
        cursor.execute("""
            SELECT center_id, COUNT(*) as member_count
            FROM Members
            WHERE status = 'ACTIVE'
            GROUP BY center_id
        """)
        member_counts = dict(cursor.fetchall())
        
        conn.close()
        

        return render_template("center.html", centers=centers, member_counts=member_counts)
        
    except Exception as e:
        logger.error(f"Error fetching centers: {e}")
        flash("Error loading centers list", "danger")
        return render_template("center.html", centers=[], member_counts={})

@center_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_center():
    """Add new center"""
    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Auto-generate center number
            branch_id = session.get('branchid', 1)
            center_no = generate_center_no(cursor, branch_id)
            
            # Get form data
            data = {
                'center_no': center_no,
                'center_name': request.form['center_name'].strip(),
                'create_staff': session.get('emp_name', ''),
                'create_date': request.form.get('create_date') or datetime.now().date(),
                'address1': request.form.get('address1', '').strip(),
                'address2': request.form.get('address2', '').strip(),
                'city': request.form.get('city', '').strip(),
                'district': request.form.get('district', '').strip(),
                'state': request.form.get('state', '').strip(),
                'pincode': request.form.get('pincode', '').strip(),
                'landmark': request.form.get('landmark', '').strip(),
                'handling_staff': request.form.get('handling_staff', '').strip(),
                'max_members': request.form.get('max_members', 50) or 50,
                'note': request.form.get('note', '').strip(),
                'loan_type': request.form.get('loan_type', 'Weekly'),
                'due_day': request.form.get('due_day', '').strip(),
                'due_date': request.form.get('due_date', None) or None,
                'close_date': request.form.get('close_date', None) or None,
                'share_capital': request.form.get('share_capital', 0) or 0,
                'savings': request.form.get('savings', 0) or 0,
                'joining_fee': request.form.get('joining_fee', 0) or 0,
                'collection_day': request.form.get('collection_day', None) or None,
                'weekly_collection_day': request.form.get('weekly_collection_day', None) or None,
                'branchid': branch_id
            }
            
            # Validate required fields
            if not data['center_name']:
                flash("Center Name is required", "warning")
                return redirect(url_for("center.add_center"))
            
            if not data['handling_staff']:
                flash("Handling Staff is required", "warning")
                return redirect(url_for("center.add_center"))
            
            # Insert center
            cursor.execute("""
                INSERT INTO Center (
                    center_no, center_name, create_staff, create_date,
                    address1, address2, city, district, state, pincode, landmark,
                    handling_staff, max_members, note, loan_type, due_day, due_date,
                    close_date, share_capital, savings, joining_fee, branchid,
                    collection_day, weekly_collection_day
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data['center_no'], data['center_name'], data['create_staff'], data['create_date'],
                data['address1'], data['address2'], data['city'], data['district'],
                data['state'], data['pincode'], data['landmark'], data['handling_staff'],
                data['max_members'], data['note'], data['loan_type'], data['due_day'],
                data['due_date'], data['close_date'], data['share_capital'],
                data['savings'], data['joining_fee'], data['branchid'],
                data['collection_day'], data['weekly_collection_day']
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"New center added: {data['center_name']} (Center No: {center_no})")
            flash(f"Center '{data['center_name']}' added successfully! Center No: {center_no}", "success")
            return redirect(url_for("center.index"))
            
        except Exception as e:
            logger.error(f"Error adding center: {e}")
            flash(f"Error adding center: {str(e)}", "danger")
    
    # GET request - fetch staff list and generate next center_no
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        branch_id = session.get('branchid', 1)
        
        # Get active staff members from Users table
        try:
            cursor.execute("""
                SELECT emp_name 
                FROM Users 
                WHERE BranchId = ? 
                AND (expire IS NULL OR expire > CAST(GETDATE() AS DATE))
                ORDER BY emp_name
            """, (branch_id,))
            staff_list = [row[0] for row in cursor.fetchall()]
            
            if not staff_list:
                logger.warning(f"No active staff found for branch {branch_id}")
                flash("Warning: No active staff members found. Please add employees first.", "warning")
        except Exception as e:
            logger.error(f"Error fetching staff list: {e}")
            staff_list = []
            flash("Could not load staff list. Using empty list.", "warning")
        
        # Generate next center number
        try:
            next_center_no = generate_center_no(cursor, branch_id)
        except Exception as e:
            logger.error(f"Error generating center number: {e}")
            next_center_no = (branch_id * 100) + 1
            flash(f"Using default center number: {next_center_no}", "info")
        
        conn.close()
        
        # Get current date for form default
        current_date = date.today().strftime('%Y-%m-%d')
        
        return render_template("center_add.html", 
                             staff_list=staff_list, 
                             next_center_no=next_center_no,
                             current_date=current_date)
    except Exception as e:
        logger.error(f"Error loading add form: {e}")
        flash(f"Error loading form: {str(e)}", "danger")
        # Return with safe defaults
        current_date = date.today().strftime('%Y-%m-%d')
        return render_template("center_add.html", 
                             staff_list=[], 
                             next_center_no=101,
                             current_date=current_date)

@center_bp.route("/edit/<int:center_id>", methods=["GET", "POST"])
@login_required
def edit_center(center_id):
    """Edit center details"""
    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get form data
            data = {
                'center_name': request.form['center_name'].strip(),
                'address1': request.form.get('address1', '').strip(),
                'address2': request.form.get('address2', '').strip(),
                'city': request.form.get('city', '').strip(),
                'district': request.form.get('district', '').strip(),
                'state': request.form.get('state', '').strip(),
                'pincode': request.form.get('pincode', '').strip(),
                'landmark': request.form.get('landmark', '').strip(),
                'handling_staff': request.form.get('handling_staff', '').strip(),
                'max_members': request.form.get('max_members', 50) or 50,
                'note': request.form.get('note', '').strip(),
                'loan_type': request.form.get('loan_type', 'Weekly'),
                'due_day': request.form.get('due_day', '').strip(),
                'due_date': request.form.get('due_date', None) or None,
                'close_date': request.form.get('close_date', None) or None,
                'share_capital': request.form.get('share_capital', 0) or 0,
                'savings': request.form.get('savings', 0) or 0,
                'joining_fee': request.form.get('joining_fee', 0) or 0,
                'collection_day': request.form.get('collection_day', None) or None,
                'weekly_collection_day': request.form.get('weekly_collection_day', None) or None,
            }
            
            # Update center
            cursor.execute("""
                UPDATE Center SET
                    center_name = ?, address1 = ?, address2 = ?, city = ?, 
                    district = ?, state = ?, pincode = ?, landmark = ?,
                    handling_staff = ?, max_members = ?, note = ?, loan_type = ?,
                    due_day = ?, due_date = ?, close_date = ?,
                    share_capital = ?, savings = ?, joining_fee = ?,
                    collection_day = ?, weekly_collection_day = ?
                WHERE id = ?
            """, (
                data['center_name'], data['address1'], data['address2'], data['city'],
                data['district'], data['state'], data['pincode'], data['landmark'],
                data['handling_staff'], data['max_members'], data['note'], data['loan_type'],
                data['due_day'], data['due_date'], data['close_date'],
                data['share_capital'], data['savings'], data['joining_fee'],
                data['collection_day'], data['weekly_collection_day'],
                center_id
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Center updated: {center_id}")
            flash("Center updated successfully!", "success")
            return redirect(url_for("center.index"))
            
        except Exception as e:
            logger.error(f"Error updating center: {e}")
            flash(f"Error updating center: {str(e)}", "danger")
    
    # GET request
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get center details
        cursor.execute("SELECT * FROM Center WHERE id = ?", (center_id,))
        center = cursor.fetchone()
        
        if not center:
            flash("Center not found", "warning")
            return redirect(url_for("center.index"))
        
        # Get active staff members
        try:
            cursor.execute("""
                SELECT emp_name 
                FROM Users 
                WHERE BranchId = ? 
                AND (expire IS NULL OR expire > CAST(GETDATE() AS DATE))
                ORDER BY emp_name
            """, (session.get('branchid', 1),))
            staff_list = [row[0] for row in cursor.fetchall()]
            
            if not staff_list:
                logger.warning("No active staff found for edit form")
                staff_list = []
        except Exception as e:
            logger.error(f"Error fetching staff for edit: {e}")
            staff_list = []
        
        conn.close()
        
        return render_template("center_edit.html", center=center, staff_list=staff_list)
        
    except Exception as e:
        logger.error(f"Error loading center: {e}")
        flash(f"Error loading center details: {str(e)}", "danger")
        return redirect(url_for("center.index"))

@center_bp.route("/delete/<int:center_id>", methods=["POST"])
@login_required
def delete_center(center_id):
    """Delete center (soft delete by setting close_date)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if center has active members
        cursor.execute("""
            SELECT COUNT(*) FROM Members 
            WHERE center_id = ? AND status = 'ACTIVE'
        """, (center_id,))
        
        active_members = cursor.fetchone()[0]
        
        if active_members > 0:
            flash(f"Cannot close center. It has {active_members} active members.", "warning")
            conn.close()
            return redirect(url_for("center.index"))
        
        # Soft delete - set close_date
        cursor.execute("""
            UPDATE Center 
            SET close_date = GETDATE()
            WHERE id = ?
        """, (center_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Center closed: {center_id}")
        flash("Center closed successfully!", "success")
        
    except Exception as e:
        logger.error(f"Error closing center: {e}")
        flash(f"Error closing center: {str(e)}", "danger")
    
    return redirect(url_for("center.index"))
