from flask import Flask
import os
from app.error import register_error_handlers
from app.settings_loader import DEFAULT_SETTINGS
from app.db import init_db, load_settings, ensure_default_settings, ensure_admin_user

# Blueprints
from routes.main import main_bp
from routes.auth import auth_bp
from routes.tickets import tickets_bp
from routes.users import users_bp
from routes.settings_routes import settings_bp
from routes.notifications_routes import notifications_bp
from routes.queues import queues_bp
from routes.profile import profile_bp

# App setup
app = Flask(__name__)
register_error_handlers(app)

IS_PROD = os.environ.get('FLASK_ENV') == 'production'

if IS_PROD and not os.environ.get('SECRET_KEY'):
    raise RuntimeError("SECRET_KEY must be set in production")

app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

if app.secret_key == 'dev-secret-key':
    app.logger.warning("Running with default secret key. Not recommended for production.")

# Upload settings
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(tickets_bp)
app.register_blueprint(users_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(queues_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(main_bp)

# Version
APP_VERSION = "v1.0"

@app.context_processor
def inject_version():
    return dict(app_version=APP_VERSION)

# Start app
if __name__ == '__main__':
    init_db()
    ensure_default_settings()
    settings = load_settings()
    ensure_admin_user()
    if settings.get('enable_api') == '1':
        import app.api as api  # Ensure api doesn't execute code on import unless necessary
    app.run(host="0.0.0.0", port=5000, debug=True)

# Error logging
if not app.debug:
    import logging
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler('error.log', maxBytes=10240, backupCount=5)
    file_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
