from flask import Blueprint, request, session, redirect, url_for, flash, render_template
#from flask_login import login_required
from utils.decorators import login_required
import threading
from db import get_db
from notifications import send_pushover_notification, send_apprise_notification  # adjust path as needed

notifications_bp = Blueprint('notifications_bp', __name__)

@notifications_bp.route('/notifications', methods=['GET', 'POST'])
@login_required
def notifications_view():
    username = session.get('username')
    if not username:
        abort(401)

    with get_db() as conn:
        user = conn.execute('''
            SELECT email, pushover_user_key, pushover_api_token, notify_email, notify_pushover,
                   apprise_url, notify_apprise
            FROM users
            WHERE username = ?
        ''', (username,)).fetchone()

        if request.method == 'POST':
            email = request.form.get('email', '')
            pushover_user_key = request.form.get('pushover_user_key', '')
            pushover_api_token = request.form.get('pushover_api_token', '')
            apprise_url = request.form.get('apprise_url', '')
            notify_email = 1 if request.form.get('notify_email') else 0
            notify_pushover = 1 if request.form.get('notify_pushover') else 0
            notify_apprise = 1 if request.form.get('notify_apprise') else 0

            conn.execute('''
                UPDATE users 
                SET email = ?, pushover_user_key = ?, pushover_api_token = ?, 
                    notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?
                WHERE username = ?
            ''', (
                email, pushover_user_key, pushover_api_token,
                notify_email, notify_pushover, apprise_url, notify_apprise,
                username
            ))
            conn.commit()

            # Optional test push notification
            if notify_pushover and pushover_user_key and pushover_api_token:
                threading.Thread(
                    target=send_pushover_notification,
                    args=(pushover_user_key, pushover_api_token, "Pushover Test", "Your Pushover settings have been saved."),
                    daemon=True
                ).start()

            if notify_apprise and apprise_url:
                threading.Thread(
                    target=send_apprise_notification,
                    args=(apprise_url, "Apprise Test", "Your Apprise settings have been saved."),
                    daemon=True
                ).start()

            flash('Notification settings updated successfully.', 'success')
            return redirect(url_for('notifications.notifications_view'))

    return render_template('notifications.html', user=user)
