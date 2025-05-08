from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash
from db import get_db
from utils.decorators import login_required
from notifications import send_email_notification, send_pushover_notification, send_apprise_notification
import threading

profile_bp = Blueprint('profile_bp', __name__)

@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session.get('user_id')

    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            abort(404)

        if request.method == 'POST':
            # Grab form data
            email = request.form['email']
            pushover_user_key = request.form['pushover_user_key']
            pushover_api_token = request.form['pushover_api_token']
            apprise_url = request.form['apprise_url']

            notify_email = 1 if 'notify_email' in request.form else 0
            notify_pushover = 1 if 'notify_pushover' in request.form else 0
            notify_apprise = 1 if 'notify_apprise' in request.form else 0

            new_password = request.form.get('new_password')

            # Update user profile
            conn.execute(
                '''UPDATE users
                   SET email = ?, pushover_user_key = ?, pushover_api_token = ?,
                       notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?
                   WHERE id = ?''',
                (email, pushover_user_key, pushover_api_token,
                 notify_email, notify_pushover, apprise_url, notify_apprise, user_id)
            )

            # Update password if provided
            if new_password:
                hashed_password = generate_password_hash(new_password)
                conn.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))

            conn.commit()

            # Optional test notification
            if 'test_notification' in request.form:
                send_test_notifications(email, pushover_user_key, pushover_api_token, apprise_url,
                                        notify_email, notify_pushover, notify_apprise)
                flash('Test notification sent.', 'info')
            else:
                flash('Profile updated successfully.', 'success')

            return redirect(url_for('profile_bp.profile'))

    return render_template('profile.html', user=user)


def send_test_notifications(email, pushover_user_key, pushover_api_token, apprise_url,
                            notify_email, notify_pushover, notify_apprise):
    """Send test notifications in background threads."""
    if notify_pushover and pushover_user_key and pushover_api_token:
        threading.Thread(
            target=send_pushover_notification,
            args=(pushover_user_key, pushover_api_token, "Test", "This is a test Pushover notification"),
            daemon=True
        ).start()

    if notify_email and email:
        threading.Thread(
            target=send_email_notification,
            args=(email, "Test", "This is a test email notification"),
            daemon=True
        ).start()

    if notify_apprise and apprise_url:
        threading.Thread(
            target=send_apprise_notification,
            args=(apprise_url, "Test", "This is a test Apprise notification"),
            daemon=True
        ).start()


@profile_bp.route('/toggle_theme', methods=['POST'])
@login_required
def toggle_theme():
    current_theme = session.get('theme', 'dark')
    new_theme = 'light' if current_theme == 'dark' else 'dark'
    session['theme'] = new_theme
    print(f"Theme switched to: {new_theme}")

    # Persist theme
    user_id = session.get('user_id')
    with get_db() as conn:
        conn.execute('UPDATE users SET theme = ? WHERE id = ?', (new_theme, user_id))
        conn.commit()

    return redirect(request.referrer or url_for('main_bp.index'))
