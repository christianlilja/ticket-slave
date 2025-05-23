from flask import abort, current_app

def get_ticket_or_404(ticket_id, db_manager, logger=None, log_extra=None):
    """
    Fetches a ticket by its ID. If not found, logs a warning and aborts with 404.

    Args:
        ticket_id (int): The ID of the ticket to fetch.
        db_manager: An instance of the database manager.
        logger: Optional logger instance. If None, current_app.logger is used.
        log_extra (dict, optional): Extra information for logging.

    Returns:
        The fetched ticket record, or aborts with 404 if not found.
    """
    if logger is None:
        logger = current_app.logger
    
    ticket = db_manager.fetchone('SELECT * FROM tickets WHERE id = ?', (ticket_id,))
    if ticket is None:
        final_log_extra = {'ticket_id': ticket_id, **(log_extra or {})}
        logger.warning("Ticket not found", extra=final_log_extra)
        abort(404)
    return ticket

def get_user_or_404(user_id, db_manager, logger=None, log_extra=None):
    """
    Fetches a user by their ID. If not found, logs a warning and aborts with 404.

    Args:
        user_id (int): The ID of the user to fetch.
        db_manager: An instance of the database manager.
        logger: Optional logger instance. If None, current_app.logger is used.
        log_extra (dict, optional): Extra information for logging.

    Returns:
        The fetched user record, or aborts with 404 if not found.
    """
    if logger is None:
        logger = current_app.logger

    user = db_manager.fetchone('SELECT * FROM users WHERE id = ?', (user_id,))
    if user is None:
        final_log_extra = {'user_id': user_id, **(log_extra or {})}
        logger.warning("User not found", extra=final_log_extra)
        abort(404)
    return user