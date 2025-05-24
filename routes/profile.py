"""
User profile management routes.

This module defines the Flask Blueprint for routes related to user profiles,
allowing logged-in users to view and update their personal information,
notification preferences, password, and UI theme.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, current_app
from werkzeug.security import generate_password_hash # For hashing new passwords.
from app.db import db_manager # Global database manager instance.
from utils.decorators import login_required # Ensures only logged-in users can access.
from app.notifications_core import send_email_notification, send_pushover_notification, send_apprise_notification # Core notification functions.
from utils.context_runner import run_in_app_context # Helper to run functions within app context.
import re # For email validation.

# Define the Blueprint for profile routes.
profile_bp = Blueprint('profile_bp', __name__)

@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required # User must be logged in to access their profile.
def profile():
    """
    Handles viewing and updating the logged-in user's profile.

    GET: Displays the profile form populated with the user's current data.
    POST: Processes form submissions to update profile information, including
          email, notification settings, password, and sends test notifications if requested.
    """
    user_id = session.get('user_id')
    username = session.get('username') # For logging purposes.

    log_base_extra = {'user_id': user_id, 'username': username}
    current_app.logger.info("User accessing their profile page.", extra=log_base_extra)

    # Fetch the current user's data from the database.
    # This is used for populating the form on GET and as a base for updates on POST.
    user = db_manager.fetchone('SELECT * FROM users WHERE id = ?', (user_id,))
    if not user:
        # This should ideally not happen if the user is in session.
        current_app.logger.error(
            "Critical: User ID from session not found in database during profile access.",
            extra=log_base_extra
        )
        flash("Your user account could not be found. Please log out and log back in.", "danger")
        session.clear() # Clear potentially corrupted session.
        return redirect(url_for('auth_bp.login')) # Redirect to login.

    if request.method == 'POST':
        # --- Handle Profile Update Form Submission ---
        current_app.logger.info("User submitted profile update form.", extra=log_base_extra)
        
        # Retrieve form data, falling back to existing user data if a field is not submitted
        # (though typically all relevant fields would be submitted by the form).
        email = request.form.get('email', user['email'])
        pushover_user_key = request.form.get('pushover_user_key', user['pushover_user_key'])
        pushover_api_token = request.form.get('pushover_api_token', user['pushover_api_token'])
        apprise_url = request.form.get('apprise_url', user['apprise_url'])
        # Checkboxes: value is present if checked, absent if not. Convert to 0 or 1 for DB.
        notify_email = 1 if 'notify_email' in request.form else 0
        notify_pushover = 1 if 'notify_pushover' in request.form else 0
        notify_apprise = 1 if 'notify_apprise' in request.form else 0
        new_password = request.form.get('new_password') # Optional: only update if provided.
        
        errors = {} # Dictionary to store validation errors.
        
        # Validate email format if it's being changed and is not empty.
        if email and email.strip() != user['email']: # Check if email actually changed.
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email.strip()):
                errors['email'] = "Invalid email address format."
        
        # TODO: Add password complexity validation if new_password is provided.
        # Example:
        # if new_password and len(new_password) < 8:
        #     errors['new_password'] = "New password must be at least 8 characters long."

        if errors:
            for field, msg in errors.items(): flash(msg, 'danger')
            current_app.logger.warning(f"Profile update for user ID {user_id} failed due to validation errors: {errors}", extra=log_base_extra)
            # Re-render the profile form with the initially fetched 'user' data (to show original values)
            # and the validation errors.
            return render_template('profile.html', user=user, errors=errors)

        # Log which fields are being changed for audit/debugging.
        updated_fields_summary = {
            'email_changed': email.strip() != user['email'],
            'pushover_user_key_changed': pushover_user_key.strip() != (user['pushover_user_key'] or ''),
            'pushover_api_token_changed': bool(pushover_api_token.strip()) and pushover_api_token.strip() != (user['pushover_api_token'] or ''),
            'apprise_url_changed': apprise_url.strip() != (user['apprise_url'] or ''),
            'notify_email_new_state': notify_email,
            'notify_pushover_new_state': notify_pushover,
            'notify_apprise_new_state': notify_apprise,
            'password_changed': bool(new_password) # True if a new password was entered.
        }
        log_update_details = {**log_base_extra, 'updated_fields_summary': updated_fields_summary}
            
        try:
            # Update user's general profile information in the database.
            db_manager.execute_query(
                '''UPDATE users
                   SET email = ?, pushover_user_key = ?, pushover_api_token = ?,
                       notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?
                   WHERE id = ?''',
                (email.strip(), pushover_user_key.strip(), pushover_api_token.strip(),
                 notify_email, notify_pushover, apprise_url.strip(), notify_apprise, user_id)
            )

            # If a new password was provided, hash and update it.
            if new_password:
                hashed_password = generate_password_hash(new_password)
                db_manager.execute_query('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))
                current_app.logger.info(f"User ID {user_id} updated their password.", extra=log_update_details)
            
            current_app.logger.info(f"User ID {user_id} successfully updated their profile.", extra=log_update_details)

            # If "Test Notification" button was clicked (form field 'test_notification' will be present).
            if 'test_notification' in request.form:
                current_app.logger.info(
                    f"User ID {user_id} initiated test notifications from profile.",
                    extra={**log_update_details, 'test_email_enabled': notify_email,
                           'test_pushover_enabled': notify_pushover, 'test_apprise_enabled': notify_apprise}
                )
                # Send test notifications based on the *newly saved* settings.
                send_test_notifications(
                    email.strip(), pushover_user_key.strip(), pushover_api_token.strip(), apprise_url.strip(),
                    notify_email, notify_pushover, notify_apprise
                )
                flash('Profile updated. Test notification(s) sent (if configured and enabled). Check your services.', 'info')
            else:
                flash('Profile updated successfully.', 'success')
            
            # Redirect to the profile page (GET request) to show updated information.
            return redirect(url_for('profile_bp.profile'))
        except Exception as e:
            current_app.logger.error(
                f"Error updating profile for user ID {user_id}: {e}", extra=log_base_extra, exc_info=True
            )
            flash('An unexpected error occurred while updating your profile. Please try again.', 'danger')
            # If an error occurs during update, re-render with initially fetched 'user' data
            # and a general error message.
            return render_template('profile.html', user=user, errors={"general": "Profile update failed due to a server error."})

    # For GET requests, the 'user' data (fetched at the beginning) is passed to the template.
    return render_template('profile.html', user=user)


def send_test_notifications(email, pushover_user_key, pushover_api_token, apprise_url,
                            notify_email, notify_pushover, notify_apprise):
    """
    Sends test notifications to the user based on their (newly saved) profile settings.
    Uses `run_in_app_context` to ensure notifications are sent correctly,
    especially if they involve operations requiring the Flask app context.
    """
    app_instance = current_app._get_current_object() # Get the current Flask app instance.
    user_id = session.get('user_id') # For logging within notification functions.
    log_extra_test = {'user_id': user_id, 'action': 'send_test_notification'}

    if notify_pushover and pushover_user_key and pushover_api_token:
        current_app.logger.info("Dispatching test Pushover notification.", extra=log_extra_test)
        run_in_app_context(
            app_instance,
            send_pushover_notification, # Function to call.
            pushover_user_key,          # Arguments for the function.
            pushover_api_token,
            "Ticket System Test",       # Title of the notification.
            "This is a test notification from your Ticket System profile." # Message body.
        )

    if notify_email and email:
        current_app.logger.info("Dispatching test Email notification.", extra=log_extra_test)
        run_in_app_context(
            app_instance,
            send_email_notification,
            "Ticket System Test Notification", # Subject of the email.
            "This is a test email notification from your Ticket System profile.", # Body of the email.
            email # Recipient email address.
        )

    if notify_apprise and apprise_url:
        current_app.logger.info("Dispatching test Apprise notification.", extra=log_extra_test)
        run_in_app_context(
            app_instance,
            send_apprise_notification,
            apprise_url,
            "Ticket System Test",       # Title for Apprise.
            "This is a test notification via Apprise from your Ticket System profile." # Body for Apprise.
        )


@profile_bp.route('/toggle_theme', methods=['POST'])
@login_required # User must be logged in to change their theme.
def toggle_theme():
    """
    Toggles the user's UI theme (e.g., light/dark) and persists it in the session and database.
    """
    user_id = session.get('user_id')
    username = session.get('username') # For logging.
    current_theme = session.get('theme', 'dark') # Default to 'dark' if not set.
    
    # Determine the new theme.
    new_theme = 'light' if current_theme == 'dark' else 'dark'
    session['theme'] = new_theme # Update theme in the current session immediately.
    
    log_extra_theme = {
        'user_id': user_id, 'username': username,
        'previous_theme': current_theme, 'new_theme': new_theme
    }
    current_app.logger.info("User toggled UI theme.", extra=log_extra_theme)

    try:
        # Persist the new theme preference in the user's database record.
        db_manager.execute_query('UPDATE users SET theme = ? WHERE id = ?', (new_theme, user_id))
        current_app.logger.info(f"User ID {user_id}'s theme preference ('{new_theme}') persisted to database.", extra=log_extra_theme)
    except Exception as e:
        current_app.logger.error(
            f"Error persisting theme preference for user ID {user_id} to database: {e}",
            extra=log_extra_theme, exc_info=True
        )
        # Theme change in session still applies for current session even if DB update fails.
        # Optionally, flash a message to the user about the persistence failure.
        # flash("Could not save your theme preference permanently, but it will apply for this session.", "warning")

    # Redirect back to the page the user was on, or to the main index as a fallback.
    return redirect(request.referrer or url_for('main_bp.index'))
