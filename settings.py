# settings.py - MINIMAL COMPLETE VERSION
# Has all routes needed for settings_dashboard.html

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
import traceback

settings_bp = Blueprint('settings_bp', __name__, template_folder='templates')


def check_table_exists(cursor, table_name):
    try:
        cursor.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", (table_name,))
        return cursor.fetchone()[0] > 0
    except:
        return False


@settings_bp.route('/')
def settings():
    """Settings Dashboard"""
    return render_template('settings_dashboard.html')


# ============ PRODUCTS ============
@settings_bp.route('/products', methods=['GET', 'POST'])
def products():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if not check_table_exists(cursor, 'LoanProduct'):
            flash('⚠️ LoanProduct table does not exist', 'warning')
            return render_template('settings_products.html', products=[])
        
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                cursor.execute("""
                    INSERT INTO LoanProduct (
                        ProductName, ProductCode, Description, MinAmount, MaxAmount,
                        InterestRate, MinTenure, MaxTenure, Active, CreatedAt, ModifiedBy, ModifiedDate
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, GETDATE())
                """, (
                    request.form.get('ProductName'),
                    request.form.get('ProductCode', ''),
                    request.form.get('Description', ''),
                    float(request.form.get('MinAmount', 0)),
                    float(request.form.get('MaxAmount', 0)),
                    float(request.form.get('InterestRate', 0)),
                    int(request.form.get('MinTenure', 0)),
                    int(request.form.get('MaxTenure', 0)),
                    1 if request.form.get('Active') else 0,
                    session.get('user_id', 1)
                ))
                conn.commit()
                flash('✅ Product added!', 'success')
            return redirect(url_for('settings_bp.products'))
        
        cursor.execute("SELECT ProductID, ProductName, ProductCode, Description, MinAmount, MaxAmount, InterestRate, MinTenure, MaxTenure, Active FROM LoanProduct ORDER BY ProductName")
        products = cursor.fetchall()
        return render_template('settings_products.html', products=products)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('settings_products.html', products=[])
    finally:
        if conn:
            conn.close()


# ============ LOAN PURPOSES ============
@settings_bp.route('/loan-purposes', methods=['GET', 'POST'])
def loan_purposes():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if not check_table_exists(cursor, 'LoanPurpose'):
            flash('⚠️ LoanPurpose table does not exist', 'warning')
            return render_template('settings_loan_purposes.html', purposes=[])
        
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                cursor.execute("INSERT INTO LoanPurpose (PurposeName, Description, IsActive, CreatedAt) VALUES (?, ?, ?, GETDATE())",
                             (request.form.get('PurposeName'), request.form.get('Description', ''), 1 if request.form.get('IsActive') else 0))
                conn.commit()
                flash('✅ Purpose added!', 'success')
            elif action == 'update':
                cursor.execute("UPDATE LoanPurpose SET PurposeName = ?, IsActive = ? WHERE LoanPurposeID = ?",
                             (request.form.get('PurposeName'), 1 if request.form.get('IsActive') else 0, request.form.get('LoanPurposeID')))
                conn.commit()
                flash('✅ Purpose updated!', 'success')
            return redirect(url_for('settings_bp.loan_purposes'))
        
        cursor.execute("SELECT LoanPurposeID, PurposeName, Description, IsActive FROM LoanPurpose ORDER BY PurposeName")
        purposes = cursor.fetchall()
        return render_template('settings_loan_purposes.html', purposes=purposes)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('settings_loan_purposes.html', purposes=[])
    finally:
        if conn:
            conn.close()


# ============ PREPAID TYPES ============
@settings_bp.route('/prepaid-types', methods=['GET', 'POST'])
def prepaid_types():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if not check_table_exists(cursor, 'PrepaidType'):
            flash('⚠️ PrepaidType table does not exist', 'warning')
            return render_template('settings_prepaid_types.html', types=[])
        
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                cursor.execute("INSERT INTO PrepaidType (TypeName, Description, IsActive, CreatedAt) VALUES (?, ?, ?, GETDATE())",
                             (request.form.get('TypeName'), request.form.get('Description', ''), 1 if request.form.get('IsActive') else 0))
                conn.commit()
                flash('✅ Type added!', 'success')
            elif action == 'update':
                cursor.execute("UPDATE PrepaidType SET TypeName = ?, IsActive = ? WHERE PrepaidTypeID = ?",
                             (request.form.get('TypeName'), 1 if request.form.get('IsActive') else 0, request.form.get('PrepaidTypeID')))
                conn.commit()
                flash('✅ Type updated!', 'success')
            return redirect(url_for('settings_bp.prepaid_types'))
        
        cursor.execute("SELECT PrepaidTypeID, TypeName, Description, IsActive FROM PrepaidType ORDER BY TypeName")
        types = cursor.fetchall()
        return render_template('settings_prepaid_types.html', types=types)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('settings_prepaid_types.html', types=[])
    finally:
        if conn:
            conn.close()


