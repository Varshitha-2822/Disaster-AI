
from functools import wraps
from flask import current_app, redirect, url_for, flash
from flask_login import current_user
from database.db import User

def check_role(user, role):
    """Check if user has specific role"""
    if not user or not user.is_authenticated:
        return False
    return user.role == role

def role_required(*roles):
    """Decorator to require specific role(s)"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login'))
            
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    """Decorator to require admin role"""
    return role_required('admin')(f)

def emergency_operator_required(f):
    """Decorator to require emergency operator or admin role"""
    return role_required('admin', 'emergency_operator')(f)
