"""
Database initialization, schema management, and utility functions.

This module is responsible for:
- Defining and initializing the database schema (tables, indexes).
- Providing functions to ensure default settings, admin user, and default queue exist.
- Loading application settings from the database.
- Interacting with the database via a global `DatabaseManager` instance.
"""
import os
from flask import current_app
import sqlite3 # Keep for sqlite3.IntegrityError, a specific exception type.
from werkzeug.security import generate_password_hash
from app.settings_loader import DEFAULT_SETTINGS # Predefined default application settings.
import logging
from app.database_manager import DatabaseManager

# --- Global DatabaseManager Instance ---
# A single instance of DatabaseManager is created when this module is loaded.
# This instance is used for all database operations throughout the application via this module.
# The DatabaseManager's constructor has a fallback for its logger if `current_app` is not yet available.
db_manager = DatabaseManager()

# --- Database Path ---
def get_db_path():
    """
    Retrieves the configured database file path from the Flask application context.

    This function is crucial for the DatabaseManager to know where the SQLite database file is located.
    It relies on `current_app.config['DATABASE']` being set.

    Raises:
        RuntimeError: If called outside of an active Flask application context.
    """
    # This function might also be used by database_manager.py if it attempts to import it directly,
    # though DatabaseManager now has its own internal way or requires it to be passed.
    if not current_app:
        # This situation should ideally be avoided by ensuring db_manager and its dependencies
        # are used only when the app context is available or by passing config explicitly.
        raise RuntimeError(
            "Application context not available for get_db_path. "
            "Ensure 'DATABASE' is configured in the Flask app."
        )
    return current_app.config['DATABASE']


# --- Settings Management ---
def load_settings():
    """
    Loads all application settings from the 'settings' table in the database.

    Returns:
        dict: A dictionary where keys are setting names and values are their corresponding values.
              Returns an empty dictionary if loading fails or no settings are found.
    """
    # Use current_app.logger if available, otherwise a default logger for this module.
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.debug("Attempting to load settings from database via DatabaseManager.")
    try:
        # Fetch all rows from the 'settings' table.
        rows = db_manager.fetchall('SELECT key, value FROM settings')
        # Convert list of rows (dictionaries) into a single settings dictionary.
        settings_data = {row['key']: row['value'] for row in rows}
        logger.debug(f"Successfully loaded {len(settings_data)} settings from the database.")
        return settings_data
    except Exception as e:
        logger.error(f"Failed to load settings from database: {e}", exc_info=True)
        return {} # Return empty dict on error to prevent crashes, allowing defaults to be used.

