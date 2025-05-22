# app/database_manager.py
import sqlite3
import os # Ensure os is imported
from flask import current_app
import logging
from contextlib import contextmanager

def _get_db_path_for_manager():
    if not hasattr(current_app, 'config'):
        raise RuntimeError("DBManager: Application context or config not available for _get_db_path_for_manager.")
    
    db_path_config = current_app.config.get('DATABASE')
    
    if db_path_config:
        # Using os.path.abspath to ensure the path is absolute for logging/consistency
        abs_db_path = os.path.abspath(db_path_config)
        current_app.logger.debug(f"DBManager: Original DATABASE config path: '{db_path_config}', Resolved absolute path: '{abs_db_path}'")
    else:
        current_app.logger.warning("DBManager: DATABASE key in config is None or empty.")

    if not db_path_config:
        raise RuntimeError("DBManager: DATABASE key not found, not configured, or empty in current_app.config.")
    return db_path_config


@contextmanager
def get_database_connection():
    """
    Provides and manages a database connection.
    """
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    
    app_id = id(current_app) if current_app else "N/A"
    config_id = id(current_app.config) if hasattr(current_app, 'config') else "N/A"
    logger.debug(f"DBManager: get_database_connection called. current_app id: {app_id}, config id: {config_id}")

    db_path = _get_db_path_for_manager()
    logger.debug(f"DBManager: Resolved db_path for connection: '{db_path}'")
    
    conn = None
    try:
        logger.debug(f"DBManager: Attempting sqlite3.connect(db_path='{db_path}')")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        logger.debug(f"DBManager: Connection object created for '{db_path}'. Conn id: {id(conn)}")

        try:
            conn.execute("PRAGMA foreign_keys = ON")
            logger.debug(f"DBManager: PRAGMA foreign_keys=ON executed for '{db_path}'")
        except sqlite3.Error as pragma_e:
            logger.error(f"DBManager: Error executing PRAGMA foreign_keys=ON for '{db_path}': {pragma_e}", exc_info=True)
            if conn: conn.close()
            raise RuntimeError(f"Failed to set PRAGMA foreign_keys on db connection to '{db_path}': {pragma_e}") from pragma_e
        
        try:
            test_cursor = conn.cursor()
            test_cursor.execute("SELECT 1")
            test_cursor.fetchone()
            logger.debug(f"DBManager: Post-PRAGMA test query on connection to '{db_path}' SUCCEEDED.")
        except sqlite3.Error as test_e:
            logger.error(f"DBManager: Post-PRAGMA test query on connection to '{db_path}' FAILED: {test_e}", exc_info=True)
            if conn: conn.close()
            raise RuntimeError(f"Connection to '{db_path}' became unusable after PRAGMA/connect: {test_e}") from test_e

        try:
            current_total_changes = conn.total_changes
            logger.debug(f"DBManager: Connection appears live before yield for '{db_path}'. total_changes: {current_total_changes}. Yielding connection.")
        except sqlite3.ProgrammingError as pe_before_yield:
            logger.error(f"DBManager: CRITICAL - Connection to '{db_path}' IS CLOSED before yield! Error: {pe_before_yield}", exc_info=True)
            if conn: conn.close()
            raise RuntimeError(f"Connection to '{db_path}' was closed before it could be yielded.") from pe_before_yield
        
        yield conn
        
        logger.debug(f"DBManager: Returned from yield for '{db_path}'. Attempting commit. Conn id: {id(conn)}")
        conn.commit()
        logger.debug(f"DBManager: Transaction committed for '{db_path}'")
    except sqlite3.Error as e:
        logger.error(f"DBManager: SQLite error for '{db_path}': {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
                logger.debug(f"DBManager: Transaction rolled back for '{db_path}' due to SQLite error.")
            except sqlite3.Error as rb_e:
                logger.error(f"DBManager: Error during rollback for '{db_path}': {rb_e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"DBManager: Non-SQLite error for '{db_path}': {e}", exc_info=True)
        if conn:
            try:
                conn.rollback()
                logger.debug(f"DBManager: Transaction rolled back for '{db_path}' due to non-SQLite error.")
            except sqlite3.Error as rb_e:
                 logger.error(f"DBManager: Error during rollback (non-SQLite error path) for '{db_path}': {rb_e}", exc_info=True)
        raise
    finally:
        if conn:
            logger.debug(f"DBManager: Closing connection in finally block for '{db_path}'. Conn id: {id(conn)}")
            conn.close()
            logger.debug(f"DBManager: Connection closed for '{db_path}'")
        else:
            logger.debug(f"DBManager: No connection object to close in finally block for '{db_path}' (conn was None).")


class DatabaseManager:
    """
    A class to manage database operations, abstracting direct SQLite calls.
    """
    def __init__(self):
        self.logger = current_app.logger if current_app else logging.getLogger(__name__)

    def execute_query(self, query, params=None):
        """
        Executes a given SQL query (DDL or DML). Returns rowcount for DML.
        """
        params = params or ()
        self.logger.debug(f"DBManager: execute_query: {query} with params: {params}")
        with get_database_connection() as conn:
            try:
                self.logger.debug(f"DBManager: execute_query - conn.total_changes: {conn.total_changes}. Conn id: {id(conn)}")
            except sqlite3.ProgrammingError as pe:
                self.logger.error(f"DBManager: execute_query - conn is CLOSED! Error: {pe}. Conn id: {id(conn)}", exc_info=True)
                raise
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                self.logger.debug(f"DBManager: execute_query - executed. Rowcount: {cursor.rowcount}")
                return cursor.rowcount
            except sqlite3.Error as e:
                self.logger.error(f"DBManager: execute_query - error: {query} - {e}", exc_info=True)
                raise
            finally:
                if cursor: cursor.close()

    def fetchone(self, query, params=None):
        """
        Executes a query and fetches one row.
        """
        params = params or ()
        self.logger.debug(f"DBManager: fetchone: {query} with params: {params}")
        with get_database_connection() as conn:
            try:
                self.logger.debug(f"DBManager: fetchone - conn.total_changes: {conn.total_changes}. Conn id: {id(conn)}")
            except sqlite3.ProgrammingError as pe:
                self.logger.error(f"DBManager: fetchone - conn is CLOSED! Error: {pe}. Conn id: {id(conn)}", exc_info=True)
                raise
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                row = cursor.fetchone()
                self.logger.debug(f"DBManager: fetchone - result: {'Row' if row else 'No row'}")
                return row
            except sqlite3.Error as e:
                self.logger.error(f"DBManager: fetchone - error: {query} - {e}", exc_info=True)
                raise
            finally:
                if cursor: cursor.close()

    def fetchall(self, query, params=None):
        """
        Executes a query and fetches all rows.
        """
        params = params or ()
        self.logger.debug(f"DBManager: fetchall: {query} with params: {params}")
        with get_database_connection() as conn:
            try:
                self.logger.debug(f"DBManager: fetchall - conn.total_changes: {conn.total_changes}. Conn id: {id(conn)}")
            except sqlite3.ProgrammingError as pe:
                self.logger.error(f"DBManager: fetchall - conn is CLOSED! Error: {pe}. Conn id: {id(conn)}", exc_info=True)
                raise
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                self.logger.debug(f"DBManager: fetchall - result: {len(rows)} rows")
                return rows
            except sqlite3.Error as e:
                self.logger.error(f"DBManager: fetchall - error: {query} - {e}", exc_info=True)
                raise
            finally:
                if cursor: cursor.close()

    def insert(self, query, params=None):
        """
        Executes an INSERT query and returns the last inserted row ID.
        """
        params = params or ()
        self.logger.debug(f"DBManager: insert: {query} with params: {params}")
        with get_database_connection() as conn:
            try:
                self.logger.debug(f"DBManager: insert - conn.total_changes: {conn.total_changes}. Conn id: {id(conn)}")
            except sqlite3.ProgrammingError as pe:
                self.logger.error(f"DBManager: insert - conn is CLOSED! Error: {pe}. Conn id: {id(conn)}", exc_info=True)
                raise
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                last_id = cursor.lastrowid
                self.logger.debug(f"DBManager: insert - lastrowid: {last_id}")
                return last_id
            except sqlite3.Error as e:
                self.logger.error(f"DBManager: insert - error: {query} - {e}", exc_info=True)
                raise
            finally:
                if cursor: cursor.close()

    def update(self, query, params=None):
        """
        Executes an UPDATE query and returns the number of rows affected.
        """
        params = params or ()
        self.logger.debug(f"DBManager: update: {query} with params: {params}")
        with get_database_connection() as conn:
            try:
                self.logger.debug(f"DBManager: update - conn.total_changes: {conn.total_changes}. Conn id: {id(conn)}")
            except sqlite3.ProgrammingError as pe:
                self.logger.error(f"DBManager: update - conn is CLOSED! Error: {pe}. Conn id: {id(conn)}", exc_info=True)
                raise
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                rc = cursor.rowcount
                self.logger.debug(f"DBManager: update - rowcount: {rc}")
                return rc
            except sqlite3.Error as e:
                self.logger.error(f"DBManager: update - error: {query} - {e}", exc_info=True)
                raise
            finally:
                if cursor: cursor.close()

    def delete(self, query, params=None):
        """
        Executes a DELETE query and returns the number of rows affected.
        """
        params = params or ()
        self.logger.debug(f"DBManager: delete: {query} with params: {params}")
        with get_database_connection() as conn:
            try:
                self.logger.debug(f"DBManager: delete - conn.total_changes: {conn.total_changes}. Conn id: {id(conn)}")
            except sqlite3.ProgrammingError as pe:
                self.logger.error(f"DBManager: delete - conn is CLOSED! Error: {pe}. Conn id: {id(conn)}", exc_info=True)
                raise
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                rc = cursor.rowcount
                self.logger.debug(f"DBManager: delete - rowcount: {rc}")
                return rc
            except sqlite3.Error as e:
                self.logger.error(f"DBManager: delete - error: {query} - {e}", exc_info=True)
                raise
            finally:
                if cursor: cursor.close()

# Example of how it might be initialized and used in the app (e.g., in app/__init__.py or app/app.py)
# db_manager = None
# def init_db_manager(app):
#     global db_manager
#     db_manager = DatabaseManager()