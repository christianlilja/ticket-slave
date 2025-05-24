"""
Database utility functions.

This module provides helper functions for common database operations,
particularly for fetching specific records (like tickets or users) and
handling cases where a record might not be found by aborting with a 404 error.
"""
from flask import abort, current_app # For aborting requests and accessing app logger.

def get_ticket_or_404(ticket_id, db_manager, logger=None, log_extra=None):
    """
    Fetches a single ticket by its ID from the database.

    If the ticket with the specified ID is not found, this function logs a
    warning message and then aborts the current request with a 404 (Not Found)
    HTTP error. This pattern simplifies error handling in view functions,
    as they don't need to explicitly check if the ticket was found.

    Args:
        ticket_id (int): The unique identifier of the ticket to fetch.
        db_manager: An instance of the DatabaseManager (or a compatible object
                    that has a `fetchone` method) used to query the database.
        logger (logging.Logger, optional): An specific logger instance to use.
            If None, `current_app.logger` from the Flask application context
            will be used. Defaults to None.
        log_extra (dict, optional): A dictionary of extra information to include
            in log messages, useful for adding context like user ID or request ID.
            Defaults to None.

    Returns:
        sqlite3.Row: A dictionary-like row object representing the fetched ticket
                     if found. The structure depends on the columns selected by
                     the `db_manager.fetchone` query (typically 'SELECT * ...').

    Raises:
        werkzeug.exceptions.NotFound: If no ticket with the given `ticket_id` is found.
                                      This is triggered by `abort(404)`.
    """
    # Use the Flask application's logger if no specific logger is provided.
    # This requires an active application context.
    if logger is None:
        logger = current_app.logger
    
    # Query the database for the ticket.
    # Assumes db_manager.fetchone returns a dictionary-like object or None.
    ticket = db_manager.fetchone('SELECT * FROM tickets WHERE id = ?', (ticket_id,))
    
    if ticket is None:
        # If the ticket is not found, prepare extra information for logging.
        final_log_extra = {'ticket_id': ticket_id, 'entity_type': 'ticket'}
        if log_extra: # Merge provided log_extra if it exists.
            final_log_extra.update(log_extra)
        
        logger.warning("Ticket not found in database.", extra=final_log_extra)
        # Abort the request with a 404 error. The user will see a "Not Found" page.
        # The error handler registered in app/error.py might customize this page.
        abort(404, description=f"Ticket with ID {ticket_id} not found.")
    
    # If ticket is found, return the ticket data.
    return ticket

def get_user_or_404(user_id, db_manager, logger=None, log_extra=None):
    """
    Fetches a single user by their ID from the database.

    Similar to `get_ticket_or_404`, if the user with the specified ID is not
    found, this function logs a warning and aborts the current request with a
    404 HTTP error.

    Args:
        user_id (int): The unique identifier of the user to fetch.
        db_manager: An instance of the DatabaseManager (or a compatible object
                    with a `fetchone` method) for database queries.
        logger (logging.Logger, optional): A specific logger instance.
            If None, `current_app.logger` is used. Defaults to None.
        log_extra (dict, optional): Extra information for logging.
            Defaults to None.

    Returns:
        sqlite3.Row: A dictionary-like row object representing the fetched user
                     if found.

    Raises:
        werkzeug.exceptions.NotFound: If no user with the given `user_id` is found.
    """
    if logger is None:
        logger = current_app.logger

    # Query the database for the user.
    user = db_manager.fetchone('SELECT * FROM users WHERE id = ?', (user_id,))
    
    if user is None:
        # If the user is not found, log and abort.
        final_log_extra = {'user_id': user_id, 'entity_type': 'user'}
        if log_extra:
            final_log_extra.update(log_extra)
            
        logger.warning("User not found in database.", extra=final_log_extra)
        abort(404, description=f"User with ID {user_id} not found.")
        
    return user

# Potential future additions:
# - get_comment_or_404
# - get_attachment_or_404
# - get_queue_or_404
# These would follow the same pattern for other entities if needed.