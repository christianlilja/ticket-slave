from flask import render_template, current_app
from jinja2 import TemplateNotFound, TemplateSyntaxError

def register_error_handlers(app):
    @app.errorhandler(TemplateNotFound)
    def handle_template_not_found(e):
        current_app.logger.error(f"TemplateNotFound: {e}")
        return render_template("error.html", error="Template not found", details=str(e)), 500

    @app.errorhandler(TemplateSyntaxError)
    def handle_template_syntax_error(e):
        current_app.logger.error(f"Template syntax error: {e}")
        msg = "There is a syntax issue in one of the templates."
        return render_template("error.html", error=msg), 500

    @app.errorhandler(403)
    def forbidden_error(e):
        current_app.logger.warning(f"403 Error: {e}")
        return render_template("error.html", error="Forbidden Access (403)"), 403

    @app.errorhandler(404)
    def not_found_error(e):
        current_app.logger.warning(f"404 Error: {e}")
        return render_template("error.html", error="Page not found (404)"), 404

    @app.errorhandler(500)
    def internal_error(e):
        current_app.logger.error(f"500 Error: {e}")
        if current_app.debug:
            return render_template("error.html", error="Internal Server Error (500)", details=str(e)), 500
        else:
            return render_template("error.html", error="Something went wrong on our end."), 500
