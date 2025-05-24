"""
Authentication routes for user registration, login, and logout.

This module defines the Flask Blueprint for authentication-related
endpoints, managing user sessions and interactions with the database
for user credential verification and creation.
"""
from flask import Blueprint, request, redirect, url_for, render_template, session, flash, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import db_manager # Use the global db_manager instance for database operations
import sqlite3 # Imported specifically for catching sqlite3.IntegrityError

# Define the Blueprint for authentication routes.
# All routes defined with 'auth_bp' will be prefixed, e.g., /login, /register.
auth_bp = Blueprint('auth_bp', __name__)


def is_registration_allowed():
    """
    Checks if user registration is currently enabled in the application settings.

    Returns:
        bool: True if registration is allowed, False otherwise.
    """
    # Fetches the 'allow_registration' setting from the database.
    setting = db_manager.fetchone("SELECT value FROM settings WHERE key = 'allow_registration'")
    # Returns True if the setting exists and its value is '1'.
    return setting and setting['value'] == '1'


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handles new user registration.

    GET: Displays the registration form.
    POST: Processes the registration form data, creates a new user if valid and
          registration is allowed.
    """
    # First, check if public registration is enabled.
    if not is_registration_allowed():
        flash('User registration is currently disabled by the administrator.', 'warning')
        return redirect(url_for('auth_bp.login')) # Redirect to login if registration is off.

    if request.method == 'POST':
        username = request.form.get('username')
        raw_password = request.form.get('password') # Password from form, before hashing.

        # Basic validation: ensure username and password are provided.
        if not username or not raw_password:
            flash('Username and password are required fields.', 'danger')
            return redirect(url_for('auth_bp.register')) # Stay on registration page.

        # TODO: Implement more robust username validation:
        #       - Minimum/maximum length.
        #       - Allowed characters (e.g., alphanumeric, no special symbols).
        #       - Consider case sensitivity policy.
        # Example: if not re.match(r"^[a-zA-Z0-9_]{3,20}$", username): flash(...)

        # TODO: Implement password complexity rules:
        #       - Minimum length (e.g., 8-12 characters).
        #       - Requirement for uppercase, lowercase, numbers, special characters.
        # Example:
        # if len(raw_password) < 8:
        #     flash('Password must be at least 8 characters long.', 'danger')
        #     return redirect(url_for('auth_bp.register'))
        # if not re.search(r"[A-Z]", raw_password) or \
        #    not re.search(r"[a-z]", raw_password) or \
        #    not re.search(r"[0-9]", raw_password):
        #     flash('Password must include uppercase, lowercase, and numbers.', 'danger')
        #     return redirect(url_for('auth_bp.register'))

        # Securely hash the password before storing it.
        hashed_password = generate_password_hash(raw_password)

        try:
            # Check if the username already exists to prevent duplicates.
            existing_user = db_manager.fetchone('SELECT id FROM users WHERE username = ?', (username,))
            if existing_user:
                flash('Username already taken. Please choose a different one.', 'danger')
                return redirect(url_for('auth_bp.register'))

            # Insert the new user into the database.
            # Default values for other user fields (is_admin, email, etc.) are handled by the DB schema.
            db_manager.insert(
                'INSERT INTO users (username, password) VALUES (?, ?)',
                (username, hashed_password)
            )
            current_app.logger.info(f"New user registered: {username}")
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('auth_bp.login')) # Redirect to login page after successful registration.

        except sqlite3.IntegrityError:
            # This handles a race condition if the username was created between
            # the existence check and the insert operation.
            current_app.logger.warning(f"IntegrityError during registration for username: {username}. Likely a race condition.")
            flash('Username already exists. Please try a different one.', 'danger')
            return redirect(url_for('auth_bp.register'))
        except Exception as e:
            # Log any other unexpected errors during registration.
            current_app.logger.error(f"An unexpected error occurred during registration for {username}: {e}", exc_info=True)
            flash('An error occurred during registration. Please try again later or contact support.', 'danger')
            return redirect(url_for('auth_bp.register'))

    # For GET requests, display the registration form.
    # Pass `is_registration_allowed` again in case it changed, though less likely for GET.
    return render_template('register.html', registration_enabled=is_registration_allowed())


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handles user login.

    GET: Displays the login form.
    POST: Processes login credentials, authenticates the user, and establishes a session.
    """
    # Determine if the registration link should be shown on the login page.
    registration_enabled = is_registration_allowed()

    if request.method == 'POST':
        username = request.form.get('username')
        password_from_form = request.form.get('password') # Password entered by the user.

        # Basic validation: ensure username and password were submitted.
        if not username or not password_from_form:
            flash('Username and password are required.', 'danger')
            return render_template('login.html', registration_enabled=registration_enabled)

        try:
            # Fetch the user from the database by username.
            user = db_manager.fetchone('SELECT * FROM users WHERE username = ?', (username,))

            # Verify user existence and password correctness.
            # `check_password_hash` compares the provided password with the stored hash.
            if user and check_password_hash(user['password'], password_from_form):
                # Successful login: store user information in the session.
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['is_admin'] = bool(user['is_admin']) # Convert DB integer (0 or 1) to boolean.
                session['theme'] = user['theme'] if user['theme'] else 'default' # Fallback theme.

                current_app.logger.info(
                    f"User '{user['username']}' (ID: {user['id']}) logged in successfully.",
                    extra={'user_id': user['id'], 'username': user['username']}
                )
                flash('Logged in successfully!', 'success')
                return redirect(url_for('main_bp.index')) # Redirect to the main application page.
            else:
                # Failed login attempt (invalid username or password).
                current_app.logger.warning(
                    f"Failed login attempt for username: '{username}'.",
                    extra={'username_attempt': username}
                )
                flash('Invalid username or password. Please try again.', 'danger')
        except Exception as e:
            # Log any unexpected errors during the login process.
            current_app.logger.error(f"An error occurred during login attempt for {username}: {e}", exc_info=True)
            flash('An error occurred during login. Please try again later or contact support.', 'danger')

    # For GET requests or failed POST attempts (without redirect), display the login form.
    return render_template('login.html', registration_enabled=registration_enabled)


@auth_bp.route('/logout')
def logout():
    """
    Handles user logout.

    Clears the current session and redirects the user to the login page.
    """
    user_id_before_logout = session.get('user_id')
    username_before_logout = session.get('username')

    session.clear() # Remove all data from the session.

    current_app.logger.info(
        f"User '{username_before_logout}' (ID: {user_id_before_logout}) logged out.",
        extra={'user_id': user_id_before_logout, 'username': username_before_logout}
    )
    flash('You have been successfully logged out.', 'info')
    return redirect(url_for('auth_bp.login')) # Redirect to the login page.
