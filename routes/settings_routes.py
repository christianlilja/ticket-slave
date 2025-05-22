from flask import Blueprint, render_template, request, session, flash, jsonify, current_app, redirect, url_for
from utils.decorators import login_required, admin_required
from app.db import db_manager # Use the db_manager instance
import smtplib
import re # For email validation

settings_bp = Blueprint('settings_bp', __name__)

def get_all_settings():
    """Helper function to fetch all settings using db_manager."""
    rows = db_manager.fetchall("SELECT key, value FROM settings")
    return {row['key']: row['value'] for row in rows}

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def system_settings():
    user_id = session.get('user_id')
    username = session.get('username')
    log_base_extra = {'user_id': user_id, 'username': username}

    if request.method == 'POST':
        action = request.form.get('action')
        current_app.logger.info(f"Admin action in settings: {action}", extra=log_base_extra)

        if action == 'save_settings':
            allow_registration = '1' if 'allow_registration' in request.form else '0'
            enable_api = '1' if 'enable_api' in request.form else '0'
            smtp_server_form = request.form.get('smtp_server', '')
            smtp_port_form = request.form.get('smtp_port', '25')
            smtp_from_email_form = request.form.get('smtp_from_email', '')
            smtp_username_form = request.form.get('smtp_username', '')
            smtp_password_form = request.form.get('smtp_password', '') # Avoid logging
            smtp_use_tls_form = '1' if 'smtp_use_tls' in request.form else '0'
    
            errors = {}
            if smtp_port_form:
                try:
                    int(smtp_port_form)
                except ValueError:
                    errors['smtp_port'] = "SMTP Port must be a valid number."
            else:
                smtp_port_form = '25'
    
            if smtp_from_email_form and not re.match(r"[^@]+@[^@]+\.[^@]+", smtp_from_email_form):
                errors['smtp_from_email'] = "Invalid 'From Email' format."
            
            if errors:
                for field, msg in errors.items():
                    flash(msg, 'danger')
                current_app.logger.warning(f"Settings update failed: {errors}", extra=log_base_extra)
                current_settings = get_all_settings() # Reload for template
                return render_template('settings.html', settings=current_settings, errors=errors)
    
            settings_to_update = {
                'allow_registration': allow_registration,
                'enable_api': enable_api,
                'smtp_server': smtp_server_form,
                'smtp_port': smtp_port_form,
                'smtp_from_email': smtp_from_email_form,
                'smtp_username': smtp_username_form,
                'smtp_use_tls': smtp_use_tls_form
            }
            # Only update password if a new one is provided
            if smtp_password_form:
                settings_to_update['smtp_password'] = smtp_password_form

            try:
                for key, value in settings_to_update.items():
                    # Assuming db_manager.update can handle this, or use execute_query
                    # For simplicity, using execute_query for direct UPDATE
                    db_manager.execute_query("UPDATE settings SET value = ? WHERE key = ?", (value, key))
                
                # Create a loggable version without the actual password
                loggable_settings = settings_to_update.copy()
                if 'smtp_password' in loggable_settings:
                    loggable_settings['smtp_password_changed'] = 'yes'
                    del loggable_settings['smtp_password']
                else:
                    loggable_settings['smtp_password_changed'] = 'no'

                current_app.logger.info("System settings updated", extra={**log_base_extra, 'updated_settings': loggable_settings})
                flash('Settings updated.', 'success')
            except Exception as e:
                current_app.logger.error(f"Error saving settings: {e}", extra=log_base_extra, exc_info=True)
                flash('An error occurred while saving settings.', 'danger')

            return redirect(url_for('settings_bp.system_settings')) # Redirect to refresh

        elif action == 'test_email': # This is part of the main form, not AJAX here
            current_settings = get_all_settings()
            smtp_server = current_settings.get('smtp_server')
            smtp_port = int(current_settings.get('smtp_port', 25))
            smtp_user = current_settings.get('smtp_username')
            smtp_password = current_settings.get('smtp_password')
            use_tls = current_settings.get('smtp_use_tls') == '1'

            if not smtp_server:
                flash("SMTP server not configured.", "warning")
            else:
                try:
                    with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                        if use_tls:
                            server.starttls()
                        if smtp_user and smtp_password:
                            server.login(smtp_user, smtp_password)
                        server.ehlo_or_helo_if_needed() # Test connection
                    flash("SMTP connection successful!", "success")
                    current_app.logger.info("SMTP test (from form) successful.", extra=log_base_extra)
                except Exception as e:
                    flash(f"SMTP connection failed: {e}", "danger")
                    current_app.logger.error(f"SMTP test (from form) failed: {e}", extra=log_base_extra, exc_info=True)
            # Fall through to render the page again with current settings
    
    # For GET request or after POST action that doesn't redirect
    current_settings = get_all_settings()
    if request.method == "GET":
         current_app.logger.info("Admin accessed system settings page", extra=log_base_extra)
    return render_template('settings.html', settings=current_settings)


@settings_bp.route('/settings/test-email', methods=['POST']) # This is the AJAX route
@login_required
@admin_required
def test_email_settings_ajax(): # Renamed to avoid conflict
    user_id = session.get('user_id')
    username = session.get('username')
    log_base_extra = {'user_id': user_id, 'username': username, 'test_type': 'ajax'}
    current_app.logger.info("Admin initiated AJAX SMTP test", extra=log_base_extra)
    
    # Fetch current settings directly for the test
    current_settings = get_all_settings()
    smtp_server = current_settings.get('smtp_server')
    smtp_port_str = current_settings.get('smtp_port', '587') # Default to 587 for AJAX
    smtp_user = current_settings.get('smtp_username')
    smtp_password = current_settings.get('smtp_password')
    use_tls = current_settings.get('smtp_use_tls') == '1' # Check current TLS setting

    if not smtp_server:
        current_app.logger.warning("AJAX SMTP test: Server not configured", extra=log_base_extra)
        return jsonify({'message': 'SMTP server not configured.', 'category': 'danger'}), 400

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        current_app.logger.warning(f"AJAX SMTP test: Invalid port '{smtp_port_str}'", extra=log_base_extra)
        return jsonify({'message': f"Invalid SMTP port: {smtp_port_str}", 'category': 'danger'}), 400

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            if use_tls: # Use the configured TLS setting
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.ehlo_or_helo_if_needed()
        
        current_app.logger.info("AJAX SMTP test successful", extra=log_base_extra)
        return jsonify({'message': 'SMTP connection successful.', 'category': 'success'}), 200

    except Exception as e:
        error_details = {**log_base_extra, 'smtp_server': smtp_server, 'smtp_port': smtp_port, 'error': str(e)}
        current_app.logger.error("AJAX SMTP test failed", extra=error_details, exc_info=True)
        return jsonify({'message': f'SMTP test failed: {str(e)}', 'category': 'danger'}), 500