"""
Application factory for the Flask web application.

This module contains the `create_app` function, which is responsible for
initializing and configuring the Flask application instance. This includes
setting up logging, configurations, error handlers, CSRF protection,
registering blueprints, and initializing the database.
"""
import os
import sys
import logging
from pythonjsonlogger import jsonlogger # For structured JSON logging.
from flask import Flask
from flask_wtf.csrf import CSRFProtect # For Cross-Site Request Forgery protection.
from app.error import register_error_handlers # Custom error page handlers.


# --- Custom JSON Logging Helper Classes ---
class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON log formatter to ensure consistent fields like 'timestamp',
    'level', 'logger_name', and add application-specific default fields.
    """
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        # Ensure standard fields are present if not already added by the formatter.
        if not log_record.get('timestamp'):
            log_record['timestamp'] = record.created  # Unix timestamp (seconds since epoch).
                                                      # Consider datetime.utcnow().isoformat() for ISO 8601.
        if not log_record.get('level'):
            log_record['level'] = record.levelname
        if not log_record.get('logger_name'):
            log_record['logger_name'] = record.name
        
        # Add application-specific static fields.
        log_record['application'] = 'ticketslave' # Name of the application.
        # Example: Add application version from environment variable.
        # log_record['app_version'] = os.environ.get('APP_VERSION', 'unknown')

class StdoutFilter(logging.Filter):
    """
    A logging filter that allows records with level INFO or lower (DEBUG, INFO)
    to pass through. Intended for directing these logs to STDOUT.
    """
    def filter(self, record):
        return record.levelno <= logging.INFO

class StderrFilter(logging.Filter):
    """
    A logging filter that allows records with level WARNING or higher
    (WARNING, ERROR, CRITICAL) to pass through. Intended for directing
    these logs to STDERR.
    """
    def filter(self, record):
        return record.levelno >= logging.WARNING


def create_app():
    """
    Application factory function. Creates, configures, and returns the Flask app instance.
    """
    # --- Determine Base and Data Directories ---
    # base_dir is the project root (one level up from 'app' directory).
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    # data_dir is where persistent data like uploads and instance folder (DB) will be stored.
    # It defaults to a 'data' subdirectory in the project root but can be overridden by DATA_DIR env var.
    data_dir = os.environ.get("DATA_DIR", os.path.join(base_dir, "data"))

    # --- Ensure Essential Directories Exist ---
    # Create 'uploads' and 'instance' directories within data_dir if they don't exist.
    # These are crucial for file uploads and the SQLite database instance path.
    os.makedirs(os.path.join(data_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "instance"), exist_ok=True)

    # --- Initialize Flask Application ---
    app = Flask(
        __name__, # Name of the application module.
        template_folder=os.path.join(base_dir, "templates"), # Path to HTML templates.
        static_folder=os.path.join(base_dir, "static"),     # Path to static files (CSS, JS, images).
        instance_path=os.path.join(data_dir, "instance")    # Path for instance-specific files (e.g., SQLite DB).
                                                            # This is where Flask looks for config files by default
                                                            # and where the SQLite DB is placed.
    )

    # --- Configure Structured JSON Logging ---
    # Remove default Flask and Werkzeug handlers to replace them with custom JSON logging.
    # This provides more control over log output, especially for containerized environments.
    for handler in list(app.logger.handlers): # Iterate over a copy of the list.
        app.logger.removeHandler(handler)
    
    werkzeug_logger = logging.getLogger('werkzeug') # Get Werkzeug's logger (handles HTTP request logs).
    for handler in list(werkzeug_logger.handlers):
        werkzeug_logger.removeHandler(handler)

    # Create and configure the custom JSON formatter.
    json_formatter = CustomJsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d %(message)s'
        # The format string here is somewhat redundant with JsonFormatter but can provide defaults.
    )

    # Handler for STDOUT: Logs DEBUG and INFO messages.
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(json_formatter)
    stdout_handler.addFilter(StdoutFilter()) # Apply filter to select appropriate log levels.
    stdout_handler.setLevel(logging.DEBUG)   # Handler processes all messages from DEBUG up; filter does the selection.

    # Handler for STDERR: Logs WARNING, ERROR, and CRITICAL messages.
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(json_formatter)
    stderr_handler.addFilter(StderrFilter())   # Apply filter.
    stderr_handler.setLevel(logging.WARNING) # Handler processes from WARNING up.

    # Add custom handlers to Flask's application logger.
    app.logger.addHandler(stdout_handler)
    app.logger.addHandler(stderr_handler)
    # Set the overall level for the app logger. If app.debug is True, log DEBUG messages, otherwise INFO.
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)

    # Configure Werkzeug logger to use the same JSON handlers and appropriate level.
    werkzeug_logger.addHandler(stdout_handler)
    werkzeug_logger.addHandler(stderr_handler)
    werkzeug_logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    werkzeug_logger.propagate = False # Prevent Werkzeug logs from also going to the root logger, avoiding duplicates.

    app.logger.info("Application logging configured for JSON output to stdout/stderr.")
    # --- End Logging Setup ---


    # --- Application Configuration ---
    # Define paths for uploads and the database file.
    app.config["UPLOAD_FOLDER"] = os.path.join(data_dir, "uploads") # Consistent with directory creation.
    app.config["DATABASE"] = os.path.join(app.instance_path, "database.db") # SQLite DB in instance folder.

    # Log if the database file doesn't exist yet (it will be created by init_db).
    if not os.path.exists(app.config["DATABASE"]):
        app.logger.info(f"Database file not found at {app.config['DATABASE']}. It will be created upon initialization.")

    # Register custom error handlers (e.g., for 404, 500 errors).
    register_error_handlers(app)

    # Secret Key Configuration: Crucial for session security and CSRF protection.
    IS_PROD = os.environ.get("FLASK_ENV") == "production"
    if IS_PROD and not os.environ.get("SECRET_KEY"):
        app.logger.critical("FATAL: SECRET_KEY environment variable must be set in production. Application cannot start.")
        raise RuntimeError("SECRET_KEY must be set in production for security reasons.")
    # Use SECRET_KEY from environment or a default (INSECURE) key for development.
    app.secret_key = os.environ.get("SECRET_KEY", "default-dev-secret-key-please-change-me")
    if app.secret_key == "default-dev-secret-key-please-change-me":
        app.logger.warning(
            "SECURITY WARNING: Running with a default development secret key. "
            "This is INSECURE and NOT suitable for production. "
            "Set the SECRET_KEY environment variable to a strong, unique random value."
        )

    # Flask-WTF CSRF Protection Configuration.
    app.config['WTF_CSRF_ENABLED'] = True  # Enable CSRF protection (default is True).
    app.config['WTF_CSRF_SECRET_KEY'] = app.secret_key # Use the app's secret key for CSRF token generation.
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # CSRF token validity period in seconds (1 hour default).
    # app.config['WTF_CSRF_CHECK_DEFAULT'] = True # Ensures CSRF check is on by default for relevant form methods.

    # Initialize CSRF protection extension.
    csrf = CSRFProtect(app)
    app.logger.info("CSRF protection initialized for the application.")

    # File Upload Configuration.
    # Note: UPLOAD_FOLDER was already set using data_dir. This re-confirms or could be a slight redundancy.
    # Ensure consistency if this path differs from the one used for os.makedirs.
    # The path `os.path.join(base_dir, "uploads")` might differ from `os.path.join(data_dir, "uploads")`
    # if DATA_DIR is set. Prefer `data_dir` for consistency.
    # Corrected path:
    app.config["UPLOAD_FOLDER"] = os.path.join(data_dir, "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 # 10MB limit for file uploads.

    # --- Register Blueprints ---
    # Blueprints are imported from routes/__init__.py where they are aggregated.
    from routes import blueprints # Expects a list named 'blueprints' in routes/__init__.py
    for bp in blueprints:
        app.register_blueprint(bp)
    app.logger.info(f"Registered {len(blueprints)} blueprints.")

    # --- Template Context Processor ---
    # Injects variables into the context of all templates.
    @app.context_processor
    def inject_version():
        """Injects the application version into template contexts."""
        # Consider making APP_VERSION configurable (e.g., via env var or a file).
        return dict(app_version="v1.0.0") # Example version.

    # --- Database and Default Data Initialization ---
    # These operations require an active application context.
    with app.app_context():
        from app.db import init_db, load_settings, ensure_default_settings, ensure_admin_user, ensure_default_queue
        
        app.logger.info("Initializing database schema and default data within application context...")
        init_db() # Create database tables if they don't exist.
        ensure_default_settings() # Populate essential settings if missing.
        
        default_queue_id = ensure_default_queue() # Ensure a default queue exists and get its ID.
        if default_queue_id is None:
            app.logger.critical(
                "Could not ensure or create the default ticket queue. "
                "This might impact ticket creation if no queue is explicitly selected "
                "and the system relies on a default."
            )
            # Depending on requirements, might raise an error or halt here.
        app.config['DEFAULT_QUEUE_ID'] = default_queue_id # Store default queue ID in app config for later use.
        app.logger.info(f"Default queue ID set in app.config: {default_queue_id}")

        settings = load_settings() # Load all application settings from the database.
        ensure_admin_user()       # Ensure a default admin user exists.

        # Conditionally load API module based on settings.
        if settings.get("enable_api") == "1":
            import app.api # Import the API module (app/api.py).
            # If app.api has an init_app function or registers its own blueprint:
            # e.g., if hasattr(app.api, 'init_api'): app.api.init_api(app)
            app.logger.info("API is enabled in settings and API module has been loaded.")
        else:
            app.logger.info("API is disabled in settings.")

    app.logger.info(f"Flask application '{app.name}' created and configured successfully. Debug mode: {app.debug}")
    return app
