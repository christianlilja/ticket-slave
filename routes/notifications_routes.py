"""
User notification settings routes.

This module defines the Flask Blueprint for routes specifically dedicated
to managing a user's notification preferences, such as email, Pushover,
and Apprise settings.
"""
from flask import Blueprint, request, session, redirect, url_for, flash, render_template, abort, current_app
from utils.decorators import login_required # Ensures only logged-in users can access.
import threading # Used for sending test notifications in a separate thread.
from app.db import db_manager # Global database manager instance.
from app.notifications_core import send_pushover_notification, send_apprise_notification, send_email_notification # Core notification functions.
from utils.context_runner import run_in_app_context # Helper to run functions within app context.
import re # For email validation.

# Define the Blueprint for notification settings routes.
notifications_bp = Blueprint('notifications_bp', __name__)

@notifications_bp.route('/notifications', methods=['GET', 'POST'])
@login_required # User must be logged in to manage their notification settings.
def notifications_view():
    """
    Handles viewing and updating the logged-in user's notification settings.

    GET: Displays the notification settings form populated with the user's current preferences.
    POST: Processes form submissions to update notification settings (email, Pushover, Apprise)
          and optionally sends test notifications.
    """
    user_id = session.get('user_id')
    username = session.get('username') # Primarily for logging.

    # Ensure user_id and username are present in session; otherwise, it's an invalid state.
    if not user_id or not username:
        current_app.logger.error("Access to notifications page without valid session (user_id/username missing).")
        flash("Your session is invalid. Please log in again.", "danger")
        return redirect(url_for('auth_bp.login'))

    log_base_extra = {'user_id': user_id, 'username': username, 'action_area': 'notification_settings'}
    current_app.logger.info("User accessing their notification settings page.", extra=log_base_extra)

    if request.method == 'POST':
        # --- Handle Notification Settings Update Form Submission ---
        current_app.logger.info("User submitted notification settings update form.", extra=log_base_extra)

        # Retrieve form data.
        email = request.form.get('email', '').strip()
        pushover_user_key = request.form.get('pushover_user_key', '').strip()
        pushover_api_token = request.form.get('pushover_api_token', '').strip()
        apprise_url = request.form.get('apprise_url', '').strip()
        # Checkboxes: value is present if checked, absent if not. Convert to 0 or 1 for DB.
        notify_email = 1 if request.form.get('notify_email') else 0
        notify_pushover = 1 if request.form.get('notify_pushover') else 0
        notify_apprise = 1 if request.form.get('notify_apprise') else 0

        errors = {}
        # Validate email format if provided.
        if email and not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            errors['email'] = "Invalid email address format."
        
        # TODO: Add validation for Pushover keys/tokens or Apprise URL format if necessary.

        if errors:
            for field, msg in errors.items(): flash(msg, 'danger')
            current_app.logger.warning(f"Notification settings update for user ID {user_id} failed validation: {errors}", extra=log_base_extra)
            # Fetch current user data again to re-populate form correctly on error.
            user_data_for_form = db_manager.fetchone('SELECT email, pushover_user_key, pushover_api_token, notify_email, notify_pushover, apprise_url, notify_apprise FROM users WHERE id = ?', (user_id,))
            return render_template('notifications.html', user=user_data_for_form or {}, errors=errors)


        try:
            # Update the user's notification settings in the database.
            db_manager.execute_query( # Using execute_query as update might not return rowcount as needed by db_manager.update
                '''UPDATE users
                   SET email = ?, pushover_user_key = ?, pushover_api_token = ?,
                       notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?
                   WHERE id = ?''', # Changed from username to user_id for PK.
                (email, pushover_user_key, pushover_api_token,
                 notify_email, notify_pushover, apprise_url, notify_apprise,
                 user_id)
            )
            # db_manager's methods using `get_database_connection` handle commits.

            log_update_details = {
                **log_base_extra,
                'updated_email': email, 'updated_notify_email': notify_email,
                'updated_pushover_key_present': bool(pushover_user_key),
                'updated_pushover_token_present': bool(pushover_api_token),
                'updated_notify_pushover': notify_pushover,
                'updated_apprise_url_present': bool(apprise_url),
                'updated_notify_apprise': notify_apprise
            }
            current_app.logger.info(f"User ID {user_id} successfully updated their notification settings.", extra=log_update_details)

            # Optional: Send test notifications if requested or by default after saving.
            # This example sends a test if the corresponding "notify" checkbox is checked and relevant keys/URLs are present.
            # This logic is similar to profile.py's test notification.
            app_instance = current_app._get_current_object()
            test_notifications_sent = False

            if notify_pushover and pushover_user_key and pushover_api_token:
                current_app.logger.info(f"Dispatching test Pushover notification for user ID {user_id}.", extra=log_base_extra)
                # Using threading to avoid blocking the request, run_in_app_context handles app context.
                threading.Thread(
                    target=run_in_app_context,
                    args=(app_instance, send_pushover_notification, pushover_user_key, pushover_api_token, "Pushover Test", "Your Pushover notification settings have been updated."),
                    daemon=True # Allows main program to exit even if thread is running.
                ).start()
                test_notifications_sent = True

            if notify_apprise and apprise_url:
                current_app.logger.info(f"Dispatching test Apprise notification for user ID {user_id}.", extra=log_base_extra)
                threading.Thread(
                    target=run_in_app_context,
                    args=(app_instance, send_apprise_notification, apprise_url, "Apprise Test", "Your Apprise notification settings have been updated."),
                    daemon=True
                ).start()
                test_notifications_sent = True
            
            if notify_email and email: # Test email notification
                current_app.logger.info(f"Dispatching test Email notification for user ID {user_id}.", extra=log_base_extra)
                threading.Thread(
                    target=run_in_app_context,
                    args=(app_instance, send_email_notification, "Notification Settings Updated", "Your email notification settings have been updated.", email),
                    daemon=True
                ).start()
                test_notifications_sent = True


            if test_notifications_sent:
                flash('Notification settings updated. Test notification(s) dispatched (if applicable).', 'success')
            else:
                flash('Notification settings updated successfully.', 'success')
            
            # Redirect after successful POST to prevent re-submission on refresh.
            return redirect(url_for('notifications_bp.notifications_view'))
        except Exception as e:
            current_app.logger.error(f"Error updating notification settings for user ID {user_id}: {e}", extra=log_base_extra, exc_info=True)
            flash('Failed to update notification settings due to an unexpected error.', 'danger')
            # Fall through to render the template again, allowing user to see their submitted (but failed) data.
            # For a better UX, pass the submitted form data back to the template.
            user_data_for_form_on_error = {
                'email': email, 'pushover_user_key': pushover_user_key, 'pushover_api_token': pushover_api_token,
                'notify_email': notify_email, 'notify_pushover': notify_pushover,
                'apprise_url': apprise_url, 'notify_apprise': notify_apprise
            }
            return render_template('notifications.html', user=user_data_for_form_on_error, errors={"general": "Update failed."})

    # --- For GET requests or if POST failed and fell through without redirect ---
    try:
        # Fetch the user's current notification settings to populate the form.
        user_settings = db_manager.fetchone('''
            SELECT email, pushover_user_key, pushover_api_token, notify_email, notify_pushover,
                   apprise_url, notify_apprise
            FROM users
            WHERE id = ? 
        ''', (user_id,)) # Fetch by user_id.
        
        if not user_settings:
            # This case should ideally not be reached if user_id from session is valid.
            current_app.logger.error(f"Failed to fetch notification settings: User ID {user_id} not found in database.", extra=log_base_extra)
            flash('Could not load your settings: User not found.', 'danger')
            return redirect(url_for('main_bp.index')) # Redirect to a safe page.
    except Exception as e:
        current_app.logger.error(f"Error fetching notification settings for user ID {user_id}: {e}", extra=log_base_extra, exc_info=True)
        flash('Failed to load your current notification settings.', 'danger')
        user_settings = {} # Provide an empty dict to prevent template errors.

    return render_template('notifications.html', user=user_settings)
