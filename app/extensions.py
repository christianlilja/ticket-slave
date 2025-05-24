"""
Flask extension instantiations.

This module is the conventional place to instantiate Flask extensions.
Instantiating extensions here (without initializing them with the app instance yet)
helps to avoid circular import problems that can arise when extensions need access
to the app object, and the app object (in app/__init__.py) needs to import
blueprints or other modules that might, in turn, depend on these extensions.

The extensions are typically initialized with the Flask app instance (using their
`init_app(app)` method) within the application factory (`create_app` function
in `app/__init__.py`).
"""
from flask_jwt_extended import JWTManager

# Instantiate Flask-JWT-Extended.
# This `jwt` object will be configured and registered with the Flask app
# in the application factory (e.g., in `app/api.py` via `init_jwt(app)`
# which calls `jwt.init_app(app)`).
jwt = JWTManager()

# Example of how other extensions would be added:
# from flask_sqlalchemy import SQLAlchemy
# from flask_marshmallow import Marshmallow
# from flask_migrate import Migrate
#
# db = SQLAlchemy()
# ma = Marshmallow()
# migrate = Migrate()
#
# Then, in app/__init__.py (within create_app):
# from .extensions import db, ma, migrate, jwt
#
# db.init_app(app)
# ma.init_app(app)
# migrate.init_app(app, db)
# # jwt.init_app(app) # (This is currently handled in app/api.py's init_jwt)
