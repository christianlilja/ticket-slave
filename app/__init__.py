import os
import sys
import logging
from pythonjsonlogger import jsonlogger
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from app.error import register_error_handlers


# Helper classes for JSON logging
class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            log_record['timestamp'] = record.created  # Unix timestamp
        if not log_record.get('level'):
            log_record['level'] = record.levelname
        if not log_record.get('logger_name'):
            log_record['logger_name'] = record.name
        log_record['application'] = 'ticketslave'
        # You can add more default fields here, e.g., application version
        # log_record['app_version'] = os.environ.get('APP_VERSION', 'unknown')

class StdoutFilter(logging.Filter):
    def filter(self, record):
        return record.levelno <= logging.INFO  # DEBUG, INFO

class StderrFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.WARNING  # WARNING, ERROR, CRITICAL


def create_app():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data_dir = os.environ.get("DATA_DIR", os.path.join(base_dir, "data"))  # fallback

    # Ensure folders exist
    os.makedirs(os.path.join(data_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(data_dir, "instance"), exist_ok=True)

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
        instance_path=os.path.join(data_dir, "instance")
    )

    # --- Early Logging Setup ---
    # Remove Flask's default handlers and Werkzeug's default handlers
    for handler in list(app.logger.handlers):
        app.logger.removeHandler(handler)
    
    werkzeug_logger = logging.getLogger('werkzeug')
    for handler in list(werkzeug_logger.handlers):
        werkzeug_logger.removeHandler(handler)

    # Configure JSON formatter
    formatter = CustomJsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(module)s %(funcName)s %(lineno)d %(message)s'
    )

    # Handler for STDOUT (DEBUG, INFO)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(StdoutFilter())
    stdout_handler.setLevel(logging.DEBUG) # Process all, filter will select

    # Handler for STDERR (WARNING, ERROR, CRITICAL)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.addFilter(StderrFilter())
    stderr_handler.setLevel(logging.WARNING) # Process from WARNING up, filter refines

    # Add handlers to Flask's app logger
    app.logger.addHandler(stdout_handler)
    app.logger.addHandler(stderr_handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)

    # Configure Werkzeug logger to use the same handlers
    werkzeug_logger.addHandler(stdout_handler)
    werkzeug_logger.addHandler(stderr_handler)
    werkzeug_logger.setLevel(logging.DEBUG if app.debug else logging.INFO) # Let handlers filter
    werkzeug_logger.propagate = False # Avoid double logging from root

    app.logger.info("Application logging configured for JSON to stdout/stderr.")
    # --- End Early Logging Setup ---


    app.config["UPLOAD_FOLDER"] = os.path.join(data_dir, "uploads")
    app.config["DATABASE"] = os.path.join(app.instance_path, "database.db")

    # Optional: log if the DB doesn't exist yet
    if not os.path.exists(app.config["DATABASE"]):
        app.logger.info("Database file not found. It will be created.")


    register_error_handlers(app)

    # Secret key setup
    IS_PROD = os.environ.get("FLASK_ENV") == "production"
    if IS_PROD and not os.environ.get("SECRET_KEY"):
        # Use logger before raising, so it's captured if possible
        app.logger.critical("SECRET_KEY must be set in production. Application cannot start.")
        raise RuntimeError("SECRET_KEY must be set in production")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
    if app.secret_key == "dev-secret-key":
        app.logger.warning("Running with default DEV secret key. NOT FOR PRODUCTION.")

    # Explicitly set Flask-WTF configurations (optional, but can help with debugging)
    # These are often the defaults, but setting them explicitly can be clearer.
    app.config['WTF_CSRF_ENABLED'] = True  # Default is True
    app.config['WTF_CSRF_SECRET_KEY'] = app.secret_key # Default uses app.secret_key
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # Default is 3600 seconds (1 hour)
    # app.config['WTF_CSRF_CHECK_DEFAULT'] = True # Default is True, CSRF on for all relevant methods

    # Initialize CSRF Protection
    csrf = CSRFProtect(app)
    app.logger.info("CSRF protection initialized.")

    # Upload and database config
    upload_folder = os.path.join(base_dir, "uploads")
    os.makedirs(upload_folder, exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)  # ensure instance folder exists
    app.config["UPLOAD_FOLDER"] = upload_folder
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    app.config["DATABASE"] = os.path.join(app.instance_path, "database.db")

    # Register blueprints
    from routes import blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

    # Template version
    @app.context_processor
    def inject_version():
        return dict(app_version="v1.0")

    # 🔧 Perform app-specific setup inside app context
    with app.app_context():
        from app.db import init_db, load_settings, ensure_default_settings, ensure_admin_user, ensure_default_queue
        init_db()
        ensure_default_settings()
        default_queue_id = ensure_default_queue() # Ensure default queue and get its ID
        if default_queue_id is None:
            app.logger.critical("Could not ensure default queue. Ticket creation without a queue might fail if DB requires it.")
            # Decide if app should halt or continue with a warning. For now, continue.
        app.config['DEFAULT_QUEUE_ID'] = default_queue_id # Store it in app config

        settings = load_settings()
        ensure_admin_user()

        if settings.get("enable_api") == "1":
            import app.api
            app.logger.info("API enabled and loaded.")


    app.logger.info(f"Application '{app.name}' created successfully. Debug mode: {app.debug}")
    return app
