import os
from flask import Flask
from app.error import register_error_handlers


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

    app.config["UPLOAD_FOLDER"] = os.path.join(data_dir, "uploads")
    app.config["DATABASE"] = os.path.join(app.instance_path, "database.db")

    # Optional: log if the DB doesn't exist yet
    if not os.path.exists(app.config["DATABASE"]):
        app.logger.info("Database file not found. It will be created.")


    register_error_handlers(app)

    # Secret key setup
    IS_PROD = os.environ.get("FLASK_ENV") == "production"
    if IS_PROD and not os.environ.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be set in production")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
    if app.secret_key == "dev-secret-key":
        app.logger.warning("Running with default secret key. Not recommended for production.")

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
        from app.db import init_db, load_settings, ensure_default_settings, ensure_admin_user
        init_db()
        ensure_default_settings()
        settings = load_settings()
        ensure_admin_user()

        if settings.get("enable_api") == "1":
            import app.api

    # Logging
    if not app.debug:
        import logging
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler("error.log", maxBytes=10240, backupCount=5)
        file_handler.setLevel(logging.ERROR)
        formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]")
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)

    return app
