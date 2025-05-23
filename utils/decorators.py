from functools import wraps
from flask import session, redirect, url_for, flash, current_app

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('main_bp.index'))
        return f(*args, **kwargs)
    return decorated_function

def handle_view_exceptions(logger_param=None, flash_error_message="An unexpected error occurred.", redirect_endpoint='main_bp.index'):
    """
    A decorator to handle common try-except patterns in view functions.
    It logs the error, flashes a message, and redirects.
    """
    # Logger will be resolved inside the decorated function to ensure app context.

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Determine the logger to use within the request context
            actual_logger = logger_param if logger_param else current_app.logger
            try:
                return f(*args, **kwargs)
            except Exception as e:
                # Attempt to get relevant IDs from kwargs for better logging
                ticket_id = kwargs.get('ticket_id')
                user_id_from_session = session.get('user_id')
                
                log_extra = {'endpoint': f.__name__}
                if ticket_id:
                    log_extra['ticket_id'] = ticket_id
                if user_id_from_session:
                    log_extra['session_user_id'] = user_id_from_session
                
                actual_logger.error(
                    f"Error in view function {f.__name__}: {e}",
                    exc_info=True,
                    extra=log_extra
                )
                flash(flash_error_message, "danger")
                return redirect(url_for(redirect_endpoint, **kwargs)) # Pass kwargs for dynamic endpoints
        return decorated_function
    return decorator
