"""
Utility for running functions within a Flask application context in a separate thread.

This is essential for background tasks or operations initiated from a request
that need to access Flask's application context (e.g., `current_app`,
database connections, configuration, logger) but should not block the main
request-response cycle.
"""
import threading
from flask import current_app # Though not directly used in run_in_app_context, it's related.

def run_in_app_context(app, target_func, *args, **kwargs):
    """
    Executes a target function with given arguments in a new daemon thread,
    ensuring the Flask application context is active within that thread.

    This is crucial for functions that rely on `current_app` or other
    context-bound proxies when run outside the main request thread (e.g.,
    in background tasks like sending emails or processing notifications).

    Args:
        app (Flask): The actual Flask application instance. This is required
                     to correctly push an application context in the new thread.
                     Typically, you would pass `current_app._get_current_object()`
                     from within a request context to get the actual app instance.
        target_func (callable): The function to be executed in the new thread.
        *args: Positional arguments to pass to `target_func`.
        **kwargs: Keyword arguments to pass to `target_func`.

    Example Usage (from within a Flask route or function with app context):
        from flask import current_app
        from .utils.context_runner import run_in_app_context

        def my_background_task(param1, param2):
            # This function can now safely use current_app.logger, current_app.config, etc.
            current_app.logger.info(f"Background task running with {param1} and {param2}")
            # ... do some work ...

        # Inside a route:
        @app.route('/start_task')
        def start_task_route():
            flask_app_instance = current_app._get_current_object()
            run_in_app_context(flask_app_instance, my_background_task, "value1", param2="value2")
            return "Task started in background."
    """
    if not app:
        # Log an error or raise an exception if the app instance is not provided,
        # as it's critical for setting up the context.
        # Using a generic logger here as current_app might not be available.
        logging.getLogger(__name__).error(
            "run_in_app_context called without a valid Flask app instance. "
            "Background task may fail if it relies on app context."
        )
        # Depending on strictness, could raise ValueError("Flask app instance is required.")

    def wrapped_target():
        """
        A wrapper function that sets up the Flask application context
        before calling the `target_func`.
        """
        # `app.app_context()` creates and pushes an application context,
        # making `current_app` and other context-bound objects available.
        with app.app_context():
            # Now, within this 'with' block, target_func can safely access current_app.
            try:
                target_func(*args, **kwargs)
            except Exception as e:
                # Log any exceptions that occur within the background thread,
                # as they might otherwise go unnoticed.
                # It's important that `app.logger` is accessible here due to app_context.
                app.logger.error(
                    f"Exception in background thread for function '{target_func.__name__}': {e}",
                    exc_info=True # Includes stack trace.
                )
                # Depending on the application's needs, further error handling or
                # notification mechanisms could be added here.

    # Create a new thread to run the wrapped_target function.
    # `daemon=True` means the thread will not prevent the main application from exiting.
    thread = threading.Thread(target=wrapped_target, daemon=True)
    thread.start() # Start the execution of the thread.
    # The function returns immediately after starting the thread; it does not wait for completion.