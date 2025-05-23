from flask import session, current_app

def get_current_session_info():
    """
    Retrieves current user_id and username from session and prepares
    a base dictionary for logging.

    Returns:
        dict: A dictionary containing 'user_id', 'username', 
              and 'base_log_extra'. Returns None for id/username
              if not found in session.
    """
    user_id = session.get('user_id')
    username = session.get('username')
    
    base_log_extra = {
        'user_id': user_id,
        'username': username
    }
    
    return {
        'user_id': user_id,
        'username': username,
        'base_log_extra': base_log_extra
    }