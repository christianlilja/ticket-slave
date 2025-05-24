"""
Main entry point for running the Flask application.

This script initializes and runs the Flask application using the
application factory pattern (`create_app`). It's typically used for
development purposes to start the built-in Flask development server.

For production deployments, a WSGI server like Gunicorn or uWSGI would
typically be used, and they would import the `app` object (or call `create_app`)
directly, rather than executing this script.
"""
# Import the application factory function from the 'app' package (app/__init__.py).
from app.app import app # Direct import of app instance from app.app

# Note: The original template had `from app import create_app` and `app = create_app()`.
# If app.app directly provides the configured app instance, then `create_app()` call is not needed here.
# If app.app.py is structured to be the one calling create_app and defining 'app',
# then importing 'app' from there is correct.
# The key is that 'app' here should be the fully configured Flask app instance.

# The `if __name__ == '__main__':` block ensures that the Flask development
# server is started only when this script is executed directly
# (e.g., by running `python run.py` from the command line).
# It will not run if this script is imported as a module by another script
# or by a WSGI server.
if __name__ == '__main__':
    # app.run() starts the Flask development server.
    # - host="0.0.0.0": Makes the server accessible from any IP address on the network,
    #   not just localhost. This is useful for testing from other devices on the
    #   local network or within containers.
    # - port=5000: Specifies the port number the server will listen on.
    # - debug=True: Enables debug mode. This provides several features useful for
    #   development, including:
    #     - An interactive debugger in the browser if an unhandled exception occurs.
    #     - Automatic reloading of the application when code changes are detected.
    #   IMPORTANT: Debug mode should NEVER be enabled in a production environment
    #              due to security risks and performance implications.
    #              FLASK_ENV=production or FLASK_DEBUG=0 should be set in production.
    app.run(host="0.0.0.0", port=5000, debug=True)