# db.py
import os
from flask import current_app
import sqlite3 # Keep for IntegrityError
from werkzeug.security import generate_password_hash
from app.settings_loader import DEFAULT_SETTINGS
import logging
from app.database_manager import DatabaseManager

# Global instance of DatabaseManager
# This will be initialized when the module is loaded, assuming app context might not be
# immediately available for its constructor if it relied on current_app for logger.
# The DatabaseManager's constructor has a fallback for logger.
db_manager = DatabaseManager()

# The get_db_path function is still needed by DatabaseManager if it's defined here
# and not self-contained or passed to DatabaseManager.
# Assuming database_manager.py's get_db_path import will work or its fallback is used.
def get_db_path():
    # This function is also used by database_manager.py through an attempted import.
    # Ensure it's available and works as expected.
    if not current_app:
        # This case should ideally be handled if db_manager is used before app is fully configured.
        # For now, assume current_app will be available when this is called.
        raise RuntimeError("Application context not available for get_db_path.")
    return current_app.config['DATABASE']


def load_settings():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.debug("Loading settings from database via DatabaseManager.")
    try:
        rows = db_manager.fetchall('SELECT key, value FROM settings')
        settings_data = {row['key']: row['value'] for row in rows}
        logger.debug(f"Loaded {len(settings_data)} settings from database.")
        return settings_data
    except Exception as e:
        logger.error(f"Failed to load settings from database: {e}", exc_info=True)
        return {}

def init_db():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Initializing database schema via DatabaseManager...")
    try:
        # Using execute_query for DDL statements.
        # The DatabaseManager's get_database_connection handles transactions.
        # No explicit commit needed here per query, as the context manager handles it.

        logger.debug("Creating/verifying table: queues")
        db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        
        logger.debug("Creating/verifying table: tickets")
        db_manager.execute_query("""
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
        db_manager.execute_query("""
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
        db_manager.execute_query("""
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
        
        logger.debug("Creating/verifying table: attachments")
        db_manager.execute_query("""
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
        db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        logger.debug("Creating/verifying indexes...")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_queue_id ON tickets (queue_id)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_assigned_to ON tickets (assigned_to)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_created_by ON tickets (created_by)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets (priority)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_comments_ticket_id ON comments (ticket_id)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments (user_id)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_attachments_ticket_id ON attachments (ticket_id)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_attachments_user_id ON attachments (user_id)")
        logger.debug("Indexes created/verified.")
        
        # Commits are handled by the context manager in execute_query's get_database_connection
        logger.info("Database schema initialization complete.")
    except Exception as e:
        logger.critical(f"CRITICAL: Database schema initialization failed: {e}", exc_info=True)
        raise

def ensure_default_settings():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Ensuring default settings are present...")
    settings_added_count = 0
    try:
        for key, info in DEFAULT_SETTINGS.items():
            exists = db_manager.fetchone("SELECT 1 FROM settings WHERE key = ?", (key,))
            if not exists:
                default_value = info.get('default', '')
                try:
                    db_manager.insert("INSERT INTO settings (key, value) VALUES (?, ?)", (key, default_value))
                    logger.info(f"Inserted default setting: {key} = '{default_value}'")
                    settings_added_count += 1
                except sqlite3.IntegrityError:
                    logger.warning(f"Default setting for key '{key}' already exists (caught by IntegrityError). Skipping.")
                except Exception as e_insert:
                    logger.error(f"Error inserting default setting for key '{key}': {e_insert}", exc_info=True)
                    # Decide if this is critical enough to re-raise or if we can continue
        
        if settings_added_count > 0:
            logger.info(f"Finished ensuring default settings. Added {settings_added_count} new settings.")
        else:
            logger.info("Finished ensuring default settings. All defaults were already present or skipped due to existing.")
    except Exception as e: # Catch errors from db_manager.fetchone or other unexpected issues
        logger.error(f"Error ensuring default settings (outer try-except): {e}", exc_info=True)


def ensure_admin_user():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Ensuring admin user exists...")
    try:
        current_settings = load_settings() # Uses db_manager
        username = current_settings.get('admin_username', 'admin')
        password = current_settings.get('admin_password', 'changeme')

        existing = db_manager.fetchone("SELECT id FROM users WHERE username = ?", (username,))
        
        if existing:
            logger.info(f"Admin user '{username}' (ID: {existing['id']}) already exists.")
            return

        logger.info(f"Admin user '{username}' not found. Attempting to create...")
        hashed_password = generate_password_hash(password)
        try:
            new_admin_id = db_manager.insert(
                "INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
                (username, hashed_password)
            )
            logger.info(f"Admin user '{username}' (ID: {new_admin_id}) created successfully.")
            if password == 'changeme':
                logger.warning(f"Admin user '{username}' (ID: {new_admin_id}) was created with the default password 'changeme'. THIS MUST BE CHANGED IMMEDIATELY.")
        
        except sqlite3.IntegrityError as ie:
            logger.warning(
                f"INSERT attempt for admin user '{username}' failed with IntegrityError: {ie}. "
                f"This suggests the user already exists."
            )
            # Assuming user exists, proceed without error.
            # The transaction in db_manager.insert would have been rolled back.

    except Exception as e:
        logger.error(f"An unexpected error occurred while ensuring admin user: {e}", exc_info=True)

def ensure_default_queue():
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    default_queue_name = "Unassigned"
    logger.info(f"Ensuring default queue '{default_queue_name}' exists...")
    try:
        existing_queue = db_manager.fetchone("SELECT id FROM queues WHERE name = ?", (default_queue_name,))

        if existing_queue:
            logger.info(f"Default queue '{default_queue_name}' (ID: {existing_queue['id']}) already exists.")
            return existing_queue['id']
        else:
            logger.info(f"Default queue '{default_queue_name}' not found. Attempting to create...")
            try:
                new_queue_id = db_manager.insert("INSERT INTO queues (name) VALUES (?)", (default_queue_name,))
                logger.info(f"Default queue '{default_queue_name}' (ID: {new_queue_id}) created successfully.")
                return new_queue_id
            except sqlite3.IntegrityError:
                # This case means it was created between the fetchone check and the insert attempt (race condition)
                # or the initial fetchone failed to see it for some reason. Re-fetch to be sure.
                logger.warning(f"IntegrityError when inserting default queue '{default_queue_name}'. It likely already exists. Re-fetching.")
                refetched_queue = db_manager.fetchone("SELECT id FROM queues WHERE name = ?", (default_queue_name,))
                if refetched_queue:
                    logger.info(f"Default queue '{default_queue_name}' (ID: {refetched_queue['id']}) confirmed to exist after IntegrityError.")
                    return refetched_queue['id']
                else:
                    # This is a more problematic state - insert failed, and it's still not there.
                    logger.error(f"CRITICAL: Default queue '{default_queue_name}' insert failed with IntegrityError, but queue still not found on re-fetch.")
                    return None # Indicate failure
            except Exception as e_insert:
                logger.error(f"Error inserting default queue '{default_queue_name}': {e_insert}", exc_info=True)
                return None


    except Exception as e: # Catch errors from the initial db_manager.fetchone
        logger.error(f"Error ensuring default queue '{default_queue_name}' (outer try-except): {e}", exc_info=True)
        return None

