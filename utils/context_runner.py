# utils/context_runner.py
import threading
from flask import current_app

def run_in_app_context(app, target_func, *args, **kwargs):
    """
    Launch target_func(*args, **kwargs) inside a thread with Flask app context.
    Requires the actual Flask app instance to be passed explicitly.
    """
    def wrapped():
        # Set up the app context for the background thread
        with app.app_context():  # Ensure the app context is active
            target_func(*args, **kwargs)

    thread = threading.Thread(target=wrapped, daemon=True)
    thread.start()