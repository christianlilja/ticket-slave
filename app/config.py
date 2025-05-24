"""
Application configuration settings.

This module defines a base configuration class (`Config`) for the Flask application.
It includes settings for secret keys, file uploads, JWT authentication, and
session cookie security.

It's common practice to have different configuration classes for various
environments (e.g., DevelopmentConfig, ProductionConfig, TestingConfig) that
inherit from this base Config class and override specific settings as needed.
The application factory (`create_app` in app/__init__.py) would then load the
appropriate configuration based on an environment variable (e.g., FLASK_ENV).

For this example, only a single base `Config` class is provided.
"""
import os
from datetime import timedelta # For JWT_ACCESS_TOKEN_EXPIRES

class Config:
    """
    Base configuration class for the Flask application.
    Settings defined here can be accessed via `current_app.config`.
    """

    # --- Security Settings ---
    # SECRET_KEY: A secret key for signing session cookies, CSRF tokens, etc.
    # CRITICAL: This MUST be a strong, unique, and random string in production.
    # It should be loaded from an environment variable and NOT hardcoded.
    SECRET_KEY = os.getenv('SECRET_KEY', 'a-very-unsafe-default-dev-secret-key-CHANGE-ME')
    # The fallback 'dev-secret-key' is highly insecure and only for development convenience.
    # A warning should be logged in app/__init__.py if this default is used.

    # JWT_SECRET_KEY: Secret key specifically for signing JSON Web Tokens (JWTs).
    # CRITICAL: Similar to SECRET_KEY, this must be strong, unique, and kept secret.
    JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY', 'another-unsafe-default-jwt-secret-key-CHANGE-ME')
    # The fallback is insecure and only for development.

    # --- File Upload Settings ---
    # UPLOAD_FOLDER: The directory where uploaded files will be stored.
    # Note: The path `os.path.join(os.getcwd(), 'uploads')` might not be ideal if the
    # application's working directory changes or if deployed in complex environments.
    # It's often better to define this relative to the application root or use an
    # absolute path configured via an environment variable or derived from `data_dir`
    # as done in `app/__init__.py`. This setting here might be overridden by `app/__init__.py`.
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'uploads_from_config')
    # ^ Example of a path relative to the project root, assuming 'config.py' is in 'app/'.
    # However, `app.config["UPLOAD_FOLDER"] = os.path.join(data_dir, "uploads")` in `app/__init__.py`
    # will likely take precedence if `app.config.from_object(Config)` is called before that line.

    # MAX_CONTENT_LENGTH: Maximum allowed size for uploaded files (in bytes).
    # 10 * 1024 * 1024 = 10 MB.
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # ALLOWED_EXTENSIONS: A set of file extensions permitted for uploads.
    # This is used by the `utils.files.allowed_file()` function.
    # Note: `utils.files.py` also defines an `ALLOWED_EXTENSIONS`. Ensure consistency
    # or decide on a single source of truth for this setting (e.g., load from app.config).
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'xlsx', 'pptx', 'txt', 'log', 'csv', 'zip', 'rar'}


    # --- JWT Configuration ---
    # JWT_ACCESS_TOKEN_EXPIRES: Duration for which an access token is valid.
    # Can be an integer (seconds) or a `timedelta` object.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv('JWT_TOKEN_EXPIRE_HOURS', '1'))) # e.g., 1 hour


    # --- Session Cookie Security Settings ---
    # These settings enhance the security of session cookies.

    # SESSION_COOKIE_SECURE: If True, the session cookie will only be sent over HTTPS.
    # CRITICAL for production: Set to True if your application is served over HTTPS.
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() == 'true' # Default to True for production readiness

    # SESSION_COOKIE_HTTPONLY: If True, the session cookie cannot be accessed by client-side JavaScript.
    # Helps mitigate Cross-Site Scripting (XSS) attacks. Highly recommended to be True.
    SESSION_COOKIE_HTTPONLY = True

    # SESSION_COOKIE_SAMESITE: Controls when cookies are sent with cross-site requests.
    # 'Lax' (default in modern Flask/browsers) provides a good balance of security and usability.
    # 'Strict' offers more protection but can break some cross-site linking functionalities.
    # 'None' (requires Secure=True) is for cookies sent in all cross-site contexts, often for APIs.
    SESSION_COOKIE_SAMESITE = 'Lax'

    # --- Database Configuration (Example, often more complex) ---
    # SQLALCHEMY_DATABASE_URI: Example if using SQLAlchemy.
    # For the current project using SQLite directly, the DB path is set in app/__init__.py.
    # SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///your_default_database.db')
    # SQLALCHEMY_TRACK_MODIFICATIONS = False # Recommended to disable to save resources.

# Example of environment-specific configurations:
# class DevelopmentConfig(Config):
#     DEBUG = True
#     SESSION_COOKIE_SECURE = False # Allow HTTP for local development.
#
# class ProductionConfig(Config):
#     DEBUG = False
#     # SECRET_KEY, JWT_SECRET_KEY, DATABASE_URL MUST be set via environment variables.
#
# class TestingConfig(Config):
#     TESTING = True
#     SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use in-memory DB for tests.
#     WTF_CSRF_ENABLED = False # Often disabled for easier testing of forms.

# The application factory (`create_app`) would then use something like:
# config_name = os.getenv('FLASK_CONFIG', 'development') # or 'production'
# if config_name == 'production':
#     app.config.from_object(ProductionConfig)
# else:
#     app.config.from_object(DevelopmentConfig)
# Or simply: app.config.from_object(Config) if only one class is used.