# ============ ROLES ============
@settings_bp.route('/roles', methods=['GET', 'POST'])
def roles():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if not check_table_exists(cursor, 'Roles'):
            flash('⚠️ Roles table does not exist', 'warning')
            return render_template('settings_roles.html', roles=[])
        
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                cursor.execute("INSERT INTO Roles (RoleName, Description, IsActive, CreatedAt, ModifiedAt) VALUES (?, ?, ?, GETDATE(), GETDATE())",
                             (request.form.get('RoleName'), request.form.get('Description', ''), 1 if request.form.get('IsActive') else 1))
                conn.commit()
                flash('✅ Role added!', 'success')
            elif action == 'update':
                cursor.execute("UPDATE Roles SET RoleName = ?, IsActive = ?, ModifiedAt = GETDATE() WHERE RoleID = ?",
                             (request.form.get('RoleName'), 1 if request.form.get('IsActive') else 0, request.form.get('RoleID')))
                conn.commit()
                flash('✅ Role updated!', 'success')
            return redirect(url_for('settings_bp.roles'))
        
        cursor.execute("SELECT RoleID, RoleName, Description, IsActive, CreatedAt FROM Roles ORDER BY RoleName")
        roles = cursor.fetchall()
        return render_template('settings_roles.html', roles=roles)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('settings_roles.html', roles=[])
    finally:
        if conn:
            conn.close()


# ============ MENUS ============
@settings_bp.route('/menus', methods=['GET', 'POST'])
def menus():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if not check_table_exists(cursor, 'MenuMaster'):
            flash('⚠️ MenuMaster table does not exist', 'warning')
            return render_template('settings_menus.html', menus=[])
        
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                cursor.execute("INSERT INTO MenuMaster (menu_name, menu_url, menu_icon, parent_id, display_order, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, GETDATE())",
                             (request.form.get('menu_name'), request.form.get('menu_url', ''), request.form.get('menu_icon', 'bi bi-circle'),
                              request.form.get('parent_id') or None, int(request.form.get('display_order', 0))))
                conn.commit()
                flash('✅ Menu added!', 'success')
            return redirect(url_for('settings_bp.menus'))
        
        cursor.execute("SELECT id, menu_name, menu_url, menu_icon, parent_id, display_order, is_active FROM MenuMaster ORDER BY display_order")
        menus = cursor.fetchall()
        return render_template('settings_menus.html', menus=menus)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('settings_menus.html', menus=[])
    finally:
        if conn:
            conn.close()


