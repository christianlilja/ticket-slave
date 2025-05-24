"""
Main Flask application setup and initialization.

This module configures the Flask application instance, including:
- Secret key management
- Upload folder configuration
- Blueprint registration
- Database initialization (when run directly)
- Context processors (e.g., for app version)
- Production error logging
"""
from flask import Flask
import os
from app.error import register_error_handlers
# DEFAULT_SETTINGS is used in app.db, not directly here anymore for these functions
# from app.settings_loader import DEFAULT_SETTINGS
from app.db import init_db, load_settings, ensure_default_settings, ensure_admin_user, ensure_default_queue
# It's good practice to also initialize the db_manager if it's meant to be a global singleton used by app.db
# However, app.db already instantiates it. If we need to pass `app` to it, that's a different pattern.
# from app.database_manager import DatabaseManager # db_manager is already instantiated in app.db

# --- Blueprints ---
# Import blueprint instances from their respective route modules.
# Blueprints help in organizing routes and views into modular components.
from routes.main import main_bp
from routes.auth import auth_bp
from routes.tickets import tickets_bp
from routes.users import users_bp
from routes.settings_routes import settings_bp
from routes.notifications_routes import notifications_bp
from routes.queues import queues_bp
from routes.profile import profile_bp

# --- Application Setup ---
app = Flask(__name__) # Create the Flask application instance.
register_error_handlers(app) # Register custom error handlers (e.g., for 404, 500).

# Determine if the application is running in a production environment
# based on the FLASK_ENV environment variable.
IS_PROD = os.environ.get('FLASK_ENV') == 'production'

# --- Secret Key Configuration ---
# The secret key is crucial for session management, CSRF protection, and other security features.
# It MUST be set to a strong, unique, and random value in production environments.
if IS_PROD and not os.environ.get('SECRET_KEY'):
    # Fail fast if SECRET_KEY is not set in production.
    raise RuntimeError("FATAL: SECRET_KEY environment variable must be set in production.")

# Use the SECRET_KEY from environment variables.
# Fallback to a default development key (INSECURE for production).
app.secret_key = os.environ.get('SECRET_KEY', 'unsafe-dev-secret-key-change-me')

if app.secret_key == 'unsafe-dev-secret-key-change-me':
    # Log a prominent warning if the default development key is used.
    app.logger.warning(
        "SECURITY WARNING: Running with a default development secret key. "
        "This is INSECURE and NOT recommended for production environments. "
        "Set the SECRET_KEY environment variable to a strong, unique value."
    )

# --- Upload Settings ---
# Configure the folder for file uploads and the maximum allowed content length.
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads') # Define the path to the 'uploads' directory.
os.makedirs(UPLOAD_FOLDER, exist_ok=True) # Ensure the upload directory exists; create if not.
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER # Store the upload folder path in Flask app config.
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # Set max upload size to 10MB.

# --- Blueprint Registration ---
# Register all imported blueprints with the Flask application.
# The order of registration can matter if blueprints have overlapping URL prefixes
# or specific dependencies between them.
app.register_blueprint(auth_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(users_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(queues_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(main_bp) # Main blueprint, often registered last or with a specific root prefix.

# --- Application Version ---
# Define the application version. This can be useful for display in templates or for API versioning.
APP_VERSION = "v1.0.0" # Current application version.

@app.context_processor
def inject_version():
    """
    Injects the application version into template contexts.
    This makes `app_version` available in all Jinja2 templates.
    """
    return dict(app_version=APP_VERSION)

# --- Direct Execution Block (Development/Initialization) ---
if __name__ == '__main__':
    # This block executes only when the script is run directly (e.g., `python app/app.py`),
    # not when imported by a WSGI server like Gunicorn in production.
    # It's typically used for starting the Flask development server and performing initial setup tasks.
    app.logger.info("Application starting in direct execution mode (development or initial setup).")

    # Operations requiring application context (e.g., database interactions).
    with app.app_context():
        app.logger.info("Initializing database and ensuring default data...")
        init_db()                 # Initialize database schema if it doesn't exist.
        ensure_default_settings() # Populate database with essential default settings if missing.
        settings = load_settings()  # Load application settings from the database.
        ensure_admin_user()       # Create a default admin user if one doesn't exist.
        ensure_default_queue()    # Create a default ticket queue if one doesn't exist.

        # Conditionally import and initialize API module if enabled in settings.
        if settings.get('enable_api') == '1':
            app.logger.info("API is enabled in settings. Initializing API module.")
            import app.api as api  # Import the API module.
            # If the API module has an init_app function, call it here:
            # if hasattr(api, 'init_app'):
            #     api.init_app(app)
        else:
            app.logger.info("API is disabled in settings.")

    # Start the Flask development server.
    # `debug=True` enables the Werkzeug debugger and auto-reloader.
    # This is NOT suitable for production environments.
    app.logger.info(f"Starting Flask development server on http://0.0.0.0:5000/ with debug={app.debug}")
    app.run(host="0.0.0.0", port=5000, debug=not IS_PROD) # debug should be False if IS_PROD

# --- Production Error Logging ---
# Configure file-based error logging when not in debug mode (typically for production).
if not app.debug: # Check app.debug, which is often set by FLASK_DEBUG or by app.run(debug=...)
    import logging
    from logging.handlers import RotatingFileHandler

    app.logger.info("Configuring file-based error logging for production.")

    # RotatingFileHandler ensures log files don't grow indefinitely.
    # Creates up to 5 backup log files (backupCount), each up to 10KB (maxBytes).
    file_handler = RotatingFileHandler('error.log', maxBytes=10240, backupCount=5)
    file_handler.setLevel(logging.ERROR) # Log only ERROR and CRITICAL level messages to this handler.

    # Define a detailed log format for better diagnostics in log files.
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    )
    file_handler.setFormatter(formatter)

    # Add the configured file handler to the Flask application's logger.
    # If you want to replace default handlers (e.g., stderr for Werkzeug),
    # you might consider clearing existing handlers first: app.logger.handlers.clear()
    app.logger.addHandler(file_handler)
    app.logger.info("File-based error logging configured to 'error.log'.")
elif app.debug:
    app.logger.info("Debug mode is ON. Using Werkzeug interactive debugger. File-based error logging is not enabled.")
