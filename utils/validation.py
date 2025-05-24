"""
Input validation utility functions.

This module provides helper functions for validating various types of input data,
such as user IDs for assignments, form fields, etc.
"""
from flask import flash, redirect, url_for, current_app # Flask utilities for messaging and routing.

def validate_user_assignment_input(user_id_str, db_manager, ticket_id_for_redirect, logger=None, log_extra_base=None):
    """
    Validates a string input intended to be a user ID for assigning to a ticket.

    This function checks several conditions:
    1. If `user_id_str` is empty or whitespace, it's treated as an "unassign" action,
       and `validated_user_id` will be `None`. This is considered a valid outcome.
    2. If `user_id_str` is provided, it attempts to convert it to an integer.
       If conversion fails (ValueError), it's an invalid ID format.
    3. If conversion to integer is successful, it checks if a user with that ID
       exists in the database. If not, the ID is invalid.

    On validation failure (invalid format or non-existent user), it flashes an
    appropriate error message to the user and prepares a redirect response object
    to send the user back to the relevant ticket detail page.

    Args:
        user_id_str (str or None): The string input from a form or query parameter
                                   representing the user ID. Can be None or empty
                                   to signify unassignment.
        db_manager: An instance of the DatabaseManager (or a compatible object
                    with a `fetchone` method) for database queries.
        ticket_id_for_redirect (int): The ID of the ticket to which the user is
                                      being assigned/unassigned. This is used to
                                      construct the redirect URL in case of validation failure.
        logger (logging.Logger, optional): A specific logger instance.
            If None, `current_app.logger` is used. Defaults to None.
        log_extra_base (dict, optional): A base dictionary of extra information
            to include in log messages for context. Defaults to None.

    Returns:
        tuple: A tuple `(validated_user_id_int, redirect_obj)` where:
               - `validated_user_id_int` (int or None): The validated integer user ID
                 if the input was valid and represented an existing user. It's `None`
                 if the input signified an "unassign" action (empty string) or if
                 validation failed (in which case `redirect_obj` will be set).
               - `redirect_obj` (werkzeug.wrappers.Response or None): A Flask redirect
                 response object if validation failed. It's `None` if validation
                 was successful (including successful unassignment).
    """
    # Use the Flask application's logger if no specific logger is provided.
    if logger is None:
        logger = current_app.logger
    
    # Initialize validated_user_id to None. This will be the result for unassignment
    # or if validation fails early.
    validated_user_id = None
    
    # Prepare a default redirect response object. This will be returned if validation fails.
    # It redirects back to the detail page of the ticket being modified.
    redirect_response_on_failure = redirect(url_for('tickets_bp.ticket_detail', ticket_id=ticket_id_for_redirect))

    # Check if user_id_str is provided and not just whitespace.
    # If it's empty or None, it implies an "unassign" action, which is valid.
    if user_id_str and user_id_str.strip():
        try:
            # Attempt to convert the string to an integer.
            val_user_id = int(user_id_str.strip())
            
            # Check if a user with this integer ID exists in the database.
            user_exists = db_manager.fetchone("SELECT 1 FROM users WHERE id = ?", (val_user_id,))
            
            if not user_exists:
                # User ID is a valid integer, but no such user exists.
                flash(f"Error: User with ID {val_user_id} selected for assignment does not exist.", 'danger')
                log_message = f"User assignment validation failed: User ID {val_user_id} does not exist."
                if log_extra_base: logger.warning(log_message, extra=log_extra_base)
                else: logger.warning(log_message)
                return None, redirect_response_on_failure # Return None for ID, and the redirect object.
            
            # If user exists, this is the validated user ID.
            validated_user_id = val_user_id
            
        except ValueError:
            # The provided string could not be converted to an integer.
            flash(f"Error: Invalid user ID format provided for assignment ('{user_id_str}').", 'danger')
            log_message = f"User assignment validation failed: Invalid user ID format '{user_id_str}'."
            if log_extra_base: logger.warning(log_message, extra=log_extra_base)
            else: logger.warning(log_message)
            return None, redirect_response_on_failure # Return None for ID, and the redirect object.
    
    # If we reach here, validation was successful.
    # - If user_id_str was empty/None, validated_user_id is None (unassign).
    # - If user_id_str was a valid existing user ID, validated_user_id is that integer ID.
    # In both successful cases, no redirect is needed from this validation step.
    return validated_user_id, None