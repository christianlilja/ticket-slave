"""
Low-level database interaction management.

This module provides a `DatabaseManager` class and a `get_database_connection`
context manager to handle SQLite database connections, query execution,
and transaction management. It aims to abstract direct SQLite operations
and provide a consistent interface for database access.
"""
import sqlite3
import os
from flask import current_app
import logging
from contextlib import contextmanager

def _get_db_path_for_manager():
    """
    Retrieves and validates the database path from the Flask app configuration.

    This internal helper function is used by `get_database_connection` to
    determine the location of the SQLite database file. It relies on
    `current_app.config['DATABASE']` being set.

    Returns:
        str: The path to the SQLite database file.

    Raises:
        RuntimeError: If the application context or 'DATABASE' config is not available or invalid.
    """
    # Ensure Flask application context and its config are accessible.
    if not hasattr(current_app, 'config'):
        # This error indicates a fundamental issue, likely that the function is called
        # too early in the app lifecycle or outside of a request/app context.
        raise RuntimeError("DBManager: Application context or config not available for _get_db_path_for_manager.")

    db_path_config = current_app.config.get('DATABASE')

    # Log the configured and resolved absolute path for debugging and clarity.
    if db_path_config:
        abs_db_path = os.path.abspath(db_path_config)
        current_app.logger.debug(f"DBManager: Original DATABASE config path: '{db_path_config}', Resolved absolute path: '{abs_db_path}'")
    else:
        current_app.logger.warning("DBManager: 'DATABASE' key in Flask app.config is None or empty.")

    # The database path must be configured.
    if not db_path_config:
        raise RuntimeError("DBManager: 'DATABASE' key not found, not configured, or empty in current_app.config.")
    return db_path_config


