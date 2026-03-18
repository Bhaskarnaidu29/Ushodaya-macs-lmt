# settings.py - Admin Settings & Master Data Management
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from db import get_db_connection
from datetime import datetime
import traceback

settings_bp = Blueprint('settings_bp', __name__, template_folder='templates')


# ═══════════════════════════════════════════════════════════════
#  ROUTE: Main Settings Dashboard
# ═══════════════════════════════════════════════════════════════
@settings_bp.route('/')
def settings():
    """Main settings dashboard with all master options"""
    return render_template('settings_dashboard.html')


# ═══════════════════════════════════════════════════════════════
#  PRODUCT MASTER
# ═══════════════════════════════════════════════════════════════
@settings_bp.route('/products', methods=['GET', 'POST'])
def products():
    """Loan Product Master - Create & Manage Products"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # POST - Add/Update Product
        if request.method == 'POST':
            try:
                action = request.form.get('action')
                
                if action == 'add':
                    # Add new product
                    product_name = request.form.get('ProductName')
                    product_code = request.form.get('ProductCode')
                    description = request.form.get('Description', '')
                    min_amount = float(request.form.get('MinAmount', 0))
                    max_amount = float(request.form.get('MaxAmount', 0))
                    interest_rate = float(request.form.get('InterestRate', 0))
                    min_tenure = int(request.form.get('MinTenure', 0))
                    max_tenure = int(request.form.get('MaxTenure', 0))
                    fixed_tenure = 1 if request.form.get('FixedTenure') else 0
                    processing_fee = float(request.form.get('ProcessingFee', 0))
                    savings = float(request.form.get('Savings', 0))
                    additional_savings = float(request.form.get('AdditionalSavings', 0))
                    member_insurance = float(request.form.get('MemberInsurance', 0))
                    nominee_insurance = float(request.form.get('NomineeInsurance', 0))
                    security_deposit = float(request.form.get('SecurityDeposit', 0))
                    payment_frequency = request.form.get('PaymentFrequency', 'Weekly')
                    int_security_deposit = float(request.form.get('IntSecurityDeposit', 0))
                    active = 1 if request.form.get('Active') else 0
                    
                    cursor.execute("""
                        INSERT INTO LoanProduct (
                            ProductName, ProductCode, Description, MinAmount, MaxAmount,
                            InterestRate, MinTenure, MaxTenure, Active, FixedTenure,
                            ProcessingFee, Savings, AdditionalSavings, MemberInsurance,
                            NomineeInsurance, SecurityDeposit, PaymentFrequency,
                            IntSecurityDeposit, CreatedAt, ModifiedBy, ModifiedDate
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                                GETDATE(), ?, GETDATE())
                    """, (product_name, product_code, description, min_amount, max_amount,
                          interest_rate, min_tenure, max_tenure, active, fixed_tenure,
                          processing_fee, savings, additional_savings, member_insurance,
                          nominee_insurance, security_deposit, payment_frequency,
                          int_security_deposit, session.get('user_id', 1)))
                    
                    conn.commit()
                    flash('✅ Product added successfully!', 'success')
                
                elif action == 'update':
                    # Update existing product
                    product_id = request.form.get('ProductID')
                    product_name = request.form.get('ProductName')
                    interest_rate = float(request.form.get('InterestRate', 0))
                    active = 1 if request.form.get('Active') else 0
                    
                    cursor.execute("""
                        UPDATE LoanProduct
                        SET ProductName = ?,
                            InterestRate = ?,
                            Active = ?,
                            ModifiedBy = ?,
                            ModifiedDate = GETDATE()
                        WHERE ProductID = ?
                    """, (product_name, interest_rate, active, 
                          session.get('user_id', 1), product_id))
                    
                    conn.commit()
                    flash('✅ Product updated successfully!', 'success')
                
                elif action == 'delete':
                    # Soft delete (set Active = 0)
                    product_id = request.form.get('ProductID')
                    cursor.execute("""
                        UPDATE LoanProduct SET Active = 0 WHERE ProductID = ?
                    """, (product_id,))
                    conn.commit()
                    flash('✅ Product deactivated successfully!', 'success')
                
                return redirect(url_for('settings_bp.products'))
            
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
                print(traceback.format_exc())
        
        # GET - Load all products
        cursor.execute("""
            SELECT 
                ProductID, ProductName, ProductCode, Description,
                MinAmount, MaxAmount, InterestRate, MinTenure, MaxTenure,
                Active, ProcessingFee, Savings, PaymentFrequency,
                SecurityDeposit, MemberInsurance, NomineeInsurance
            FROM LoanProduct
            ORDER BY ProductName
        """)
        products = cursor.fetchall()
        
        return render_template('settings_products.html', products=products)
    
    except Exception:
        flash('Error loading products', 'danger')
        print(traceback.format_exc())
        return render_template('settings_products.html', products=[])
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  LOAN PURPOSE MASTER
# ═══════════════════════════════════════════════════════════════
@settings_bp.route('/loan-purposes', methods=['GET', 'POST'])
def loan_purposes():
    """Loan Purpose Master"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # POST - Add/Update Purpose
        if request.method == 'POST':
            try:
                action = request.form.get('action')
                
                if action == 'add':
                    purpose_name = request.form.get('PurposeName')
                    description = request.form.get('Description', '')
                    is_active = 1 if request.form.get('IsActive') else 0
                    
                    cursor.execute("""
                        INSERT INTO LoanPurpose (
                            PurposeName, Description, IsActive, CreatedAt
                        )
                        VALUES (?, ?, ?, GETDATE())
                    """, (purpose_name, description, is_active))
                    
                    conn.commit()
                    flash('✅ Loan purpose added successfully!', 'success')
                
                elif action == 'update':
                    purpose_id = request.form.get('LoanPurposeID')
                    purpose_name = request.form.get('PurposeName')
                    is_active = 1 if request.form.get('IsActive') else 0
                    
                    cursor.execute("""
                        UPDATE LoanPurpose
                        SET PurposeName = ?,
                            IsActive = ?,
                            UpdatedAt = GETDATE()
                        WHERE LoanPurposeID = ?
                    """, (purpose_name, is_active, purpose_id))
                    
                    conn.commit()
                    flash('✅ Loan purpose updated successfully!', 'success')
                
                return redirect(url_for('settings_bp.loan_purposes'))
            
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
                print(traceback.format_exc())
        
        # GET - Load all purposes
        cursor.execute("""
            SELECT LoanPurposeID, PurposeName, Description, IsActive, CreatedAt
            FROM LoanPurpose
            ORDER BY PurposeName
        """)
        purposes = cursor.fetchall()
        
        return render_template('settings_loan_purposes.html', purposes=purposes)
    
    except Exception:
        flash('Error loading loan purposes', 'danger')
        print(traceback.format_exc())
        return render_template('settings_loan_purposes.html', purposes=[])
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  PREPAID TYPE MASTER
# ═══════════════════════════════════════════════════════════════
@settings_bp.route('/prepaid-types', methods=['GET', 'POST'])
def prepaid_types():
    """Prepaid Type Master"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # POST - Add/Update Prepaid Type
        if request.method == 'POST':
            try:
                action = request.form.get('action')
                
                if action == 'add':
                    prepaid_type_name = request.form.get('prepaidtypename')
                    has_charges = 1 if request.form.get('haspreclosurecharges') else 0
                    charges_percent = float(request.form.get('preclosurechargespercent', 0))
                    full_interest = 1 if request.form.get('fullinterest') else 0
                    full_savings = 1 if request.form.get('fullsavings') else 0
                    active = 1 if request.form.get('active') else 1
                    
                    cursor.execute("""
                        INSERT INTO PrepaidType (
                            prepaidtypename, active, haspreclosurecharges,
                            preclosurechargespercent, fullinterest, fullsavings,
                            createdby, createddate
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
                    """, (prepaid_type_name, active, has_charges, charges_percent,
                          full_interest, full_savings, session.get('user_id', 1)))
                    
                    conn.commit()
                    flash('✅ Prepaid type added successfully!', 'success')
                
                elif action == 'update':
                    prepaid_type_id = request.form.get('prepaidtypeid')
                    prepaid_type_name = request.form.get('prepaidtypename')
                    active = 1 if request.form.get('active') else 0
                    
                    cursor.execute("""
                        UPDATE PrepaidType
                        SET prepaidtypename = ?,
                            active = ?,
                            modifiedby = ?,
                            modifieddate = GETDATE()
                        WHERE prepaidtypeid = ?
                    """, (prepaid_type_name, active, 
                          session.get('user_id', 1), prepaid_type_id))
                    
                    conn.commit()
                    flash('✅ Prepaid type updated successfully!', 'success')
                
                return redirect(url_for('settings_bp.prepaid_types'))
            
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
                print(traceback.format_exc())
        
        # GET - Load all prepaid types
        cursor.execute("""
            SELECT 
                prepaidtypeid, prepaidtypename, active,
                haspreclosurecharges, preclosurechargespercent,
                fullinterest, fullsavings
            FROM PrepaidType
            ORDER BY prepaidtypename
        """)
        prepaid_types = cursor.fetchall()
        
        return render_template('settings_prepaid_types.html', prepaid_types=prepaid_types)
    
    except Exception:
        flash('Error loading prepaid types', 'danger')
        print(traceback.format_exc())
        return render_template('settings_prepaid_types.html', prepaid_types=[])
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  ROLE MASTER
# ═══════════════════════════════════════════════════════════════
@settings_bp.route('/roles', methods=['GET', 'POST'])
def roles():
    """Role Master"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # POST - Add/Update Role
        if request.method == 'POST':
            try:
                action = request.form.get('action')
                
                if action == 'add':
                    role_name = request.form.get('RoleName')
                    description = request.form.get('Description', '')
                    is_active = 1 if request.form.get('IsActive') else 1
                    
                    cursor.execute("""
                        INSERT INTO Roles (
                            RoleName, Description, IsActive, CreatedAt
                        )
                        VALUES (?, ?, ?, GETDATE())
                    """, (role_name, description, is_active))
                    
                    conn.commit()
                    flash('✅ Role added successfully!', 'success')
                
                elif action == 'update':
                    role_id = request.form.get('RoleID')
                    role_name = request.form.get('RoleName')
                    is_active = 1 if request.form.get('IsActive') else 0
                    
                    cursor.execute("""
                        UPDATE Roles
                        SET RoleName = ?,
                            IsActive = ?,
                            ModifiedAt = GETDATE()
                        WHERE RoleID = ?
                    """, (role_name, is_active, role_id))
                    
                    conn.commit()
                    flash('✅ Role updated successfully!', 'success')
                
                return redirect(url_for('settings_bp.roles'))
            
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
                print(traceback.format_exc())
        
        # GET - Load all roles
        cursor.execute("""
            SELECT RoleID, RoleName, Description, IsActive, CreatedAt
            FROM Roles
            ORDER BY RoleName
        """)
        roles = cursor.fetchall()
        
        return render_template('settings_roles.html', roles=roles)
    
    except Exception:
        flash('Error loading roles', 'danger')
        print(traceback.format_exc())
        return render_template('settings_roles.html', roles=[])
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  MENU MASTER
# ═══════════════════════════════════════════════════════════════
@settings_bp.route('/menus', methods=['GET', 'POST'])
def menus():
    """Menu Master"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # POST - Add/Update Menu
        if request.method == 'POST':
            try:
                action = request.form.get('action')
                
                if action == 'add':
                    menu_name = request.form.get('menu_name')
                    menu_url = request.form.get('menu_url', '')
                    menu_icon = request.form.get('menu_icon', '')
                    parent_id = request.form.get('parent_id') or None
                    display_order = int(request.form.get('display_order', 0))
                    is_active = 1 if request.form.get('is_active') else 1
                    
                    cursor.execute("""
                        INSERT INTO MenuMaster (
                            menu_name, menu_url, menu_icon, parent_id,
                            display_order, is_active, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, GETDATE())
                    """, (menu_name, menu_url, menu_icon, parent_id,
                          display_order, is_active))
                    
                    conn.commit()
                    flash('✅ Menu added successfully!', 'success')
                
                elif action == 'update':
                    menu_id = request.form.get('id')
                    menu_name = request.form.get('menu_name')
                    is_active = 1 if request.form.get('is_active') else 0
                    
                    cursor.execute("""
                        UPDATE MenuMaster
                        SET menu_name = ?,
                            is_active = ?
                        WHERE id = ?
                    """, (menu_name, is_active, menu_id))
                    
                    conn.commit()
                    flash('✅ Menu updated successfully!', 'success')
                
                return redirect(url_for('settings_bp.menus'))
            
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
                print(traceback.format_exc())
        
        # GET - Load all menus
        cursor.execute("""
            SELECT id, menu_name, menu_url, menu_icon, 
                   parent_id, display_order, is_active
            FROM MenuMaster
            ORDER BY display_order, menu_name
        """)
        menus = cursor.fetchall()
        
        return render_template('settings_menus.html', menus=menus)
    
    except Exception:
        flash('Error loading menus', 'danger')
        print(traceback.format_exc())
        return render_template('settings_menus.html', menus=[])
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════
#  ROLE PERMISSIONS
# ═══════════════════════════════════════════════════════════════
@settings_bp.route('/role-permissions', methods=['GET', 'POST'])
def role_permissions():
    """Role Permission Master"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # POST - Update Permissions
        if request.method == 'POST':
            try:
                role_id = request.form.get('role_id')
                menu_id = request.form.get('menu_id')
                can_view = 1 if request.form.get('can_view') else 0
                can_add = 1 if request.form.get('can_add') else 0
                can_edit = 1 if request.form.get('can_edit') else 0
                can_delete = 1 if request.form.get('can_delete') else 0
                
                # Check if permission exists
                cursor.execute("""
                    SELECT id FROM RolePermissions
                    WHERE role_id = ? AND menu_id = ?
                """, (role_id, menu_id))
                
                existing = cursor.fetchone()
                
                if existing:
                    # Update
                    cursor.execute("""
                        UPDATE RolePermissions
                        SET can_view = ?, can_add = ?, can_edit = ?, can_delete = ?
                        WHERE role_id = ? AND menu_id = ?
                    """, (can_view, can_add, can_edit, can_delete, role_id, menu_id))
                else:
                    # Insert
                    cursor.execute("""
                        INSERT INTO RolePermissions (
                            role_id, menu_id, can_view, can_add, can_edit, can_delete, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, GETDATE())
                    """, (role_id, menu_id, can_view, can_add, can_edit, can_delete))
                
                conn.commit()
                flash('✅ Permissions updated successfully!', 'success')
                return redirect(url_for('settings_bp.role_permissions'))
            
            except Exception as e:
                conn.rollback()
                flash(f'Error: {str(e)}', 'danger')
                print(traceback.format_exc())
        
        # GET - Load roles and menus
        cursor.execute("SELECT RoleID, RoleName FROM Roles WHERE IsActive = 1")
        roles = cursor.fetchall()
        
        cursor.execute("SELECT id, menu_name FROM MenuMaster WHERE is_active = 1 ORDER BY display_order")
        menus = cursor.fetchall()
        
        # Load existing permissions
        cursor.execute("""
            SELECT role_id, menu_id, can_view, can_add, can_edit, can_delete
            FROM RolePermissions
        """)
        permissions = cursor.fetchall()
        
        # Convert to dict for easy lookup
        perm_dict = {}
        for p in permissions:
            key = f"{p[0]}_{p[1]}"
            perm_dict[key] = {
                'can_view': p[2],
                'can_add': p[3],
                'can_edit': p[4],
                'can_delete': p[5]
            }
        
        return render_template('settings_role_permissions.html', 
                             roles=roles, menus=menus, permissions=perm_dict)
    
    except Exception:
        flash('Error loading role permissions', 'danger')
        print(traceback.format_exc())
        return render_template('settings_role_permissions.html', 
                             roles=[], menus=[], permissions={})
    finally:
        if conn:
            conn.close()
