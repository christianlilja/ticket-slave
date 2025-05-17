from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, current_app
from werkzeug.security import generate_password_hash
from app.db import get_db
from utils.decorators import login_required
from app.notifications_core import send_email_notification, send_pushover_notification, send_apprise_notification
import threading
from utils.context_runner import run_in_app_context


profile_bp = Blueprint('profile_bp', __name__)

@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session.get('user_id')
    username = session.get('username') # Assuming username is in session

    current_app.logger.info(
        "User accessed their profile page",
        extra={'user_id': user_id, 'username': username}
    )

    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            current_app.logger.error(
                "User in session not found in database during profile access",
                extra={'user_id': user_id, 'username': username}
            )
            abort(404)

        if request.method == 'POST':
            log_extra_update = {
                'user_id': user_id,
                'username': username,
            }
            current_app.logger.info("User attempting to update their profile", extra=log_extra_update)
            
            # Grab form data, using .get() with defaults from existing user object
            email = request.form.get('email', user['email'])
            pushover_user_key = request.form.get('pushover_user_key', user['pushover_user_key'])
            pushover_api_token = request.form.get('pushover_api_token', user['pushover_api_token'])
            apprise_url = request.form.get('apprise_url', user['apprise_url'])

            notify_email = 1 if 'notify_email' in request.form else 0
            notify_pushover = 1 if 'notify_pushover' in request.form else 0
            notify_apprise = 1 if 'notify_apprise' in request.form else 0

            new_password = request.form.get('new_password')
            
            errors = {}
            # Validate email format if provided and changed
            if email and email != user['email']:
                # Basic email regex, consider a library for more robust validation
                import re
                if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                    errors['email'] = "Invalid email format."
            
            # Validate password complexity if new password is provided
            if new_password:
                # TODO: Add password complexity rules (e.g., minimum length, character types)
                # Example:
                # if len(new_password) < 8:
                #     errors['new_password'] = "Password must be at least 8 characters long."
                pass # Placeholder for actual complexity checks

            if errors:
                for field, msg in errors.items():
                    flash(msg, 'danger')
                current_app.logger.warning(f"Profile update failed due to validation errors: {errors}", extra=log_extra_update)
                # Re-fetch user for template as the POST might have failed before commit
                # The 'conn' from the outer 'with' block is still open here if validation fails within POST
                # However, to be consistent and ensure fresh data if other logic modified 'user', re-fetch.
                # Or, pass the initially fetched 'user' object if no modifications are expected before this point.
                # For simplicity and safety, let's assume 'user' (fetched at the start of POST) is sufficient here.
                # If 'user' object could be changed by other parts of the POST before validation error, then re-fetch:
                # with get_db() as conn_val_err:
                #    user_for_template_val_err = conn_val_err.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
                # return render_template('profile.html', user=user_for_template_val_err, errors=errors)
                # For now, using the 'user' object fetched at the start of the 'profile' function for the error case.
                return render_template('profile.html', user=user, errors=errors)


            # For logging, summarize changes
            updated_fields_summary = {
                'email_changed': email != user['email'],
                'pushover_user_key_changed': pushover_user_key != user['pushover_user_key'],
                'pushover_api_token_changed': bool(pushover_api_token) and pushover_api_token != user['pushover_api_token'],
                'apprise_url_changed': apprise_url != user['apprise_url'],
                'notify_email': notify_email,
                'notify_pushover': notify_pushover,
                'notify_apprise': notify_apprise,
                'password_changed': bool(new_password)
            }
            log_extra_update['updated_fields_summary'] = updated_fields_summary
            
            try:
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
                current_app.logger.info("User successfully updated their profile", extra=log_extra_update)

                # Optional test notification
                if 'test_notification' in request.form:
                    current_app.logger.info(
                        "User initiated test notifications from profile",
                        extra={
                            **log_extra_update,
                            'test_email_enabled': notify_email,
                            'test_pushover_enabled': notify_pushover,
                            'test_apprise_enabled': notify_apprise
                        }
                    )
                    send_test_notifications(email, pushover_user_key, pushover_api_token, apprise_url,
                                            notify_email, notify_pushover, notify_apprise)
                    flash('Test notification sent (if configured and enabled).', 'info')
                else:
                    flash('Profile updated successfully.', 'success')
                
                return redirect(url_for('profile_bp.profile'))
            except Exception as e:
                current_app.logger.error(
                    "Error updating user profile",
                    extra=log_extra_update,
                    exc_info=True
                )
                flash('An error occurred while updating your profile.', 'danger')


    # Fetch user again in case of GET or failed POST to ensure fresh data for template
    # The 'user' variable from the initial fetch might be stale or the conn closed.
    with get_db() as conn_refresh:
        user_for_template = conn_refresh.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    if not user_for_template:
        # This should ideally not happen if the user was found at the start of the function
        current_app.logger.error(
            "User disappeared from database before template rendering in profile view.",
            extra={'user_id': user_id, 'username': username}
        )
        abort(404) # Or handle more gracefully

    return render_template('profile.html', user=user_for_template)


def send_test_notifications(email, pushover_user_key, pushover_api_token, apprise_url,
                            notify_email, notify_pushover, notify_apprise):
    """Send test notifications in background threads."""
    app = current_app._get_current_object()

    if notify_pushover and pushover_user_key and pushover_api_token:
        run_in_app_context(
            app,
            send_pushover_notification,
            pushover_user_key,
            pushover_api_token,
            "Test",
            "This is a test Pushover notification"
        )

    if notify_email and email:
        run_in_app_context(
            app,
            send_email_notification,
            "Test",
            "This is a test email notification",
            email
        )

    if notify_apprise and apprise_url:
        run_in_app_context(
            app,
            send_apprise_notification,
            apprise_url,
            "Test",
            "This is a test Apprise notification"
        )


@profile_bp.route('/toggle_theme', methods=['POST'])
@login_required
def toggle_theme():
    user_id = session.get('user_id')
    username = session.get('username')
    current_theme = session.get('theme', 'dark') # Default to 'dark' if not set
    new_theme = 'light' if current_theme == 'dark' else 'dark'
    session['theme'] = new_theme
    
    log_extra_theme = {
        'user_id': user_id,
        'username': username,
        'previous_theme': current_theme,
        'new_theme': new_theme
    }
    current_app.logger.info("User toggled UI theme", extra=log_extra_theme)
    # print(f"Theme switched to: {new_theme}") # Can be removed if logging is sufficient

    # Persist theme
    try:
        with get_db() as conn:
            conn.execute('UPDATE users SET theme = ? WHERE id = ?', (new_theme, user_id))
            conn.commit()
        current_app.logger.info("User theme preference persisted to DB", extra=log_extra_theme)
    except Exception as e:
        current_app.logger.error(
            "Error persisting user theme preference to DB",
            extra=log_extra_theme,
            exc_info=True
        )
        # Optionally flash a message to the user, though theme toggle is usually silent on backend error
        # flash('Could not save theme preference.', 'warning')


    return redirect(request.referrer or url_for('main_bp.index'))
