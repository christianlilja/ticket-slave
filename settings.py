# settings.py

import sqlite3
from contextlib import contextmanager
from werkzeug.security import generate_password_hash

DB_PATH = 'database.db'

DEFAULT_SETTINGS = {
    'allow_registration': {
        'default': '0',
        'label': 'Allow new users to register',
        'type': 'checkbox'
    },
    'enable_api': {
        'default': '0',
        'label': 'Enable API',
        'type': 'checkbox'
    },
    'smtp_server': {
        'default': 'localhost',
        'label': 'SMTP Server',
        'type': 'text'
    },
    'smtp_port': {
        'default': '25',
        'label': 'SMTP Port',
        'type': 'number'
    },
    'smtp_from_email': {
        'default': 'noreply@example.com',
        'label': 'From Email Address',
        'type': 'text'
    },
    'smtp_username': {
        'default': '',
        'label': 'SMTP Username',
        'type': 'text'
    },
    'smtp_password': {
        'default': '',
        'label': 'SMTP Password',
        'type': 'password'
    },
    'smtp_use_tls': {
        'default': '0',
        'label': 'Use TLS for SMTP',
        'type': 'checkbox'
    },
    'admin_username': {
        'default': 'admin', 
        'label': 'Default admin username', 
        'type': 'text'
    },
    'admin_password': {
        'default': 'changeme', 
        'label': 'Default admin password', 
        'type': 'password'},

}

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def load_settings():
    with get_db() as conn:
        return {
            row['key']: row['value']
            for row in conn.execute('SELECT key, value FROM settings').fetchall()
        }

def ensure_default_settings():
    with get_db() as conn:
        for key, info in DEFAULT_SETTINGS.items():
            exists = conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone()
            if not exists:
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, info['default']))
        conn.commit()

def ensure_admin_user():
    from app import get_db, load_settings  # Avoid circular import issues by importing here
    settings = load_settings()
    username = settings.get('admin_username', 'admin')
    password = settings.get('admin_password', 'changeme')

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE is_admin = 1")
        if cur.fetchone():
            return  # Admin already exists

        hashed_password = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
            (username, hashed_password)
        )
        conn.commit()