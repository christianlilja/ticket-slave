from flask import Blueprint, render_template, request, session, flash, jsonify, current_app
from utils.decorators import login_required, admin_required
from app.db import get_db
import smtplib

settings_bp = Blueprint('settings_bp', __name__)

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def system_settings():
    user_id = session.get('user_id')
    username = session.get('username')

    current_app.logger.info(
        "Admin accessed system settings page",
        extra={'user_id': user_id, 'username': username}
    )

    with get_db() as conn:
        cur = conn.cursor()

        if request.method == 'POST':
            action = request.form.get('action')

            if action == 'save_settings':
                # Log attempt to save settings
                current_app.logger.info(
                    "Admin attempting to save system settings",
                    extra={'user_id': user_id, 'username': username}
                )
                allow_registration = 1 if 'allow_registration' in request.form else 0
                enable_api = 1 if 'enable_api' in request.form else 0
                smtp_server = request.form.get('smtp_server', '')
                smtp_port = request.form.get('smtp_port', '25')
                smtp_from_email = request.form.get('smtp_from_email', '')
                smtp_username = request.form.get('smtp_username', '')
                smtp_password = request.form.get('smtp_password', '') # Avoid logging this directly
                smtp_use_tls = 1 if 'smtp_use_tls' in request.form else 0
    
                errors = {}
                # Validate smtp_port
                if smtp_port:
                    try:
                        int(smtp_port) # Check if it's a valid integer
                    except ValueError:
                        errors['smtp_port'] = "SMTP Port must be a valid number."
                else: # Default if empty, or handle as error if required
                    smtp_port = '25' # Or flash error if it must be provided
    
                # Validate smtp_from_email
                if smtp_from_email:
                    import re
                    if not re.match(r"[^@]+@[^@]+\.[^@]+", smtp_from_email):
                        errors['smtp_from_email'] = "Invalid 'From Email' format."
                
                if errors:
                    for field, msg in errors.items():
                        flash(msg, 'danger')
                    # Log validation errors
                    current_app.logger.warning(
                        f"Admin settings update failed due to validation errors: {errors}",
                        extra={'user_id': user_id, 'username': username}
                    )
                    # Need to reload settings for the template
                    settings_dict_error = {
                        s_row['key']: s_row['value']
                        for s_row in cur.execute("SELECT key, value FROM settings").fetchall()
                    }
                    return render_template('settings.html', settings=settings_dict_error, errors=errors)
    
                # For logging, create a dictionary of settings being changed, excluding sensitive ones
                changed_settings_log = {
                    'allow_registration': allow_registration,
                    'enable_api': enable_api,
                    'smtp_server': smtp_server,
                    'smtp_port': smtp_port,
                    'smtp_from_email': smtp_from_email,
                    'smtp_username': smtp_username,
                    'smtp_password_changed': 'yes' if smtp_password else 'no', # Don't log the password itself
                    'smtp_use_tls': smtp_use_tls
                }

                cur.execute("UPDATE settings SET value = ? WHERE key = 'allow_registration'", (allow_registration,))
                cur.execute("UPDATE settings SET value = ? WHERE key = 'enable_api'", (enable_api,))
                cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_server'", (smtp_server,))
                cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_port'", (smtp_port,))
                cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_from_email'", (smtp_from_email,))
                cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_username'", (smtp_username,))
                if smtp_password: # Only update password if a new one is provided
                    cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_password'", (smtp_password,))
                cur.execute("UPDATE settings SET value = ? WHERE key = 'smtp_use_tls'", (smtp_use_tls,))
                conn.commit()
                
                current_app.logger.info(
                    "Admin successfully updated system settings",
                    extra={
                        'user_id': user_id,
                        'username': username,
                        'updated_settings': changed_settings_log
                    }
                )
                flash('Settings updated.', 'success')

            elif action == 'test_email': # This action seems to be part of the main settings form, not the separate AJAX route
                current_app.logger.info(
                    "Admin initiated SMTP test from settings page",
                    extra={'user_id': user_id, 'username': username}
                )
                cur.execute("SELECT key, value FROM settings")
                settings = {row['key']: row['value'] for row in cur.fetchall()}

                smtp_server = settings.get('smtp_server')
                smtp_port = int(settings.get('smtp_port', 25))
                smtp_user = settings.get('smtp_username')
                smtp_password = settings.get('smtp_password')
                use_tls = settings.get('smtp_use_tls') == '1'

                try:
                    with smtplib.SMTP(smtp_server, smtp_port, timeout=5) as server:
                        if use_tls:
                            server.starttls()
                        if smtp_user and smtp_password:
                            server.login(smtp_user, smtp_password)
                    current_app.logger.info(
                        "SMTP test from settings page successful",
                        extra={'user_id': user_id, 'username': username, 'smtp_server': smtp_server, 'smtp_port': smtp_port}
                    )
                    flash("SMTP connection successful!", "success")
                except Exception as e:
                    current_app.logger.error(
                        "SMTP test from settings page failed",
                        extra={
                            'user_id': user_id,
                            'username': username,
                            'smtp_server': smtp_server,
                            'smtp_port': smtp_port,
                            'error': str(e)
                        },
                        exc_info=True # Include stack trace
                    )
                    flash(f"SMTP connection failed: {e}", "danger")

        # Load current settings for display
        settings_dict = {
            row['key']: row['value']
            for row in cur.execute("SELECT key, value FROM settings").fetchall()
        }

    return render_template('settings.html', settings=settings_dict)

@settings_bp.route('/settings/test-email', methods=['POST'])
@login_required
@admin_required
def test_email_settings():
    user_id = session.get('user_id')
    username = session.get('username')
    current_app.logger.info(
        "Admin initiated AJAX SMTP test",
        extra={'user_id': user_id, 'username': username}
    )
    try:
        with get_db() as conn:
            settings = {
                row['key']: row['value']
                for row in conn.execute("SELECT key, value FROM settings").fetchall()
            }

        smtp_server = settings.get('smtp_server')
        smtp_port = int(settings.get('smtp_port', 587)) # Default to 587 for AJAX, common for TLS
        smtp_user = settings.get('smtp_username')
        smtp_password = settings.get('smtp_password') # Avoid logging this

        if not smtp_server:
            current_app.logger.warning(
                "AJAX SMTP test failed: SMTP server not configured",
                 extra={'user_id': user_id, 'username': username}
            )
            raise Exception("SMTP server not configured")

        # Attempt to connect
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            # For AJAX test, let's assume TLS if user/pass is present, common practice
            if smtp_user and smtp_password:
                server.starttls()
                server.login(smtp_user, smtp_password)
            # If no user/pass, it might be an open relay or just a connection test
            # Some servers might require EHLO/HELO even for basic connection test
            server.ehlo_or_helo_if_needed()


        current_app.logger.info(
            "AJAX SMTP test successful",
            extra={
                'user_id': user_id,
                'username': username,
                'smtp_server': smtp_server,
                'smtp_port': smtp_port
            }
        )
        return jsonify({'message': 'SMTP connection successful.', 'category': 'success'}), 200

    except Exception as e:
        current_app.logger.error(
            "AJAX SMTP test failed",
            extra={
                'user_id': user_id,
                'username': username,
                'smtp_server': smtp_server,
                'smtp_port': smtp_port if 'smtp_port' in locals() else 'N/A', # smtp_port might not be defined if smtp_server is None
                'error': str(e)
            },
            exc_info=True # Include stack trace
        )
        return jsonify({'message': f'SMTP test failed: {str(e)}', 'category': 'danger'}), 500