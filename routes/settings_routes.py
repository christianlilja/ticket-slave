"""
Application settings management routes for administrators.

This module defines the Flask Blueprint for administrator-only routes
related to managing system-wide application settings, such as registration
options, API enablement, and SMTP configuration for email notifications.
"""
from flask import Blueprint, render_template, request, session, flash, jsonify, current_app, redirect, url_for
from utils.decorators import login_required, admin_required # Ensure only logged-in admins can access.
from app.db import db_manager # Global database manager instance.
import smtplib # For testing SMTP connections.
import re # For regular expression matching, e.g., email validation.

# Define the Blueprint for settings routes.
settings_bp = Blueprint('settings_bp', __name__)

def get_all_settings():
    """
    Helper function to fetch all current settings from the database.

    Returns:
        dict: A dictionary where keys are setting names and values are their
              corresponding values from the 'settings' table.
    """
    try:
        rows = db_manager.fetchall("SELECT key, value FROM settings")
        return {row['key']: row['value'] for row in rows}
    except Exception as e:
        current_app.logger.error(f"Failed to fetch all settings from database: {e}", exc_info=True)
        return {} # Return empty dict on error to prevent crashes.

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required # User must be logged in.
@admin_required # User must be an administrator.
def system_settings():
    """
    Handles viewing and updating system-wide application settings.
    Also includes functionality to test SMTP settings via a form action.

    GET: Displays the settings form populated with current values.
    POST: Processes form submissions to save settings or test SMTP connection.
    """
    user_id = session.get('user_id')
    username = session.get('username') # For logging.
    log_base_extra = {'user_id': user_id, 'username': username, 'action_area': 'system_settings'}

    if request.method == 'POST':
        action = request.form.get('action') # Hidden field to determine POST action.
        current_app.logger.info(f"Admin performing settings action: '{action}'.", extra=log_base_extra)

        if action == 'save_settings':
            # --- Handle Save Settings Form Submission ---
            # Retrieve settings from the form. Checkboxes provide '1' if checked, '0' otherwise.
            allow_registration = '1' if 'allow_registration' in request.form else '0'
            enable_api = '1' if 'enable_api' in request.form else '0'
            smtp_server_form = request.form.get('smtp_server', '').strip()
            smtp_port_form = request.form.get('smtp_port', '25').strip() # Default to '25' if empty.
            smtp_from_email_form = request.form.get('smtp_from_email', '').strip()
            smtp_username_form = request.form.get('smtp_username', '').strip()
            smtp_password_form = request.form.get('smtp_password', '') # Password field, not stripped to preserve spaces if intended.
            smtp_use_tls_form = '1' if 'smtp_use_tls' in request.form else '0'
    
            errors = {} # Dictionary for validation errors.
            # Validate SMTP port.
            if smtp_port_form:
                try:
                    int(smtp_port_form) # Check if it's a valid integer.
                except ValueError:
                    errors['smtp_port'] = "SMTP Port must be a valid number (e.g., 25, 587, 465)."
            else: # If empty, default to '25' (though form might provide default).
                smtp_port_form = '25' 
    
            # Validate 'From Email' format if provided.
            if smtp_from_email_form and not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", smtp_from_email_form):
                errors['smtp_from_email'] = "Invalid 'From Email' address format."
            
            if errors:
                for field, msg in errors.items(): flash(msg, 'danger')
                current_app.logger.warning(f"System settings update failed due to validation errors: {errors}", extra=log_base_extra)
                current_settings = get_all_settings() # Reload current settings to display with errors.
                return render_template('settings.html', settings=current_settings, errors=errors)
    
            # Prepare settings dictionary for database update.
            settings_to_update = {
                'allow_registration': allow_registration,
                'enable_api': enable_api,
                'smtp_server': smtp_server_form,
                'smtp_port': smtp_port_form,
                'smtp_from_email': smtp_from_email_form,
                'smtp_username': smtp_username_form,
                'smtp_use_tls': smtp_use_tls_form
            }
            # Only update SMTP password in the database if a new one is provided in the form.
            # This prevents overwriting an existing password with an empty string if the field is left blank.
            if smtp_password_form: # Check if the password field was filled.
                settings_to_update['smtp_password'] = smtp_password_form
            # If not filled, the existing 'smtp_password' in the DB remains unchanged.

            try:
                for key, value in settings_to_update.items():
                    # Update each setting in the database.
                    # Assumes 'key' is PRIMARY KEY in 'settings' table.
                    # Using an UPSERT-like logic: update if exists, or insert if not (though settings should exist from defaults).
                    # A more robust way might be to check existence first or use specific UPSERT SQL.
                    # For simplicity, assuming all keys exist and we are just updating values.
                    db_manager.execute_query("UPDATE settings SET value = ? WHERE key = ?", (value, key))
                
                # Create a loggable version of settings (omitting actual password).
                loggable_settings_summary = {k: v for k, v in settings_to_update.items() if k != 'smtp_password'}
                loggable_settings_summary['smtp_password_changed'] = 'yes' if smtp_password_form else 'no'

                current_app.logger.info("System settings updated successfully by admin.", extra={**log_base_extra, 'updated_settings_summary': loggable_settings_summary})
                flash('System settings updated successfully.', 'success')
            except Exception as e:
                current_app.logger.error(f"Error saving system settings to database: {e}", extra=log_base_extra, exc_info=True)
                flash('An unexpected error occurred while saving settings. Please try again.', 'danger')

            return redirect(url_for('settings_bp.system_settings')) # Redirect to refresh the page with updated settings.

        elif action == 'test_email':
            # --- Handle Test SMTP (from main form button) ---
            # This action uses the *currently saved* settings from the database for the test.
            current_settings = get_all_settings()
            smtp_server = current_settings.get('smtp_server')
            smtp_port_str = current_settings.get('smtp_port', '25') # Default to 25 if not set.
            smtp_user = current_settings.get('smtp_username')
            smtp_password = current_settings.get('smtp_password')
            use_tls = current_settings.get('smtp_use_tls') == '1'
            from_email = current_settings.get('smtp_from_email') # Needed for sending a test email.

            log_smtp_test_extra = {**log_base_extra, 'test_type': 'form_button'}

            if not smtp_server or not from_email: # From email is also essential for a meaningful test.
                flash("SMTP Server and From Email must be configured to send a test email.", "warning")
                current_app.logger.warning("SMTP test (form button) skipped: Server or From Email not configured.", extra=log_smtp_test_extra)
            else:
                try:
                    smtp_port = int(smtp_port_str)
                    with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                        if use_tls:
                            server.starttls()
                        if smtp_user and smtp_password: # Login only if credentials are provided.
                            server.login(smtp_user, smtp_password)
                        # Send a simple test email to the configured 'from_email' address.
                        # This also implicitly tests if the 'from_email' is valid for the server.
                        server.sendmail(from_email, [from_email], f"Subject: Ticket System SMTP Test\n\nThis is a test email from your Ticket System settings page.")
                    flash("SMTP connection and test email sent successfully to configured 'From Email'!", "success")
                    current_app.logger.info("SMTP test (form button) and email send successful.", extra=log_smtp_test_extra)
                except ValueError:
                     flash(f"Invalid SMTP port configured: '{smtp_port_str}'. Please enter a valid number.", "danger")
                     current_app.logger.error(f"SMTP test (form button) failed: Invalid port '{smtp_port_str}'.", extra=log_smtp_test_extra)
                except Exception as e:
                    flash(f"SMTP connection or test email send failed: {e}", "danger")
                    current_app.logger.error(f"SMTP test (form button) or email send failed: {e}", extra=log_smtp_test_extra, exc_info=True)
            # Fall through to render the page again, showing current settings and flash messages.
    
    # For GET requests, or after a POST action that doesn't redirect (like the form-based SMTP test).
    current_settings = get_all_settings()
    if request.method == "GET":
         current_app.logger.info("Admin accessed the system settings page.", extra=log_base_extra)
    return render_template('settings.html', settings=current_settings)


