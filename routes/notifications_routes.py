from flask import Blueprint, request, session, redirect, url_for, flash, render_template, abort, current_app
from utils.decorators import login_required
import threading
from app.db import db_manager # Use the db_manager instance
from app.notifications_core import send_pushover_notification, send_apprise_notification
from utils.context_runner import run_in_app_context

notifications_bp = Blueprint('notifications_bp', __name__)

@notifications_bp.route('/notifications', methods=['GET', 'POST'])
@login_required
def notifications_view():
    username = session.get('username')
    if not username:
        abort(401) # Or redirect to login

    if request.method == 'POST':
        email = request.form.get('email', '')
        pushover_user_key = request.form.get('pushover_user_key', '')
        pushover_api_token = request.form.get('pushover_api_token', '')
        apprise_url = request.form.get('apprise_url', '')
        notify_email = 1 if request.form.get('notify_email') else 0
        notify_pushover = 1 if request.form.get('notify_pushover') else 0
        notify_apprise = 1 if request.form.get('notify_apprise') else 0

        try:
            db_manager.update('''
                UPDATE users
                SET email = ?, pushover_user_key = ?, pushover_api_token = ?,
                    notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?
                WHERE username = ?
            ''', (
                email, pushover_user_key, pushover_api_token,
                notify_email, notify_pushover, apprise_url, notify_apprise,
                username
            ))
            # db_manager's update method implies commit through its context manager

            # Optional test push notification
            if notify_pushover and pushover_user_key and pushover_api_token:
                threading.Thread(
                    target=run_in_app_context,
                    args=(send_pushover_notification, pushover_user_key, pushover_api_token, "Pushover Test", "Your Pushover settings have been saved."),
                    daemon=True
                ).start()

            if notify_apprise and apprise_url:
                threading.Thread(
                    target=run_in_app_context,
                    args=(send_apprise_notification, apprise_url, "Apprise Test", "Your Apprise settings have been saved."),
                    daemon=True
                ).start()

            flash('Notification settings updated successfully.', 'success')
            # It's good practice to redirect after a successful POST to prevent re-submission
            return redirect(url_for('notifications_bp.notifications_view')) # Corrected blueprint name
        except Exception as e:
            current_app.logger.error(f"Error updating notification settings for {username}: {e}", exc_info=True)
            flash('Failed to update notification settings.', 'danger')
            # Fall through to render the template again, possibly with old data or error messages

    # For GET request or if POST failed and fell through
    try:
        user = db_manager.fetchone('''
            SELECT email, pushover_user_key, pushover_api_token, notify_email, notify_pushover,
                   apprise_url, notify_apprise
            FROM users
            WHERE username = ?
        ''', (username,))
        if not user:
            # This case should ideally not happen if user is logged in, but good to handle
            flash('User not found.', 'danger')
            return redirect(url_for('main_bp.index')) # Or some other appropriate page
    except Exception as e:
        current_app.logger.error(f"Error fetching notification settings for {username}: {e}", exc_info=True)
        flash('Failed to load notification settings.', 'danger')
        user = {} # Provide an empty dict or default structure for the template

    return render_template('notifications.html', user=user)
