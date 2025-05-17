# db.py
import os
from flask import current_app
import sqlite3
from contextlib import contextmanager
from werkzeug.security import generate_password_hash
from app.settings_loader import DEFAULT_SETTINGS
import logging

@contextmanager
def get_db():
    # Using current_app.logger here might be tricky if get_db is called outside app context
    # For now, let's assume it's mostly called within context or during app setup where logger is available.
    # A more robust solution might involve passing a logger or checking current_app.
    logger = current_app.logger if current_app else logging.getLogger(__name__) # Fallback if no app context
    
    db_path = get_db_path()
    conn = None # Initialize conn to None
    try:
        # logger.debug(f"Attempting to connect to database: {db_path}") # Can be too verbose
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON") # Ensure FKs are enabled for every connection
        # logger.debug(f"Database connection established and foreign keys enabled for: {db_path}")
        yield conn
        conn.commit()
        # logger.debug(f"Database transaction committed for: {db_path}")
    except Exception as e:
        if conn: # Check if conn was successfully assigned
            logger.error(f"Database transaction rolled back due to error: {e}", exc_info=True)
            conn.rollback()
        else:
            logger.error(f"Failed to establish database connection or error before connection: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()
            # logger.debug(f"Database connection closed for: {db_path}")

def get_db_path():
    return current_app.config['DATABASE']

def load_settings():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.debug("Loading settings from database.")
    try:
        with get_db() as conn:
            settings_data = {
                row['key']: row['value']
                for row in conn.execute('SELECT key, value FROM settings').fetchall()
            }
        logger.debug(f"Loaded {len(settings_data)} settings from database.")
        return settings_data
    except Exception as e:
        logger.error(f"Failed to load settings from database: {e}", exc_info=True)
        return {} # Return empty dict on failure to prevent crashes, or re-raise

def init_db():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Initializing database schema...")
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Table creation logs can be verbose, so maybe one message before and after
            logger.debug("Creating/verifying table: queues")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                )
            """)
            
            # Add created_by to tickets table
            logger.debug("Creating/verifying table: tickets")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'in progress', 'closed')),
                    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high')),
                    deadline TEXT,
                    created_at TEXT NOT NULL,
                    created_by INTEGER,
                    queue_id INTEGER NOT NULL,
                    assigned_to INTEGER,
                    FOREIGN KEY (queue_id) REFERENCES queues(id) ON DELETE CASCADE,
                    FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL,
                    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
                )
            """)

            logger.debug("Creating/verifying table: users")
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

            logger.debug("Creating/verifying table: comments")
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
            
            # Add user_id to attachments table
            logger.debug("Creating/verifying table: attachments")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    user_id INTEGER,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
            """)

            logger.debug("Creating/verifying table: settings")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # Add Indexes for performance
            logger.debug("Creating/verifying indexes...")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_queue_id ON tickets (queue_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_assigned_to ON tickets (assigned_to)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_created_by ON tickets (created_by)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets (priority)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_ticket_id ON comments (ticket_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments (user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attachments_ticket_id ON attachments (ticket_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_attachments_user_id ON attachments (user_id)")
            logger.debug("Indexes created/verified.")

            conn.commit() # Commit after all table creations and index creations
        logger.info("Database schema initialization complete.")
    except Exception as e:
        logger.critical(f"CRITICAL: Database schema initialization failed: {e}", exc_info=True)
        raise # Re-raise to halt app startup if DB init fails critically

def ensure_default_settings():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Ensuring default settings are present...")
    settings_added_count = 0
    try:
        with get_db() as conn:
            for key, info in DEFAULT_SETTINGS.items():
                exists = conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone()
                if not exists:
                    default_value = info.get('default', '') # Ensure there's a default for default
                    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, default_value))
                    logger.info(f"Inserted default setting: {key} = '{default_value}'")
                    settings_added_count += 1
            conn.commit() # Commit after all potential inserts
        if settings_added_count > 0:
            logger.info(f"Finished ensuring default settings. Added {settings_added_count} new settings.")
        else:
            logger.info("Finished ensuring default settings. All defaults were already present.")
    except Exception as e:
        logger.error(f"Error ensuring default settings: {e}", exc_info=True)


def ensure_admin_user():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Ensuring admin user exists...")
    try:
        current_settings = load_settings()
        username = current_settings.get('admin_username', 'admin')
        password = current_settings.get('admin_password', 'changeme')

        with get_db() as conn:
            cur = conn.cursor()
            existing = cur.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            
            if existing:
                logger.info(f"Admin user '{username}' (ID: {existing['id']}) already exists (found by initial SELECT).")
                return

            # If the initial SELECT didn't find the user, attempt to create.
            logger.info(f"Admin user '{username}' not found by initial SELECT. Attempting to create...")
            
            hashed_password = generate_password_hash(password)
            try:
                cur.execute(
                    "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
                    (username, hashed_password)
                )
                new_admin_id = cur.lastrowid
                # conn.commit() is handled by the get_db context manager if no exception occurs here
                logger.info(f"Admin user '{username}' (ID: {new_admin_id}) created successfully by INSERT.")
                if password == 'changeme':
                    logger.warning(f"Admin user '{username}' (ID: {new_admin_id}) was created with the default password 'changeme'. THIS MUST BE CHANGED IMMEDIATELY.")
            
            except sqlite3.IntegrityError as ie:
                # This block is reached if the INSERT fails due to a constraint (e.g., UNIQUE on username).
                # This implies the user *does* exist, but the initial SELECT failed to find them.
                logger.warning(
                    f"INSERT attempt for admin user '{username}' failed with IntegrityError: {ie}. "
                    f"This suggests the user already exists, but the initial SELECT query did not find them. "
                    f"Proceeding under the assumption that the admin user exists."
                )
                # We don't re-raise the IntegrityError here, so the application startup won't crash.
                # The transaction managed by get_db() will be rolled back if this IntegrityError was the only thing
                # that would have caused it to fail, or it will commit other changes if any were made before this point
                # in this specific transaction (though ensure_admin_user doesn't make other changes before this).
                # Effectively, the failed INSERT is ignored, and we assume the user is already there.
            
            # No explicit conn.commit() here; it's handled by the get_db() context manager's __exit__ method.
            # If an IntegrityError was caught and handled above, the get_db() will still try to commit
            # the transaction, which would be a no-op if only the failed INSERT was attempted.

    except Exception as e:
        # Catch any other unexpected errors during the process
        logger.error(f"An unexpected error occurred while ensuring admin user: {e}", exc_info=True)

