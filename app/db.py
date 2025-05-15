# db.py
import os
from flask import current_app
import sqlite3
from contextlib import contextmanager
from werkzeug.security import generate_password_hash
from app.settings_loader import DEFAULT_SETTINGS

@contextmanager
def get_db():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_db_path():
    return current_app.config['DATABASE']

def load_settings():
    with get_db() as conn:
        return {
            row['key']: row['value']
            for row in conn.execute('SELECT key, value FROM settings').fetchall()
        }

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()

        # Enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys = ON")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'in progress', 'closed')),
                priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high')),
                deadline TEXT,
                created_at TEXT NOT NULL,
                queue_id INTEGER NOT NULL,
                assigned_to INTEGER,
                FOREIGN KEY (queue_id) REFERENCES queues(id) ON DELETE CASCADE,
                FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                email TEXT,
                apprise_url TEXT,
                pushover_user_key TEXT,
                pushover_api_token TEXT,
                is_admin INTEGER DEFAULT 0,
                notify_email INTEGER DEFAULT 0,
                notify_pushover INTEGER DEFAULT 0,
                notify_apprise INTEGER DEFAULT 0,
                theme TEXT DEFAULT 'dark'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                user_id INTEGER,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        conn.commit()

def ensure_default_settings():
    with get_db() as conn:
        for key, info in DEFAULT_SETTINGS.items():
            exists = conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone()
            if not exists:
                conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, info['default']))
        conn.commit()




def ensure_admin_user():
    settings = load_settings()
    username = settings.get('admin_username', 'admin')
    password = settings.get('admin_password', 'changeme')

    with get_db() as conn:
        cur = conn.cursor()
        existing = cur.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return  # User already exists

        hashed_password = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
            (username, hashed_password)
        )
        conn.commit()
