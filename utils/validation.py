from flask import flash, redirect, url_for, current_app

def validate_user_assignment_input(user_id_str, db_manager, ticket_id_for_redirect, logger=None, log_extra_base=None):
    """
    Validates a string input for a user ID to be assigned to a ticket.
    Checks if it's a valid integer and if the user exists in the database.
    Flashes appropriate messages and prepares a redirect response on failure.

    Args:
        user_id_str (str): The string input for the user ID.
        db_manager: An instance of the database manager.
        ticket_id_for_redirect (int): The ticket ID to redirect to on failure.
        logger: Optional logger instance. If None, current_app.logger is used.
        log_extra_base (dict, optional): Base dictionary for logging.

    Returns:
        tuple: (validated_user_id_int, None) on success, 
               or (None, redirect_response_object) on failure.
    """
    if logger is None:
        logger = current_app.logger
    
    validated_user_id = None
    redirect_response = redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id_for_redirect))

    if user_id_str and user_id_str.strip():
        try:
            val_user_id = int(user_id_str)
            user_exists = db_manager.fetchone("SELECT 1 FROM users WHERE id = ?", (val_user_id,))
            if not user_exists:
                flash('Selected user for assignment does not exist.', 'danger')
                logger.warning(f"Update assignment failed: User ID {val_user_id} DNE.", extra=log_extra_base)
                return None, redirect_response
            validated_user_id = val_user_id
        except ValueError:
            flash('Invalid user ID for assignment.', 'danger')
            logger.warning(f"Update assignment failed: Invalid user ID '{user_id_str}'.", extra=log_extra_base)
            return None, redirect_response
    
    return validated_user_id, None # Success, no redirect needed if validated_user_id is None (for unassigning) or a valid ID