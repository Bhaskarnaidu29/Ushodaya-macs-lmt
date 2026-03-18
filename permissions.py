# permissions.py - RECTIFIED & COMPLETE
# Role-Based Permission System with all functions and error handling

from flask import session, redirect, url_for, flash
from functools import wraps
from db import get_db_connection


# --------------------------------------------------
# GET USER ROLE
# --------------------------------------------------

def get_user_role(user_id):
    """Get role_id for a user"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT role_id FROM Employee WHERE EmpId = ?", (user_id,))
        row = cursor.fetchone()
        
        return row[0] if row else None
        
    except Exception as e:
        print(f"Error getting user role: {e}")
        return None
    finally:
        if conn:
            conn.close()


# --------------------------------------------------
# GET USER PERMISSIONS
# --------------------------------------------------

def get_user_permissions(user_id):
    """Get all permissions for a user based on their role"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        role_id = get_user_role(user_id)
        
        if not role_id:
            return {}
        
        cursor.execute("""
            SELECT rp.menu_id,
                   rp.can_view,
                   rp.can_add,
                   rp.can_edit,
                   rp.can_delete,
                   mm.menu_url
            FROM role_permissions rp
            JOIN MenuMaster mm ON rp.menu_id = mm.id
            WHERE rp.role_id = ?
              AND mm.is_active = 1
        """, (role_id,))
        
        permissions = {}
        
        for row in cursor.fetchall():
            permissions[row[0]] = {
                "can_view": bool(row[1]),
                "can_add": bool(row[2]),
                "can_edit": bool(row[3]),
                "can_delete": bool(row[4]),
                "menu_url": row[5]
            }
        
        return permissions
        
    except Exception as e:
        print(f"Error getting user permissions: {e}")
        return {}
    finally:
        if conn:
            conn.close()


# --------------------------------------------------
# GET USER MENUS (FIXED - includes all fields)
# --------------------------------------------------

def get_user_menus(user_id):
    """Get all accessible menus for a user (including VIEW-ONLY)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        role_id = get_user_role(user_id)
        
        if not role_id:
            return []
        
        cursor.execute("""
            SELECT
                mm.id,
                mm.menu_name,
                mm.menu_url,
                mm.menu_icon,
                mm.parent_id,
                mm.display_order,
                rp.can_view,
                rp.can_add,
                rp.can_edit,
                rp.can_delete
            FROM MenuMaster mm
            JOIN role_permissions rp ON mm.id = rp.menu_id
            WHERE rp.role_id = ?
              AND rp.can_view = 1
              AND mm.is_active = 1
            ORDER BY mm.display_order, mm.menu_name
        """, (role_id,))
        
        menus = []
        
        for row in cursor.fetchall():
            menus.append({
                "id": row[0],
                "name": row[1],
                "url": row[2],
                "icon": row[3],
                "parent_id": row[4],
                "order": row[5],
                "can_view": bool(row[6]),
                "can_add": bool(row[7]),
                "can_edit": bool(row[8]),
                "can_delete": bool(row[9]),
                "readonly": bool(row[6]) and not bool(row[7]) and not bool(row[8]) and not bool(row[9])
            })
        
        return menus
        
    except Exception as e:
        print(f"Error getting user menus: {e}")
        return []
    finally:
        if conn:
            conn.close()


# --------------------------------------------------
# CHECK PERMISSION (FIXED - with admin bypass and error handling)
# --------------------------------------------------

def check_permission(menu_url, permission_type="view"):
    """
    Check if current user has specific permission for a menu
    
    Args:
        menu_url: URL path of the menu (e.g., '/members')
        permission_type: 'view', 'add', 'edit', or 'delete'
    
    Returns:
        bool: True if user has permission, False otherwise
    """
    user_id = session.get("user_id")
    
    if not user_id:
        return False
    
    # Admin bypass (optional - uncomment if admins should bypass permissions)
    # if session.get("role") == "Admin":
    #     return True
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        role_id = get_user_role(user_id)
        
        if not role_id:
            return False
        
        column = f"can_{permission_type}"
        
        query = f"""
            SELECT rp.{column}
            FROM role_permissions rp
            JOIN MenuMaster mm ON rp.menu_id = mm.id
            WHERE rp.role_id = ?
              AND mm.menu_url = ?
              AND mm.is_active = 1
        """
        
        cursor.execute(query, (role_id, menu_url))
        row = cursor.fetchone()
        
        return bool(row[0]) if row else False
        
    except Exception as e:
        print(f"Error checking permission: {e}")
        return False
    finally:
        if conn:
            conn.close()


# --------------------------------------------------
# ROUTE PROTECTION DECORATOR
# --------------------------------------------------

def require_permission(menu_url, permission_type="view"):
    """
    Decorator to require specific permission for a route
    
    Usage:
        @app.route('/members')
        @require_permission('/members', 'view')
        def members():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            
            if not session.get("user_id"):
                flash("Please login first", "warning")
                return redirect(url_for("login"))
            
            if not check_permission(menu_url, permission_type):
                
                if permission_type != "view" and check_permission(menu_url, "view"):
                    session["readonly_mode"] = True
                    flash("View only permission", "warning")
                else:
                    flash("Access denied", "danger")
                    return redirect(url_for("home"))
            else:
                session["readonly_mode"] = False
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


