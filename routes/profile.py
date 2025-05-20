from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, current_app
from werkzeug.security import generate_password_hash
from app.db import db_manager # Use the db_manager instance
from utils.decorators import login_required
from app.notifications_core import send_email_notification, send_pushover_notification, send_apprise_notification
# import threading # Not directly used here, run_in_app_context handles threading if needed
from utils.context_runner import run_in_app_context


profile_bp = Blueprint('profile_bp', __name__)

@profile_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session.get('user_id')
    username = session.get('username')

    current_app.logger.info(
        "User accessed their profile page",
        extra={'user_id': user_id, 'username': username}
    )

    # Fetch initial user data for GET request or to populate form defaults
    # This user object will be used if POST fails validation or for GET.
    user = db_manager.fetchone('SELECT * FROM users WHERE id = ?', (user_id,))
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
        
        email = request.form.get('email', user['email'])
        pushover_user_key = request.form.get('pushover_user_key', user['pushover_user_key'])
        pushover_api_token = request.form.get('pushover_api_token', user['pushover_api_token'])
        apprise_url = request.form.get('apprise_url', user['apprise_url'])
        notify_email = 1 if 'notify_email' in request.form else 0
        notify_pushover = 1 if 'notify_pushover' in request.form else 0
        notify_apprise = 1 if 'notify_apprise' in request.form else 0
        new_password = request.form.get('new_password')
        
        errors = {}
        if email and email != user['email']:
            import re
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                errors['email'] = "Invalid email format."
        
        if new_password:
            # Add password complexity checks here if desired
            pass

        if errors:
            for field, msg in errors.items():
                flash(msg, 'danger')
            current_app.logger.warning(f"Profile update failed due to validation errors: {errors}", extra=log_extra_update)
            # Render with the initially fetched 'user' data and errors
            return render_template('profile.html', user=user, errors=errors)

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
            db_manager.execute_query( # Using execute_query as update might not return rowcount as needed by db_manager.update
                '''UPDATE users
                   SET email = ?, pushover_user_key = ?, pushover_api_token = ?,
                       notify_email = ?, notify_pushover = ?, apprise_url = ?, notify_apprise = ?
                   WHERE id = ?''',
                (email, pushover_user_key, pushover_api_token,
                 notify_email, notify_pushover, apprise_url, notify_apprise, user_id)
            )

            if new_password:
                hashed_password = generate_password_hash(new_password)
                db_manager.execute_query('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))
            
            # Commits are handled by db_manager's context manager
            current_app.logger.info("User successfully updated their profile", extra=log_extra_update)

            if 'test_notification' in request.form:
                current_app.logger.info(
                    "User initiated test notifications from profile",
                    extra={**log_extra_update, 'test_email_enabled': notify_email,
                           'test_pushover_enabled': notify_pushover, 'test_apprise_enabled': notify_apprise}
                )
                send_test_notifications(email, pushover_user_key, pushover_api_token, apprise_url,
                                        notify_email, notify_pushover, notify_apprise)
                flash('Test notification sent (if configured and enabled).', 'info')
            else:
                flash('Profile updated successfully.', 'success')
            
            return redirect(url_for('profile_bp.profile'))
        except Exception as e:
            current_app.logger.error(
                "Error updating user profile", extra=log_extra_update, exc_info=True
            )
            flash('An error occurred while updating your profile.', 'danger')
            # If error, render with initially fetched 'user' data
            return render_template('profile.html', user=user, errors={"general": "Update failed."})


    # For GET request, 'user' is already fetched.
    return render_template('profile.html', user=user)


def send_test_notifications(email, pushover_user_key, pushover_api_token, apprise_url,
                            notify_email, notify_pushover, notify_apprise):
    """Send test notifications. run_in_app_context handles threading if necessary."""
    app = current_app._get_current_object() # Ensure we have the app object for context

    if notify_pushover and pushover_user_key and pushover_api_token:
        run_in_app_context(
            app, # Pass the app object
            send_pushover_notification,
            pushover_user_key,
            pushover_api_token,
            "Test",
            "This is a test Pushover notification"
        )

    if notify_email and email:
        run_in_app_context(
            app, # Pass the app object
            send_email_notification,
            "Test",
            "This is a test email notification",
            email
        )

    if notify_apprise and apprise_url:
        run_in_app_context(
            app, # Pass the app object
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
    current_theme = session.get('theme', 'dark')
    new_theme = 'light' if current_theme == 'dark' else 'dark'
    session['theme'] = new_theme
    
    log_extra_theme = {
        'user_id': user_id, 'username': username,
        'previous_theme': current_theme, 'new_theme': new_theme
    }
    current_app.logger.info("User toggled UI theme", extra=log_extra_theme)

    try:
        # Persist theme using db_manager
        db_manager.execute_query('UPDATE users SET theme = ? WHERE id = ?', (new_theme, user_id))
        # Commits handled by db_manager
        current_app.logger.info("User theme preference persisted to DB", extra=log_extra_theme)
    except Exception as e:
        current_app.logger.error(
            "Error persisting user theme preference to DB", extra=log_extra_theme, exc_info=True
        )

    return redirect(request.referrer or url_for('main_bp.index'))