# --- Database Initialization and Schema ---
def init_db():
    """
    Initializes the database by creating all necessary tables and indexes if they don't already exist.

    This function defines the entire database schema. It's designed to be idempotent,
    meaning it can be run multiple times without causing errors or unintended changes
    if the schema already exists.
    Uses `db_manager.execute_query` which handles transactions implicitly.
    """
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Initializing database schema via DatabaseManager...")
    try:
        # The DatabaseManager's get_database_connection method uses a context manager
        # that handles commits for DDL statements automatically if successful, or rolls back on error.

        logger.debug("Creating/verifying table: queues (for ticket categorization)")
        db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique identifier for the queue
                name TEXT NOT NULL UNIQUE             -- Name of the queue (e.g., "Support", "Development")
            )
        """)

        logger.debug("Creating/verifying table: tickets (core ticket information)")
        db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,     -- Unique identifier for the ticket
                title TEXT NOT NULL,                      -- Brief summary/title of the ticket
                description TEXT,                         -- Detailed description of the issue/request
                status TEXT NOT NULL DEFAULT 'open'       -- Current status (e.g., 'open', 'in progress', 'closed')
                    CHECK(status IN ('open', 'in progress', 'closed')),
                priority TEXT NOT NULL DEFAULT 'medium'   -- Priority level (e.g., 'low', 'medium', 'high')
                    CHECK(priority IN ('low', 'medium', 'high')),
                deadline TEXT,                            -- Optional due date/time for the ticket (ISO format string)
                created_at TEXT NOT NULL,                 -- Timestamp of when the ticket was created (ISO format string)
                created_by INTEGER,                       -- User ID of the creator
                queue_id INTEGER NOT NULL,                -- ID of the queue this ticket belongs to
                assigned_to INTEGER,                      -- User ID of the person this ticket is assigned to
                FOREIGN KEY (queue_id) REFERENCES queues(id) ON DELETE CASCADE, -- If a queue is deleted, its tickets are also deleted
                FOREIGN KEY (assigned_to) REFERENCES users(id) ON DELETE SET NULL, -- If an assigned user is deleted, set assigned_to to NULL
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL   -- If the creating user is deleted, set created_by to NULL
            )
        """)

        logger.debug("Creating/verifying table: users (application users and their details)")
        db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique identifier for the user
                username TEXT NOT NULL UNIQUE,        -- Unique username for login
                password TEXT NOT NULL,               -- Hashed password
                email TEXT,                           -- User's email address (optional)
                apprise_url TEXT,                     -- Apprise notification service URL (optional)
                pushover_user_key TEXT,               -- Pushover user key for notifications (optional)
                pushover_api_token TEXT,              -- Pushover API token for notifications (optional)
                is_admin INTEGER DEFAULT 0,           -- Flag indicating if the user is an administrator (0=false, 1=true)
                notify_email INTEGER DEFAULT 0,       -- Flag for enabling email notifications (0=false, 1=true)
                notify_pushover INTEGER DEFAULT 0,    -- Flag for enabling Pushover notifications (0=false, 1=true)
                notify_apprise INTEGER DEFAULT 0,     -- Flag for enabling Apprise notifications (0=false, 1=true)
                theme TEXT DEFAULT 'dark'             -- User's preferred UI theme (e.g., 'light', 'dark')
            )
        """)

        logger.debug("Creating/verifying table: comments (for discussions on tickets)")
        db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique identifier for the comment
                ticket_id INTEGER NOT NULL,           -- ID of the ticket this comment belongs to
                user_id INTEGER,                      -- User ID of the commenter
                content TEXT NOT NULL,                -- The text content of the comment
                created_at TEXT NOT NULL,             -- Timestamp of when the comment was created (ISO format string)
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE, -- If a ticket is deleted, its comments are also deleted
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL     -- If the commenting user is deleted, set user_id to NULL
            )
        """)

        logger.debug("Creating/verifying table: attachments (for files attached to tickets)")
        db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, -- Unique identifier for the attachment
                ticket_id INTEGER NOT NULL,           -- ID of the ticket this attachment belongs to
                user_id INTEGER,                      -- User ID of the uploader
                original_filename TEXT NOT NULL,      -- The original name of the uploaded file
                stored_filename TEXT NOT NULL,        -- The (potentially sanitized) name of the file as stored on the server
                filepath TEXT NOT NULL,               -- Full path to the stored file on the server
                uploaded_at TEXT NOT NULL,            -- Timestamp of when the file was uploaded (ISO format string)
                FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE, -- If a ticket is deleted, its attachments are also deleted
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL     -- If the uploading user is deleted, set user_id to NULL
            )
        """)

        logger.debug("Creating/verifying table: settings (for application-wide configuration)")
        db_manager.execute_query("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, -- Unique key for the setting (e.g., 'site_name')
                value TEXT NOT NULL   -- Value of the setting
            )
        """)

        logger.debug("Creating/verifying indexes for performance optimization...")
        # Indexes on foreign keys and frequently queried columns can significantly improve query performance.
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_queue_id ON tickets (queue_id)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_assigned_to ON tickets (assigned_to)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_created_by ON tickets (created_by)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets (priority)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_comments_ticket_id ON comments (ticket_id)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments (user_id)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_attachments_ticket_id ON attachments (ticket_id)")
        db_manager.execute_query("CREATE INDEX IF NOT EXISTS idx_attachments_user_id ON attachments (user_id)")
        logger.debug("Database indexes created/verified successfully.")

        logger.info("Database schema initialization process complete.")
    except Exception as e:
        logger.critical(f"CRITICAL FAILURE: Database schema initialization failed: {e}", exc_info=True)
        raise # Re-raise the exception to halt application startup if schema init fails.

def ensure_default_settings():
    """
    Ensures that all default application settings (defined in `DEFAULT_SETTINGS`)
    are present in the 'settings' table. If a setting is missing, it's inserted
    with its default value.
    """
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Ensuring default application settings are present in the database...")
    settings_added_count = 0
    try:
        for key, info in DEFAULT_SETTINGS.items():
            # Check if the setting key already exists in the database.
            exists = db_manager.fetchone("SELECT 1 FROM settings WHERE key = ?", (key,))
            if not exists:
                default_value = info.get('default', '') # Get default value from DEFAULT_SETTINGS structure.
                try:
                    # Insert the missing setting with its default value.
                    db_manager.insert("INSERT INTO settings (key, value) VALUES (?, ?)", (key, default_value))
                    logger.info(f"Inserted default setting: '{key}' = '{default_value}'")
                    settings_added_count += 1
                except sqlite3.IntegrityError:
                    # This handles a rare race condition if another process inserted it meanwhile.
                    logger.warning(f"Default setting for key '{key}' already exists (caught by IntegrityError during insert). Skipping.")
                except Exception as e_insert:
                    logger.error(f"Error inserting default setting for key '{key}': {e_insert}", exc_info=True)
                    # Depending on severity, one might choose to re-raise here.
        
        if settings_added_count > 0:
            logger.info(f"Finished ensuring default settings. Added {settings_added_count} new settings.")
        else:
            logger.info("Finished ensuring default settings. All defaults were already present or skipped.")
    except Exception as e: # Catch errors from the initial db_manager.fetchone or other unexpected issues.
        logger.error(f"An error occurred during the ensure_default_settings process (outer try-except): {e}", exc_info=True)


