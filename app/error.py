from flask import render_template, current_app, request, session
from jinja2 import TemplateNotFound, TemplateSyntaxError

def register_error_handlers(app):
    @app.errorhandler(TemplateNotFound)
    def handle_template_not_found(e):
        current_app.logger.exception(
            "TemplateNotFound error",
            extra={
                'error_details': str(e),
                'requested_url': request.url,
                'user_id': session.get('user_id')
            }
        )
        return render_template("error.html", error="Template not found", details=str(e) if current_app.debug else None), 500

    @app.errorhandler(TemplateSyntaxError)
    def handle_template_syntax_error(e):
        current_app.logger.exception(
            "TemplateSyntaxError",
            extra={
                'error_details': str(e),
                'template_file': e.filename if hasattr(e, 'filename') else 'Unknown',
                'line_number': e.lineno if hasattr(e, 'lineno') else 'Unknown',
                'requested_url': request.url,
                'user_id': session.get('user_id')
            }
        )
        msg = "There is a syntax issue in one of the templates."
        return render_template("error.html", error=msg, details=str(e) if current_app.debug else None), 500

    @app.errorhandler(403)
    def forbidden_error(e):
        current_app.logger.warning(
            "Forbidden access (403)",
            extra={
                'error_details': str(e),
                'requested_url': request.url,
                'user_id': session.get('user_id'),
                'user_agent': request.user_agent.string,
                'ip_address': request.remote_addr
            }
        )
        return render_template("error.html", error="Forbidden Access (403)"), 403

    @app.errorhandler(404)
    def not_found_error(e):
        current_app.logger.warning(
            "Page not found (404)",
            extra={
                'error_details': str(e),
                'requested_url': request.url,
                'user_id': session.get('user_id'),
                'referrer': request.referrer
            }
        )
        return render_template("error.html", error="Page not found (404)"), 404

    @app.errorhandler(Exception) # Catch-all for other 500-type errors
    def internal_error(e):
        # For specific 500 errors, they might be caught here if not handled by a more specific handler
        # For a generic exception, it's good to use logger.exception to get the stack trace
        current_app.logger.exception(
            "Unhandled Internal Server Error (500)",
            extra={
                'error_details': str(e),
                'requested_url': request.url,
                'user_id': session.get('user_id')
            }
        )
        if current_app.debug:
            return render_template("error.html", error="Internal Server Error (500)", details=str(e)), 500
        else:
            return render_template("error.html", error="Something went wrong on our end. We've been notified!"), 500
