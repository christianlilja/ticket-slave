# routes/__init__.py

from routes.main import main_bp
from routes.auth import auth_bp
from routes.tickets import tickets_bp
from routes.users import users_bp
from routes.settings_routes import settings_bp
from routes.notifications_routes import notifications_bp
from routes.queues import queues_bp
from routes.profile import profile_bp

blueprints = [
    main_bp,
    auth_bp,
    tickets_bp,
    users_bp,
    settings_bp,
    notifications_bp,
    queues_bp,
    profile_bp
]
