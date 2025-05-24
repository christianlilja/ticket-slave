"""
Custom error handlers for the Flask application.

This module defines functions to handle common HTTP errors (like 403, 404, 500)
and specific Jinja2 template errors. These handlers ensure that users are shown
a user-friendly error page instead of raw error messages (especially in production)
and that relevant error details are logged for debugging.
"""
from flask import render_template, current_app, request, session
from jinja2 import TemplateNotFound, TemplateSyntaxError # Specific Jinja2 exceptions.
# werkzeug.exceptions can be imported for more specific HTTP exceptions if needed,
# e.g., from werkzeug.exceptions import HTTPException

def register_error_handlers(app):
    """
    Registers custom error handler functions with the Flask application instance.

    Args:
        app (Flask): The Flask application instance to which the error handlers
                     will be attached.
    """

    @app.errorhandler(TemplateNotFound)
    def handle_template_not_found(e):
        """
        Handles errors raised when a Jinja2 template file cannot be found.
        Logs the error and displays a custom 500 error page.
        """
        current_app.logger.exception( # Use .exception() to include stack trace.
            "Jinja2 TemplateNotFound error occurred.",
            extra={
                'error_type': type(e).__name__,
                'error_details': str(e), # Name of the template that was not found.
                'requested_url': request.url,
                'user_id': session.get('user_id'),
                'username': session.get('username')
            }
        )
        # Display a generic error page. In debug mode, more details might be shown.
        # Returning 500 as this is a server-side configuration issue.
        return render_template(
            "error.html",
            error_code=500,
            error_title="Server Configuration Error",
            error_message="A required template file was not found on the server.",
            details=f"Template name: {str(e)}" if current_app.debug else "Please contact support if the issue persists."
        ), 500

    @app.errorhandler(TemplateSyntaxError)
    def handle_template_syntax_error(e):
        """
        Handles errors raised due to syntax issues within a Jinja2 template.
        Logs the error with details (filename, line number) and displays a custom 500 error page.
        """
        current_app.logger.exception( # Use .exception() for stack trace.
            "Jinja2 TemplateSyntaxError occurred.",
            extra={
                'error_type': type(e).__name__,
                'error_details': str(e), # Description of the syntax error.
                'template_file': e.filename if hasattr(e, 'filename') else 'Unknown Template',
                'line_number': e.lineno if hasattr(e, 'lineno') else 'Unknown Line',
                'requested_url': request.url,
                'user_id': session.get('user_id'),
                'username': session.get('username')
            }
        )
        error_msg = "There is a syntax issue in one of the application's templates."
        return render_template(
            "error.html",
            error_code=500,
            error_title="Template Processing Error",
            error_message=error_msg,
            details=f"Error in '{e.filename or 'template'}' at line {e.lineno}: {str(e)}" if current_app.debug else "Please contact support."
        ), 500

    @app.errorhandler(403)
    def forbidden_error(e):
        """
        Handles 403 Forbidden errors (access denied).
        Logs the attempt and displays a custom 403 error page.
        """
        current_app.logger.warning( # Use .warning as it's a client-side access issue, not server fault.
            "Forbidden access attempt (403).",
            extra={
                'error_type': type(e).__name__,
                'error_details': str(e), # Original error description, if any.
                'requested_url': request.url,
                'user_id': session.get('user_id'),
                'username': session.get('username'),
                'user_agent': request.user_agent.string,
                'ip_address': request.remote_addr
            }
        )
        return render_template(
            "error.html",
            error_code=403,
            error_title="Access Forbidden",
            error_message="You do not have permission to access this page or resource."
        ), 403

    @app.errorhandler(404)
    def not_found_error(e):
        """
        Handles 404 Not Found errors (requested resource does not exist).
        Logs the attempt and displays a custom 404 error page.
        """
        current_app.logger.warning( # Use .warning as it's a client request for a non-existent resource.
            "Resource not found (404).",
            extra={
                'error_type': type(e).__name__,
                'error_details': str(e), # Original error description.
                'requested_url': request.url,
                'user_id': session.get('user_id'),
                'username': session.get('username'),
                'referrer': request.referrer # URL from which the user came, if available.
            }
        )
        return render_template(
            "error.html",
            error_code=404,
            error_title="Page Not Found",
            error_message="The page or resource you were looking for could not be found."
        ), 404

    @app.errorhandler(Exception) # Catch-all for any other unhandled exceptions.
    def internal_server_error(e): # Renamed for clarity from 'internal_error'
        """
        Handles all other unhandled exceptions, typically resulting in a 500 Internal Server Error.
        Logs the exception with a full stack trace and displays a generic 500 error page.
        In debug mode, more detailed error information might be shown.
        """
        # Use logger.exception() to automatically include the stack trace in the log.
        current_app.logger.exception(
            "Unhandled Internal Server Error (500) occurred.",
            extra={
                'error_type': type(e).__name__, # Get the type of the exception.
                'error_details': str(e),       # String representation of the exception.
                'requested_url': request.url,
                'user_id': session.get('user_id'),
                'username': session.get('username')
                # Add more context if available, e.g., request.data for POST errors.
            }
        )
        # In production, show a generic error message.
        # In debug mode, more details can be shown for easier debugging.
        if current_app.debug:
            error_details_for_template = f"Exception Type: {type(e).__name__}\nDetails: {str(e)}"
            # For very detailed debugging, one might pass the full traceback, but be cautious.
        else:
            error_details_for_template = "We are sorry, but something went wrong on our end. Our team has been notified."
            
        return render_template(
            "error.html",
            error_code=500,
            error_title="Internal Server Error",
            error_message="An unexpected error occurred on the server.",
            details=error_details_for_template
        ), 500

    app.logger.info("Custom error handlers registered.")