def ensure_admin_user():
    """
    Ensures that a default administrator user exists in the 'users' table.
    If not, it creates one using credentials from application settings
    ('admin_username', 'admin_password') or falls back to 'admin'/'changeme'.
    """
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    logger.info("Ensuring default admin user exists...")
    try:
        current_settings = load_settings() # Load settings to get admin credentials.
        # Use configured admin username/password, or fallback to defaults.
        username = current_settings.get('admin_username', 'admin')
        password = current_settings.get('admin_password', 'changeme') # Default password, highly insecure.

        # Check if the admin user already exists.
        existing_admin = db_manager.fetchone("SELECT id FROM users WHERE username = ?", (username,))
        
        if existing_admin:
            logger.info(f"Admin user '{username}' (ID: {existing_admin['id']}) already exists. No action needed.")
            return

        # If admin user does not exist, create one.
        logger.info(f"Admin user '{username}' not found. Attempting to create...")
        hashed_password = generate_password_hash(password) # Always hash passwords before storing.
        try:
            new_admin_id = db_manager.insert(
                "INSERT INTO users (username, password, is_admin, email, theme) VALUES (?, ?, 1, ?, ?)", # is_admin set to 1
                (username, hashed_password, f"{username}@example.com", "dark") # Added default email and theme
            )
            logger.info(f"Admin user '{username}' (ID: {new_admin_id}) created successfully.")
            if password == 'changeme':
                # Log a critical warning if the default insecure password was used.
                logger.warning(
                    f"CRITICAL SECURITY WARNING: Admin user '{username}' (ID: {new_admin_id}) "
                    f"was created with the default password 'changeme'. "
                    f"THIS PASSWORD MUST BE CHANGED IMMEDIATELY through the application settings or user profile."
                )
        
        except sqlite3.IntegrityError as ie:
            # Handles race condition: if user was created between check and insert.
            logger.warning(
                f"INSERT attempt for admin user '{username}' failed with IntegrityError: {ie}. "
                f"This usually means the user was created concurrently. Assuming user now exists."
            )
            # The transaction in db_manager.insert would have been rolled back by DatabaseManager.

    except Exception as e:
        logger.error(f"An unexpected error occurred while ensuring admin user: {e}", exc_info=True)

def ensure_default_queue():
    """
    Ensures that a default ticket queue (named "Unassigned") exists in the 'queues' table.
    If not, it creates one.

    Returns:
        int or None: The ID of the default queue if it exists or was created successfully,
                     otherwise None if an error occurred.
    """
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    default_queue_name = "Unassigned"
    logger.info(f"Ensuring default ticket queue '{default_queue_name}' exists...")
    try:
        # Check if the default queue already exists.
        existing_queue = db_manager.fetchone("SELECT id FROM queues WHERE name = ?", (default_queue_name,))

        if existing_queue:
            logger.info(f"Default queue '{default_queue_name}' (ID: {existing_queue['id']}) already exists.")
            return existing_queue['id']
        else:
            # If default queue does not exist, create it.
            logger.info(f"Default queue '{default_queue_name}' not found. Attempting to create...")
            try:
                new_queue_id = db_manager.insert("INSERT INTO queues (name) VALUES (?)", (default_queue_name,))
                logger.info(f"Default queue '{default_queue_name}' (ID: {new_queue_id}) created successfully.")
                return new_queue_id
            except sqlite3.IntegrityError:
                # Handles race condition or if initial fetchone missed it.
                logger.warning(
                    f"IntegrityError when inserting default queue '{default_queue_name}'. "
                    f"It likely already exists or was created concurrently. Re-fetching to confirm."
                )
                refetched_queue = db_manager.fetchone("SELECT id FROM queues WHERE name = ?", (default_queue_name,))
                if refetched_queue:
                    logger.info(f"Default queue '{default_queue_name}' (ID: {refetched_queue['id']}) confirmed to exist after IntegrityError.")
                    return refetched_queue['id']
                else:
                    # This is an unexpected and problematic state.
                    logger.error(
                        f"CRITICAL: Default queue '{default_queue_name}' insert failed with IntegrityError, "
                        f"but the queue still not found on re-fetch. Manual intervention may be required."
                    )
                    return None # Indicate failure.
            except Exception as e_insert:
                logger.error(f"Error inserting default queue '{default_queue_name}': {e_insert}", exc_info=True)
                return None # Indicate failure.

    except Exception as e: # Catch errors from the initial db_manager.fetchone.
        logger.error(f"An error occurred during the ensure_default_queue process for '{default_queue_name}' (outer try-except): {e}", exc_info=True)
        return None # Indicate failure.