@contextmanager
def get_database_connection():
    """
    Provides and manages a database connection using a context manager.

    This function handles the lifecycle of a database connection:
    1. Establishes a connection to the SQLite database specified in Flask app config.
    2. Sets `conn.row_factory = sqlite3.Row` to allow dictionary-like access to columns.
    3. Enables foreign key constraints (`PRAGMA foreign_keys = ON`).
    4. Yields the connection for use within a `with` statement.
    5. Commits the transaction if no exceptions occur.
    6. Rolls back the transaction if any exception occurs.
    7. Ensures the connection is closed in all cases (success or failure).

    Yields:
        sqlite3.Connection: An active SQLite database connection object.

    Raises:
        RuntimeError: If connection fails, PRAGMA fails, or connection becomes unusable.
        sqlite3.Error: Re-raises SQLite-specific errors after attempting rollback.
        Exception: Re-raises other exceptions after attempting rollback.
    """
    logger = current_app.logger if current_app else logging.getLogger(__name__) # Fallback logger.

    # Debugging information about the application and config context.
    app_id = id(current_app) if current_app else "N/A"
    config_id = id(current_app.config) if hasattr(current_app, 'config') else "N/A"
    logger.debug(f"DBManager: get_database_connection called. current_app id: {app_id}, config id: {config_id}")

    db_path = _get_db_path_for_manager() # Get database path.
    logger.debug(f"DBManager: Resolved db_path for connection: '{db_path}'")

    conn = None # Initialize connection variable.
    try:
        logger.debug(f"DBManager: Attempting sqlite3.connect(db_path='{db_path}')")
        conn = sqlite3.connect(db_path, timeout=10) # Added timeout
        conn.row_factory = sqlite3.Row # Access columns by name.
        logger.debug(f"DBManager: Connection object created for '{db_path}'. Conn id: {id(conn)}")

        # Enable foreign key constraint enforcement for this connection.
        # This is crucial for data integrity.
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            logger.debug(f"DBManager: PRAGMA foreign_keys=ON executed for '{db_path}'")
        except sqlite3.Error as pragma_e:
            logger.error(f"DBManager: Error executing PRAGMA foreign_keys=ON for '{db_path}': {pragma_e}", exc_info=True)
            if conn: conn.close() # Close connection if PRAGMA fails.
            raise RuntimeError(f"Failed to set PRAGMA foreign_keys on db connection to '{db_path}': {pragma_e}") from pragma_e

        # Perform a quick test query to ensure the connection is usable after PRAGMA.
        try:
            test_cursor = conn.cursor()
            test_cursor.execute("SELECT 1")
            test_cursor.fetchone()
            logger.debug(f"DBManager: Post-PRAGMA test query on connection to '{db_path}' SUCCEEDED.")
        except sqlite3.Error as test_e:
            logger.error(f"DBManager: Post-PRAGMA test query on connection to '{db_path}' FAILED: {test_e}", exc_info=True)
            if conn: conn.close()
            raise RuntimeError(f"Connection to '{db_path}' became unusable after PRAGMA/connect: {test_e}") from test_e

        # Check if connection is live before yielding (addresses potential pre-closure issues).
        try:
            current_total_changes = conn.total_changes
            logger.debug(f"DBManager: Connection appears live before yield for '{db_path}'. total_changes: {current_total_changes}. Yielding connection.")
        except sqlite3.ProgrammingError as pe_before_yield:
            # This indicates the connection was closed unexpectedly.
            logger.error(f"DBManager: CRITICAL - Connection to '{db_path}' IS CLOSED before yield! Error: {pe_before_yield}", exc_info=True)
            if conn: conn.close() # Ensure it's closed if not already.
            raise RuntimeError(f"Connection to '{db_path}' was closed before it could be yielded.") from pe_before_yield

        yield conn # Provide the connection to the `with` block.

        # If the `with` block completes without exceptions, commit the transaction.
        logger.debug(f"DBManager: Returned from yield for '{db_path}'. Attempting commit. Conn id: {id(conn)}")
        conn.commit()
        logger.debug(f"DBManager: Transaction committed successfully for '{db_path}'")
    except sqlite3.Error as e:
        # Handle SQLite-specific errors.
        logger.error(f"DBManager: SQLite error occurred with database '{db_path}': {e}", exc_info=True)
        if conn:
            try:
                conn.rollback() # Rollback transaction on SQLite error.
                logger.debug(f"DBManager: Transaction rolled back for '{db_path}' due to SQLite error.")
            except sqlite3.Error as rb_e:
                logger.error(f"DBManager: Error during rollback for '{db_path}' (SQLite error path): {rb_e}", exc_info=True)
        raise # Re-raise the original SQLite error.
    except Exception as e:
        # Handle any other non-SQLite exceptions.
        logger.error(f"DBManager: A non-SQLite error occurred with database '{db_path}': {e}", exc_info=True)
        if conn:
            try:
                conn.rollback() # Rollback transaction on other errors.
                logger.debug(f"DBManager: Transaction rolled back for '{db_path}' due to non-SQLite error.")
            except sqlite3.Error as rb_e:
                 logger.error(f"DBManager: Error during rollback (non-SQLite error path) for '{db_path}': {rb_e}", exc_info=True)
        raise # Re-raise the original non-SQLite error.
    finally:
        # Ensure the connection is always closed, whether an error occurred or not.
        if conn:
            logger.debug(f"DBManager: Closing connection in finally block for '{db_path}'. Conn id: {id(conn)}")
            conn.close()
            logger.debug(f"DBManager: Connection to '{db_path}' closed.")
        else:
            logger.debug(f"DBManager: No active connection object to close in finally block for '{db_path}' (conn was None).")


