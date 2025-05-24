"""
Flask session helper functions.

This module provides utility functions for interacting with the Flask session,
primarily for retrieving common user-related information stored in the session
and preparing it for use, such_as in logging.
"""
from flask import session, current_app # Import Flask's session and current_app proxies.

def get_current_session_info():
    """
    Retrieves current user information (user_id, username) from the Flask session
    and prepares a base dictionary suitable for enriching log messages with
    user context.

    This function centralizes the logic for accessing common session variables,
    ensuring consistency and making it easier to add more session-derived
    information in the future if needed.

    Returns:
        dict: A dictionary with the following keys:
            'user_id' (int or None): The ID of the currently logged-in user,
                                     or None if 'user_id' is not in the session.
            'username' (str or None): The username of the currently logged-in user,
                                      or None if 'username' is not in the session.
            'base_log_extra' (dict): A dictionary containing 'user_id' and 'username',
                                     intended to be merged into the 'extra' parameter
                                     of logging calls (e.g., `current_app.logger.info(msg, extra=info['base_log_extra'])`).
                                     This helps in standardizing log entries with user context.
    
    Example Usage:
        session_info = get_current_session_info()
        if session_info['user_id']:
            current_app.logger.info("User action performed.", extra=session_info['base_log_extra'])
        else:
            current_app.logger.info("Anonymous action performed.") # base_log_extra will have None values
    """
    # Retrieve 'user_id' and 'username' from the session.
    # Using session.get() is safer as it returns None if the key is not found,
    # rather than raising a KeyError.
    user_id = session.get('user_id')
    username = session.get('username')
    
    # Prepare a dictionary specifically for logging context.
    # This can be directly passed to the 'extra' argument of logger methods.
    base_log_extra = {
        'user_id': user_id,     # Will be None if user is not logged in.
        'username': username    # Will be None if user is not logged in.
        # Potentially add other common session items here for logging, e.g., 'ip_address', 'session_id'
    }
    
    # Return a dictionary containing the retrieved session information
    # and the pre-formatted logging dictionary.
    return {
        'user_id': user_id,
        'username': username,
        'base_log_extra': base_log_extra
        # Consider adding 'is_admin': session.get('is_admin', False) if frequently needed.
    }

# Potential future additions:
# - def clear_user_session(): session.clear() (though often done in logout routes)
# - def set_user_session(user_id, username, is_admin): (though often done in login routes)