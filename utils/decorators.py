"""
Custom decorators for Flask view functions.

This module provides decorators to handle common concerns in web applications,
such as authentication (login required), authorization (admin required),
and centralized exception handling for view functions.
"""
from functools import wraps # Used to preserve metadata of the decorated function.
from flask import session, redirect, url_for, flash, current_app # Flask utilities.

def login_required(f):
    """
    Decorator to ensure that a user is logged in before accessing a route.

    If the 'user_id' is not found in the current session, it flashes a
    warning message and redirects the user to the login page ('auth_bp.login').
    Otherwise, it allows the decorated view function to execute.

    Args:
        f (callable): The view function to be decorated.

    Returns:
        callable: The decorated function.
    """
    @wraps(f) # Preserves the original function's name, docstring, etc.
    def decorated_function(*args, **kwargs):
        # Check if 'user_id' is present in the session, indicating a logged-in user.
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            # Redirect to the login page defined in the 'auth_bp' blueprint.
            return redirect(url_for('auth_bp.login'))
        # If logged in, proceed to call the original view function.
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Decorator to ensure that the logged-in user has administrator privileges.

    This decorator should typically be used after `@login_required` or on routes
    where login is implicitly handled. It checks if `session.get('is_admin')`
    is True. If not, it flashes an error message and redirects the user to the
    main index page ('main_bp.index').

    Args:
        f (callable): The view function to be decorated.

    Returns:
        callable: The decorated function.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if 'is_admin' flag in session is True.
        # Assumes 'is_admin' is set correctly during login for admin users.
        if not session.get('is_admin'): # Using .get() avoids KeyError if 'is_admin' is not set.
            flash('Administrator access is required to view this page.', 'danger')
            # Redirect to the main application index page.
            return redirect(url_for('main_bp.index'))
        # If user is an admin, proceed to call the original view function.
        return f(*args, **kwargs)
    return decorated_function

def handle_view_exceptions(logger_param=None, flash_error_message="An unexpected error occurred. Please try again.", redirect_endpoint='main_bp.index'):
    """
    A decorator for robust exception handling in Flask view functions.

    It wraps the decorated view function in a try-except block. If any
    exception occurs during the execution of the view:
    1. The exception is logged (using `current_app.logger` or a provided logger).
    2. A user-friendly error message is flashed.
    3. The user is redirected to a specified fallback endpoint.

    This helps in providing a consistent error handling mechanism and prevents
    unhandled exceptions from crashing the application or exposing raw error
    details to the user.

    Args:
        logger_param (logging.Logger, optional): A specific logger instance to use.
            If None, `current_app.logger` is used. This allows for custom logging
            per decorated route if needed. Defaults to None.
        flash_error_message (str, optional): The message to flash to the user
            when an exception occurs. Defaults to "An unexpected error occurred. Please try again.".
        redirect_endpoint (str, optional): The Flask endpoint (e.g., 'blueprint_name.view_function_name')
            to redirect the user to after an exception. Defaults to 'main_bp.index'.

    Returns:
        callable: A new function that wraps the original view function with
                  exception handling logic.
    """
    # The logger (`actual_logger`) is resolved inside the `decorated_function`
    # to ensure that `current_app` (and thus `current_app.logger`) is available
    # within an active application context when the view is actually called.
    # This was a key fix to prevent "working outside of application context" errors.

    def decorator(f): # This is the actual decorator that takes the function `f`.
        @wraps(f)
        def decorated_function(*args, **kwargs): # This wrapper is called when the route is accessed.
            # Determine the logger to use within the request context.
            # If logger_param was passed to the decorator, use it; otherwise, use current_app.logger.
            actual_logger = logger_param if logger_param else current_app.logger
            
            try:
                # Attempt to execute the original view function.
                return f(*args, **kwargs)
            except Exception as e:
                # If any exception occurs:
                # Attempt to get relevant IDs from route kwargs or session for better logging context.
                ticket_id = kwargs.get('ticket_id') # Common in ticket-related views.
                user_id_from_session = session.get('user_id') # Logged-in user, if any.
                
                # Prepare extra information for structured logging.
                log_extra_context = {'endpoint': f.__name__} # Name of the view function where error occurred.
                if ticket_id:
                    log_extra_context['ticket_id'] = ticket_id
                if user_id_from_session:
                    log_extra_context['session_user_id'] = user_id_from_session
                
                # Log the error with details and stack trace.
                actual_logger.error(
                    f"Error in view function '{f.__name__}': {e}", # Brief error message.
                    exc_info=True,  # Include full exception information (stack trace).
                    extra=log_extra_context # Add custom contextual information.
                )
                
                # Flash a user-friendly message.
                flash(flash_error_message, "danger")
                
                # Redirect to the specified fallback endpoint.
                # Pass along original kwargs if the redirect endpoint might use them (e.g., for dynamic routes).
                return redirect(url_for(redirect_endpoint, **kwargs))
        return decorated_function
    return decorator
