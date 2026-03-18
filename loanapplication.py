"""
Loan Application Management Module
Handles loan applications with LoanProduct integration and auto-calculations
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime, date
from db import get_db_connection
from login import login_required
import logging

logger = logging.getLogger(__name__)

loanapplication_bp = Blueprint("loanapplication", __name__, template_folder="templates")

@loanapplication_bp.route("/", methods=["GET"])
@login_required
def index():
    """Display all loan applications"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all loan applications with member and center details
        cursor.execute("""
            SELECT 
                L.LoanApplicationID,
                L.MemberCode,
                M.full_name AS MemberName,
                C.center_name AS CenterName,
                L.LoanAmountRequested,
                L.LoanAmountApproved,
                P.PurposeName AS LoanPurpose,
                LP.ProductName AS LoanProduct,
                L.ApplicationStatus,
                L.ApplicationDate,
                L.Tenure,
                L.LoanCycle
            FROM LoanApplication L
            LEFT JOIN Members M ON L.MemberCode = M.member_code
            LEFT JOIN Center C ON C.center_name = L.CenterName
            LEFT JOIN LoanPurpose P ON L.LoanPurposeID = P.LoanPurposeID
            LEFT JOIN LoanProduct LP ON L.LoanTypeID = LP.ProductID
            WHERE L.branchid = ?
            ORDER BY L.LoanApplicationID DESC
        """, (session.get('branchid', 1),))
        
        applications = cursor.fetchall()
        conn.close()
        
        return render_template("loanapplication.html", applications=applications)
        
    except Exception as e:
        logger.error(f"Error fetching loan applications: {e}")
        flash("Error loading loan applications", "danger")
        return render_template("loanapplication.html", applications=[])