# ============ ROLE PERMISSIONS ============
@settings_bp.route('/role-permissions', methods=['GET', 'POST'])
def role_permissions():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if not check_table_exists(cursor, 'role_permissions'):
            flash('⚠️ role_permissions table does not exist', 'warning')
            return render_template('settings_role_permissions.html', roles=[], menus=[], permissions={})
        
        if request.method == 'POST':
            try:
                # Debug: Show form data
                print(f"DEBUG POST: Form has {len(request.form)} items")
                checked_items = [k for k in request.form.keys() if k.startswith('perm_')]
                print(f"DEBUG POST: {len(checked_items)} permissions checked")
                print(f"DEBUG POST: First 5 checked: {checked_items[:5]}")
                
                # Get all roles and menus
                cursor.execute("SELECT RoleID FROM Roles WHERE IsActive = 1")
                all_role_ids = [r[0] for r in cursor.fetchall()]
                
                cursor.execute("SELECT id FROM MenuMaster WHERE is_active = 1")
                all_menu_ids = [m[0] for m in cursor.fetchall()]
                
                # Process each role-menu combination
                saved_count = 0
                updated_count = 0
                
                for role_id in all_role_ids:
                    for menu_id in all_menu_ids:
                        # Check checkbox states
                        has_view = f"perm_{role_id}_{menu_id}_view" in request.form
                        has_add = f"perm_{role_id}_{menu_id}_add" in request.form
                        has_edit = f"perm_{role_id}_{menu_id}_edit" in request.form
                        has_delete = f"perm_{role_id}_{menu_id}_delete" in request.form
                        
                        # Check if permission exists
                        cursor.execute("SELECT id FROM role_permissions WHERE role_id = ? AND menu_id = ?", (role_id, menu_id))
                        existing = cursor.fetchone()
                        
                        if existing:
                            # Update existing permission
                            cursor.execute("""
                                UPDATE role_permissions 
                                SET can_view = ?, can_add = ?, can_edit = ?, can_delete = ? 
                                WHERE role_id = ? AND menu_id = ?
                            """, (1 if has_view else 0, 1 if has_add else 0, 
                                  1 if has_edit else 0, 1 if has_delete else 0, role_id, menu_id))
                            updated_count += 1
                        else:
                            # Only create new permission if at least one checkbox is checked
                            if has_view or has_add or has_edit or has_delete:
                                cursor.execute("""
                                    INSERT INTO role_permissions 
                                    (role_id, menu_id, can_view, can_add, can_edit, can_delete, created_at)
                                    VALUES (?, ?, ?, ?, ?, ?, GETDATE())
                                """, (role_id, menu_id, 1 if has_view else 0, 1 if has_add else 0,
                                      1 if has_edit else 0, 1 if has_delete else 0))
                                saved_count += 1
                
                conn.commit()
                print(f"DEBUG POST: Saved {saved_count} new, updated {updated_count}")
                flash(f'✅ Permissions saved! ({saved_count} new, {updated_count} updated)', 'success')
                return redirect(url_for('settings_bp.role_permissions'))
            except Exception as e:
                conn.rollback()
                flash(f'❌ Error: {str(e)}', 'danger')
                print(f"DEBUG ERROR: {traceback.format_exc()}")
        
        cursor.execute("SELECT RoleID, RoleName FROM Roles WHERE IsActive = 1 ORDER BY RoleName")
        roles = cursor.fetchall()
        cursor.execute("SELECT id, menu_name, menu_url FROM MenuMaster WHERE is_active = 1 ORDER BY display_order")
        menus = cursor.fetchall()
        cursor.execute("SELECT role_id, menu_id, can_view, can_add, can_edit, can_delete FROM role_permissions")
        permissions = cursor.fetchall()
        
        perm_dict = {}
        for p in permissions:
            perm_dict[f"{p[0]}_{p[1]}"] = {'can_view': bool(p[2]), 'can_add': bool(p[3]), 'can_edit': bool(p[4]), 'can_delete': bool(p[5])}
        
        # Debug output
        print(f"DEBUG: Loaded {len(roles)} roles, {len(menus)} menus, {len(permissions)} permissions")
        print(f"DEBUG: Permission keys: {list(perm_dict.keys())[:5]}...")  # Show first 5
        
        return render_template('settings_role_permissions.html', roles=roles, menus=menus, permissions=perm_dict)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('settings_role_permissions.html', roles=[], menus=[], permissions={})
    finally:
        if conn:
            conn.close()


# ============ BULK PERMISSIONS ============
@settings_bp.route('/bulk-permissions', methods=['GET', 'POST'])
def bulk_permissions():
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if request.method == 'POST':
            role_id = request.form.get('role_id')
            selected_menus = request.form.getlist('menu_ids')
            can_view = 1 if request.form.get('can_view') else 0
            can_add = 1 if request.form.get('can_add') else 0
            can_edit = 1 if request.form.get('can_edit') else 0
            can_delete = 1 if request.form.get('can_delete') else 0
            
            if role_id and selected_menus:
                for menu_id in selected_menus:
                    cursor.execute("SELECT id FROM role_permissions WHERE role_id = ? AND menu_id = ?", (role_id, menu_id))
                    if cursor.fetchone():
                        cursor.execute("UPDATE role_permissions SET can_view = ?, can_add = ?, can_edit = ?, can_delete = ? WHERE role_id = ? AND menu_id = ?",
                                     (can_view, can_add, can_edit, can_delete, role_id, menu_id))
                    else:
                        cursor.execute("INSERT INTO role_permissions (role_id, menu_id, can_view, can_add, can_edit, can_delete, created_at) VALUES (?, ?, ?, ?, ?, ?, GETDATE())",
                                     (role_id, menu_id, can_view, can_add, can_edit, can_delete))
                conn.commit()
                flash(f'✅ {len(selected_menus)} permissions assigned!', 'success')
            return redirect(url_for('settings_bp.role_permissions'))
        
        cursor.execute("SELECT RoleID, RoleName FROM Roles WHERE IsActive = 1 ORDER BY RoleName")
        roles = cursor.fetchall()
        cursor.execute("SELECT id, menu_name, menu_url FROM MenuMaster WHERE is_active = 1 ORDER BY display_order")
        menus = cursor.fetchall()
        return render_template('settings_bulk_permissions.html', roles=roles, menus=menus)
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template('settings_bulk_permissions.html', roles=[], menus=[])
    finally:
        if conn:
            conn.close()