# --------------------------------------------------
# GET MENU PERMISSIONS
# --------------------------------------------------

def get_menu_permissions(menu_url):
    """
    Get all permission flags for current user for a specific menu
    Returns dict: {'can_view': bool, 'can_add': bool, 'can_edit': bool, 'can_delete': bool, 'readonly': bool}
    """
    perms = {
        "can_view": check_permission(menu_url, "view"),
        "can_add": check_permission(menu_url, "add"),
        "can_edit": check_permission(menu_url, "edit"),
        "can_delete": check_permission(menu_url, "delete"),
    }
    
    perms["readonly"] = (
        perms["can_view"]
        and not perms["can_add"]
        and not perms["can_edit"]
        and not perms["can_delete"]
    )
    
    return perms


# --------------------------------------------------
# IS READONLY ACCESS (NEW - MISSING FUNCTION)
# --------------------------------------------------

def is_readonly_access(menu_url):
    """
    Check if user has ONLY view permission (read-only mode)
    Returns True if user can view but not add/edit/delete
    """
    return (check_permission(menu_url, "view") and 
            not check_permission(menu_url, "add") and 
            not check_permission(menu_url, "edit") and 
            not check_permission(menu_url, "delete"))


# --------------------------------------------------
# HAS ANY PERMISSION (NEW - MISSING FUNCTION)
# --------------------------------------------------

def has_any_permission(menu_url):
    """
    Check if user has ANY permission (view/add/edit/delete) for a menu
    Useful for checking if menu item should be shown at all
    """
    return (check_permission(menu_url, "view") or 
            check_permission(menu_url, "add") or 
            check_permission(menu_url, "edit") or 
            check_permission(menu_url, "delete"))


# --------------------------------------------------
# GET ROLE NAME (NEW - MISSING FUNCTION)
# --------------------------------------------------

def get_role_name(role_id):
    """Get role name from role ID"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT RoleName FROM Roles WHERE RoleID = ?", (role_id,))
        result = cursor.fetchone()
        
        return result[0] if result else "Unknown"
        
    except Exception as e:
        print(f"Error getting role name: {e}")
        return "Unknown"
    finally:
        if conn:
            conn.close()


# --------------------------------------------------
# GET CURRENT USER ROLE (NEW - MISSING FUNCTION)
# --------------------------------------------------

def get_current_user_role():
    """Get current logged-in user's role name"""
    user_id = session.get("user_id")
    
    if not user_id:
        return None
    
    role_id = get_user_role(user_id)
    
    if not role_id:
        return None
    
    return get_role_name(role_id)


# --------------------------------------------------
# GET CURRENT USER ROLE ID (NEW - HELPER FUNCTION)
# --------------------------------------------------

def get_current_user_role_id():
    """Get current logged-in user's role ID"""
    user_id = session.get("user_id")
    
    if not user_id:
        return None
    
    return get_user_role(user_id)