@loanapplication_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_application():
    """Add new loan application"""
    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get form data
            member_code = request.form.get('member_code')
            loan_product_id = request.form.get('loan_product_id')
            loan_amount_requested = request.form.get('loan_amount_requested')
            loan_purpose_id = request.form.get('loan_purpose_id')
            tenure = request.form.get('tenure')
            
            # Validate required fields
            if not all([member_code, loan_product_id, loan_amount_requested, loan_purpose_id]):
                flash("Please fill all required fields", "warning")
                return redirect(url_for("loanapplication.add_application"))
            
            # Get member details
            cursor.execute("""
                SELECT M.center_id, C.center_name, C.branchid
                FROM Members M
                JOIN Center C ON M.center_id = C.id
                WHERE M.member_code = ?
            """, (member_code,))
            
            member_data = cursor.fetchone()
            if not member_data:
                flash("Member not found", "danger")
                return redirect(url_for("loanapplication.add_application"))
            
            center_id, center_name, branch_id = member_data
            
            # Calculate loan cycle (count of approved loans + 1)
            cursor.execute("""
                SELECT COUNT(*) FROM LoanApplication
                WHERE MemberCode = ? AND ApplicationStatus = 'Approved'
            """, (member_code,))
            loan_cycle = cursor.fetchone()[0] + 1
            
            # Insert loan application
            cursor.execute("""
                INSERT INTO LoanApplication (
                    MemberCode, branchid, CenterName, LoanAmountRequested,
                    LoanPurposeID, LoanTypeID, ApplicationStatus, ApplicationDate,
                    CreatedBy, LoanCycle, Tenure
                )
                VALUES (?, ?, ?, ?, ?, ?, 'Pending', GETDATE(), ?, ?, ?)
            """, (
                member_code, branch_id, center_name, loan_amount_requested,
                loan_purpose_id, loan_product_id, session.get('emp_name', ''),
                loan_cycle, tenure
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"New loan application created for member: {member_code}")
            flash("Loan application submitted successfully!", "success")
            return redirect(url_for("loanapplication.index"))
            
        except Exception as e:
            logger.error(f"Error adding loan application: {e}")
            flash(f"Error submitting application: {str(e)}", "danger")
    
    # GET request - fetch data for form
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get active members with center info
        cursor.execute("""
            SELECT 
                M.member_code, 
                M.full_name, 
                M.phone1, 
                C.center_name,
                C.center_no,
                M.nominee_name,
                M.nominee_relation,
                M.nominee_phone,
                M.nominee_aadhaar
            FROM Members M
            JOIN Center C ON M.center_id = C.id
            WHERE M.BranchId = ? AND M.status = 'ACTIVE'
            ORDER BY M.full_name
        """, (session.get('branchid', 1),))
        members = cursor.fetchall()
        
        # Get active loan products
        cursor.execute("""
            SELECT 
                ProductID, ProductName, ProductCode, Description,
                MinAmount, MaxAmount, InterestRate,
                MinTenure, MaxTenure, FixedTenure,
                ProcessingFee, Savings, AdditionalSavings,
                MemberInsurance, NomineeInsurance, SecurityDeposit
            FROM LoanProduct
            WHERE Active = 1
            ORDER BY ProductName
        """)
        products = cursor.fetchall()
        
        # Get active loan purposes
        cursor.execute("""
            SELECT LoanPurposeID, PurposeName 
            FROM LoanPurpose 
            WHERE IsActive = 1
            ORDER BY PurposeName
        """)
        purposes = cursor.fetchall()
        
        conn.close()
        
        return render_template("loanapplication_form.html",
                             members=members,
                             products=products,
                             purposes=purposes)
        
    except Exception as e:
        logger.error(f"Error loading application form: {e}")
        flash(f"Error loading form: {str(e)}", "danger")
        return render_template("loanapplication_form.html",
                             members=[],
                             products=[],
                             purposes=[])

@loanapplication_bp.route("/approve/<int:app_id>", methods=["GET", "POST"])
@login_required
def approve_application(app_id):
    """Approve loan application (Admin only)"""
    if session.get("role") not in ["admin", "Manager"]:
        flash("Only Admins/Managers can approve loans!", "danger")
        return redirect(url_for("loanapplication.index"))
    
    if request.method == "POST":
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            loan_amount_approved = request.form.get('loan_amount_approved')
            disbursement_date = request.form.get('disbursement_date')
            
            cursor.execute("""
                UPDATE LoanApplication
                SET ApplicationStatus = 'Approved',
                    LoanAmountApproved = ?,
                    DisbursementDate = ?,
                    ApprovedBy = ?,
                    ApprovedOn = GETDATE(),
                    ModifiedBy = ?,
                    ModifiedDate = GETDATE()
                WHERE LoanApplicationID = ?
            """, (
                loan_amount_approved,
                disbursement_date,
                session.get('emp_name', ''),
                session.get('emp_name', ''),
                app_id
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Loan application {app_id} approved")
            flash("Loan application approved successfully!", "success")
            return redirect(url_for("loanapplication.index"))
            
        except Exception as e:
            logger.error(f"Error approving application: {e}")
            flash(f"Error approving application: {str(e)}", "danger")
    
    # GET request - show approval form
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                L.LoanApplicationID,
                L.MemberCode,
                M.full_name AS MemberName,
                M.phone1,
                C.center_name AS CenterName,
                L.LoanAmountRequested,
                P.PurposeName AS LoanPurpose,
                LP.ProductName,
                LP.InterestRate,
                L.Tenure,
                L.ApplicationDate,
                L.LoanCycle,
                LP.ProcessingFee,
                LP.MemberInsurance,
                LP.NomineeInsurance,
                LP.SecurityDeposit,
                LP.Savings,
                LP.AdditionalSavings
            FROM LoanApplication L
            LEFT JOIN Members M ON L.MemberCode = M.member_code
            LEFT JOIN Center C ON C.center_name = L.CenterName
            LEFT JOIN LoanPurpose P ON L.LoanPurposeID = P.LoanPurposeID
            LEFT JOIN LoanProduct LP ON L.LoanTypeID = LP.ProductID
            WHERE L.LoanApplicationID = ?
        """, (app_id,))
        
        application = cursor.fetchone()
        conn.close()
        
        if not application:
            flash("Application not found", "warning")
            return redirect(url_for("loanapplication.index"))
        
        # Get today's date for disbursement date default
        today = date.today().strftime('%Y-%m-%d')
        
        return render_template("loanapplication_approve.html", 
                             application=application,
                             today=today)
        
    except Exception as e:
        logger.error(f"Error loading approval form: {e}")
        flash(f"Error loading approval form: {str(e)}", "danger")
        return redirect(url_for("loanapplication.index"))

@loanapplication_bp.route("/reject/<int:app_id>", methods=["POST"])
@login_required
def reject_application(app_id):
    """Reject loan application (Admin only)"""
    if session.get("role") not in ["admin", "Manager"]:
        flash("Only Admins/Managers can reject loans!", "danger")
        return redirect(url_for("loanapplication.index"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        rejection_reason = request.form.get('rejection_reason', '')
        
        cursor.execute("""
            UPDATE LoanApplication
            SET ApplicationStatus = 'Rejected',
                AppRejectionReason = ?,
                ModifiedBy = ?,
                ModifiedDate = GETDATE()
            WHERE LoanApplicationID = ?
        """, (
            rejection_reason,
            session.get('emp_name', ''),
            app_id
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Loan application {app_id} rejected")
        flash("Loan application rejected!", "warning")
        
    except Exception as e:
        logger.error(f"Error rejecting application: {e}")
        flash(f"Error rejecting application: {str(e)}", "danger")
    
    return redirect(url_for("loanapplication.index"))

@loanapplication_bp.route("/pending", methods=["GET"])
@login_required
def pending_applications():
    """Show pending applications (Admin/Manager only)"""
    if session.get("role") not in ["admin", "Manager"]:
        flash("Only Admins/Managers can view pending approvals!", "danger")
        return redirect(url_for("loanapplication.index"))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                L.LoanApplicationID,
                L.MemberCode,
                M.full_name AS MemberName,
                M.phone1,
                C.center_name AS CenterName,
                L.LoanAmountRequested,
                P.PurposeName AS LoanPurpose,
                LP.ProductName,
                L.ApplicationStatus,
                L.ApplicationDate,
                L.Tenure,
                L.LoanCycle
            FROM LoanApplication L
            LEFT JOIN Members M ON L.MemberCode = M.member_code
            LEFT JOIN Center C ON C.center_name = L.CenterName
            LEFT JOIN LoanPurpose P ON L.LoanPurposeID = P.LoanPurposeID
            LEFT JOIN LoanProduct LP ON L.LoanTypeID = LP.ProductID
            WHERE L.ApplicationStatus = 'Pending' AND L.branchid = ?
            ORDER BY L.ApplicationDate ASC
        """, (session.get('branchid', 1),))
        
        applications = cursor.fetchall()
        conn.close()
        
        return render_template("loanapplication_pending.html", applications=applications)
        
    except Exception as e:
        logger.error(f"Error fetching pending applications: {e}")
        flash("Error loading pending applications", "danger")
        return render_template("loanapplication_pending.html", applications=[])

@loanapplication_bp.route("/product/<int:product_id>", methods=["GET"])
@login_required
def get_product_details(product_id):
    """API endpoint to get loan product details"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                ProductID, ProductName, ProductCode, Description,
                MinAmount, MaxAmount, InterestRate,
                MinTenure, MaxTenure, FixedTenure,
                ProcessingFee, Savings, AdditionalSavings,
                MemberInsurance, NomineeInsurance, SecurityDeposit
            FROM LoanProduct
            WHERE ProductID = ?
        """, (product_id,))
        
        product = cursor.fetchone()
        conn.close()
        
        if product:
            # Convert to dictionary for JSON response
            product_data = {
                'ProductID': product[0],
                'ProductName': product[1],
                'ProductCode': product[2],
                'Description': product[3],
                'MinAmount': float(product[4]) if product[4] else 0,
                'MaxAmount': float(product[5]) if product[5] else 0,
                'InterestRate': float(product[6]) if product[6] else 0,
                'MinTenure': product[7],
                'MaxTenure': product[8],
                'FixedTenure': product[9],
                'ProcessingFee': float(product[10]) if product[10] else 0,
                'Savings': float(product[11]) if product[11] else 0,
                'AdditionalSavings': float(product[12]) if product[12] else 0,
                'MemberInsurance': float(product[13]) if product[13] else 0,
                'NomineeInsurance': float(product[14]) if product[14] else 0,
                'SecurityDeposit': float(product[15]) if product[15] else 0
            }
            
            from flask import jsonify
            return jsonify(product_data)
        else:
            return jsonify({'error': 'Product not found'}), 404
            
    except Exception as e:
        logger.error(f"Error getting product details: {e}")
        from flask import jsonify
        return jsonify({'error': str(e)}), 500
