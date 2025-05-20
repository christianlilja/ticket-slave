# app/database_manager.py
import sqlite3
from flask import current_app
import logging
from contextlib import contextmanager

# Assuming get_db_path is defined in app.db or can be moved/replicated here
# For now, let's try to import it or define a similar utility
try:
    from .db import get_db_path
except ImportError:
    # Fallback or simplified version if direct import fails
    # This might happen if this module is used in a context where app.db is not yet fully set up
    # Or if we decide to make database_manager more independent.
    def get_db_path():
        if current_app:
            return current_app.config['DATABASE']
        # This fallback is problematic if no app context is available.
        # Consider how this module will be initialized and used.
        raise RuntimeError("Database path not configured and no app context.")

@contextmanager
def get_database_connection():
    """
    Provides a database connection using the application's configured database path.
    This is a simplified version of the get_db context manager from db.py,
    focused on connection management for the DatabaseManager.
    """
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        logger.debug(f"DBManager: Connection established to {db_path}")
        yield conn
        conn.commit()
        logger.debug(f"DBManager: Transaction committed for {db_path}")
    except Exception as e:
        if conn:
            logger.error(f"DBManager: Transaction rolled back for {db_path} due to: {e}", exc_info=True)
            conn.rollback()
        else:
            logger.error(f"DBManager: Failed to connect to {db_path}: {e}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()
            logger.debug(f"DBManager: Connection closed for {db_path}")


class DatabaseManager:
    """
    A class to manage database operations, abstracting direct SQLite calls.
    """
    def __init__(self):
        # The logger can be initialized here if preferred, or used from current_app
        self.logger = current_app.logger if current_app else logging.getLogger(__name__)

    def execute_query(self, query, params=None, commit=False):
        """
        Executes a given SQL query.

        :param query: The SQL query string.
        :param params: A tuple of parameters to substitute into the query.
        :param commit: Whether to commit the transaction immediately after this query.
                       Note: get_database_connection handles commit on successful exit.
                       This parameter might be redundant if all operations are single queries
                       within their own connection context, or if batch operations are handled differently.
        :return: The cursor object after execution.
        """
        params = params or ()
        self.logger.debug(f"Executing query: {query} with params: {params}")
        with get_database_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                # Commit is handled by the context manager on successful block exit.
                # If an explicit commit is needed *before* the block ends, it's unusual
                # for this setup. For DML returning lastrowid, it's fine.
                self.logger.debug(f"Query executed successfully: {query}")
                return cursor
            except sqlite3.Error as e:
                self.logger.error(f"Database error during query execution: {query} - {e}", exc_info=True)
                raise # Re-raise the exception to be handled by the caller or context manager

    def fetchone(self, query, params=None):
        """
        Executes a query and fetches one row.

        :param query: The SQL query string.
        :param params: A tuple of parameters.
        :return: A single row as a dictionary (or sqlite3.Row object), or None.
        """
        cursor = self.execute_query(query, params)
        return cursor.fetchone()

    def fetchall(self, query, params=None):
        """
        Executes a query and fetches all rows.

        :param query: The SQL query string.
        :param params: A tuple of parameters.
        :return: A list of rows (dictionaries or sqlite3.Row objects).
        """
        cursor = self.execute_query(query, params)
        return cursor.fetchall()

    def insert(self, query, params=None):
        """
        Executes an INSERT query and returns the last inserted row ID.

        :param query: The SQL INSERT query string.
        :param params: A tuple of parameters.
        :return: The ID of the last inserted row.
        """
        cursor = self.execute_query(query, params)
        return cursor.lastrowid

    def update(self, query, params=None):
        """
        Executes an UPDATE query and returns the number of rows affected.

        :param query: The SQL UPDATE query string.
        :param params: A tuple of parameters.
        :return: The number of rows affected.
        """
        cursor = self.execute_query(query, params)
        return cursor.rowcount

    def delete(self, query, params=None):
        """
        Executes a DELETE query and returns the number of rows affected.

        :param query: The SQL DELETE query string.
        :param params: A tuple of parameters.
        :return: The number of rows affected.
        """
        cursor = self.execute_query(query, params)
        return cursor.rowcount

# Example of how it might be initialized and used in the app (e.g., in app/__init__.py or app/app.py)
# db_manager = None
# def init_db_manager(app):
#     global db_manager
#     db_manager = DatabaseManager()