@settings_bp.route('/settings/test-email-ajax', methods=['POST']) # Changed route for clarity
@login_required
@admin_required
def test_email_settings_ajax():
    """
    Handles an AJAX request to test SMTP connection settings.
    This is typically triggered by a separate "Test Connection" button for SMTP
    that doesn't submit the whole settings form.
    It uses the *currently saved* settings from the database.
    """
    user_id = session.get('user_id')
    username = session.get('username')
    log_ajax_test_extra = {'user_id': user_id, 'username': username, 'test_type': 'ajax_connection_only'}
    current_app.logger.info("Admin initiated AJAX SMTP connection test.", extra=log_ajax_test_extra)
    
    current_settings = get_all_settings() # Fetch current settings from DB.
    smtp_server = current_settings.get('smtp_server')
    smtp_port_str = current_settings.get('smtp_port', '587') # Default to 587 for AJAX test if not set.
    smtp_user = current_settings.get('smtp_username')
    smtp_password = current_settings.get('smtp_password')
    use_tls = current_settings.get('smtp_use_tls') == '1'

    if not smtp_server:
        current_app.logger.warning("AJAX SMTP test failed: SMTP server not configured.", extra=log_ajax_test_extra)
        return jsonify({'message': 'SMTP server is not configured in settings.', 'category': 'danger'}), 400

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        current_app.logger.warning(f"AJAX SMTP test failed: Invalid SMTP port '{smtp_port_str}'.", extra=log_ajax_test_extra)
        return jsonify({'message': f"Invalid SMTP port: '{smtp_port_str}'. Please enter a valid number.", 'category': 'danger'}), 400

    try:
        # Attempt to connect, optionally use TLS, and login if credentials provided.
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server: # 10-second timeout.
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password: # Login only if both username and password are set.
                server.login(smtp_user, smtp_password)
            server.ehlo_or_helo_if_needed() # Basic command to confirm server is responsive.
        
        current_app.logger.info("AJAX SMTP connection test successful.", extra=log_ajax_test_extra)
        return jsonify({'message': 'SMTP connection test successful!', 'category': 'success'}), 200
    except smtplib.SMTPAuthenticationError as auth_e:
        current_app.logger.error(f"AJAX SMTP test failed: Authentication error - {auth_e}", extra=log_ajax_test_extra)
        return jsonify({'message': f'SMTP Authentication Failed: {str(auth_e)}. Check username/password.', 'category': 'danger'}), 500
    except smtplib.SMTPException as smtp_e: # Catches various SMTP errors (conn, helo, etc.)
        current_app.logger.error(f"AJAX SMTP test failed: SMTP error - {smtp_e}", extra=log_ajax_test_extra, exc_info=True)
        return jsonify({'message': f'SMTP Connection Error: {str(smtp_e)}', 'category': 'danger'}), 500
    except ConnectionRefusedError as conn_ref_e: # More specific network error
        current_app.logger.error(f"AJAX SMTP test failed: Connection refused - {conn_ref_e}", extra=log_ajax_test_extra)
        return jsonify({'message': f'SMTP Connection Refused: {str(conn_ref_e)}. Check server/port and firewall.', 'category': 'danger'}), 500
    except TimeoutError as timeout_e: # Socket timeout
        current_app.logger.error(f"AJAX SMTP test failed: Timeout - {timeout_e}", extra=log_ajax_test_extra)
        return jsonify({'message': f'SMTP Connection Timed Out: {str(timeout_e)}. Check server responsiveness.', 'category': 'danger'}), 500
    except Exception as e: # Catch-all for other unexpected errors.
        error_details_log = {**log_ajax_test_extra, 'smtp_server': smtp_server, 'smtp_port': smtp_port, 'error_type': type(e).__name__, 'error_message': str(e)}
        current_app.logger.error("AJAX SMTP test failed due to an unexpected error.", extra=error_details_log, exc_info=True)
        return jsonify({'message': f'An unexpected error occurred during SMTP test: {str(e)}', 'category': 'danger'}), 500