class DatabaseManager:
    """
    Manages database operations by providing a simplified interface
    for common SQL tasks like SELECT, INSERT, UPDATE, DELETE.
    It uses the `get_database_connection` context manager for robust
    connection and transaction handling.
    """
    def __init__(self):
        """
        Initializes the DatabaseManager, primarily setting up a logger.
        """
        # Use Flask's current_app.logger if available, otherwise a standard Python logger.
        self.logger = current_app.logger if current_app else logging.getLogger(__name__)
        self.logger.debug("DatabaseManager instance created.")

    def _execute_raw_query(self, query_type, query, params=None):
        """
        Internal helper to execute queries and handle common cursor logic.
        Not meant to be called directly from outside.
        """
        params = params or ()
        self.logger.debug(f"DBManager: _execute_raw_query (type: {query_type}): {query} with params: {params}")
        with get_database_connection() as conn:
            # The check `conn.total_changes` before cursor creation was a debug step.
            # It can be useful to ensure the connection object `conn` is still valid
            # if there were prior issues with connection management.
            try:
                self.logger.debug(f"DBManager: _execute_raw_query - conn.total_changes: {conn.total_changes}. Conn id: {id(conn)}")
            except sqlite3.ProgrammingError as pe: # Indicates connection might be closed
                self.logger.error(f"DBManager: _execute_raw_query - Connection is closed before cursor creation! Error: {pe}. Conn id: {id(conn)}", exc_info=True)
                raise # Re-raise to indicate a critical failure.

            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                self.logger.debug(f"DBManager: _execute_raw_query - Query executed. Rowcount (if applicable): {cursor.rowcount}")
                
                if query_type == "fetchone":
                    return cursor.fetchone()
                elif query_type == "fetchall":
                    return cursor.fetchall()
                elif query_type == "insert":
                    return cursor.lastrowid
                elif query_type in ["update", "delete", "execute_query"]: # execute_query for DDL/general
                    return cursor.rowcount
                else: # Should not happen
                    raise ValueError(f"Unsupported query_type: {query_type}")

            except sqlite3.Error as e:
                self.logger.error(f"DBManager: _execute_raw_query - SQLite error during execution: {query} - {e}", exc_info=True)
                raise # Re-raise the SQLite error to be handled by calling code or context manager.
            finally:
                if cursor:
                    cursor.close()

    def execute_query(self, query, params=None):
        """
        Executes a general SQL query (typically DDL like CREATE TABLE, or other non-SELECT/INSERT/UPDATE/DELETE commands).
        For DML that modifies data and where rowcount is relevant (like some UPDATE/DELETE), this can also be used.

        Args:
            query (str): The SQL query string.
            params (tuple, optional): Parameters to substitute into the query. Defaults to None.

        Returns:
            int: The number of rows affected if applicable (e.g., for some DML), or often -1 for DDL.
                 Behavior depends on the specific SQL command and SQLite driver.
        """
        return self._execute_raw_query("execute_query", query, params)

    def fetchone(self, query, params=None):
        """
        Executes a SELECT query and fetches the first row as a dictionary-like object.

        Args:
            query (str): The SQL SELECT query string.
            params (tuple, optional): Parameters to substitute into the query. Defaults to None.

        Returns:
            sqlite3.Row or None: The first row if found, otherwise None.
        """
        row = self._execute_raw_query("fetchone", query, params)
        self.logger.debug(f"DBManager: fetchone - result: {'Row returned' if row else 'No row returned'}")
        return row

    def fetchall(self, query, params=None):
        """
        Executes a SELECT query and fetches all rows as a list of dictionary-like objects.

        Args:
            query (str): The SQL SELECT query string.
            params (tuple, optional): Parameters to substitute into the query. Defaults to None.

        Returns:
            list: A list of sqlite3.Row objects. Returns an empty list if no rows are found.
        """
        rows = self._execute_raw_query("fetchall", query, params)
        self.logger.debug(f"DBManager: fetchall - result: {len(rows)} rows returned.")
        return rows

    def insert(self, query, params=None):
        """
        Executes an INSERT SQL query.

        Args:
            query (str): The SQL INSERT query string.
            params (tuple, optional): Parameters to substitute into the query. Defaults to None.

        Returns:
            int or None: The ID of the last inserted row (if `lastrowid` is supported and applicable),
                         otherwise None or another value depending on the database/driver.
        """
        last_id = self._execute_raw_query("insert", query, params)
        self.logger.debug(f"DBManager: insert - lastrowid: {last_id}")
        return last_id

    def update(self, query, params=None):
        """
        Executes an UPDATE SQL query.

        Args:
            query (str): The SQL UPDATE query string.
            params (tuple, optional): Parameters to substitute into the query. Defaults to None.

        Returns:
            int: The number of rows affected by the UPDATE operation.
        """
        rc = self._execute_raw_query("update", query, params)
        self.logger.debug(f"DBManager: update - rowcount: {rc}")
        return rc

    def delete(self, query, params=None):
        """
        Executes a DELETE SQL query.

        Args:
            query (str): The SQL DELETE query string.
            params (tuple, optional): Parameters to substitute into the query. Defaults to None.

        Returns:
            int: The number of rows affected by the DELETE operation.
        """
        rc = self._execute_raw_query("delete", query, params)
        self.logger.debug(f"DBManager: delete - rowcount: {rc}")
        return rc

# Note on the example snippet previously at the end:
# The lines:
# # db_manager = None
# # def init_db_manager(app):
# #     global db_manager
# #     db_manager = DatabaseManager()
# appear to be an illustrative example of how one *might* initialize a global
# db_manager instance if it weren't already instantiated at the module level
# (as `db_manager = DatabaseManager()` is now done in `app/db.py` which imports this class,
# or if this class itself was the primary provider of the global instance).
# In the current project structure, `app.db.db_manager` is the global instance.