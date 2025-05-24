"""
Core logic for sending notifications via various channels.

This module provides functions to send notifications through Email, Pushover,
and Apprise. It also includes a central orchestrator function `notify_assigned_user`
that determines which notifications to send based on user preferences and specific
ticket events. SMTP connection testing functionality is also included.
"""
import smtplib
from email.mime.text import MIMEText # For creating email messages.
import requests # For making HTTP requests (e.g., to Pushover API).
from apprise import Apprise # Multi-platform notification library.
from app.db import db_manager # Global database manager instance.
from utils.context_runner import run_in_app_context # For running tasks in app context (background threads).
from flask import current_app # To access Flask app's logger and config.

def send_email_notification(subject, body, to_email):
    """
    Sends an email notification using SMTP settings configured in the application.

    It fetches SMTP server details, port, credentials, and 'from' address
    from the application settings stored in the database.

    Args:
        subject (str): The subject line of the email.
        body (str): The plain text body content of the email.
        to_email (str): The recipient's email address.
    """
    logger = current_app.logger
    try:
        # Fetch all current application settings from the database.
        settings_rows = db_manager.fetchall("SELECT key, value FROM settings")
        settings = {row['key']: row['value'] for row in settings_rows}
    except Exception as e:
        logger.error(f"Failed to load settings from database for email notification: {e}", exc_info=True)
        return # Cannot proceed without SMTP settings.

    # Retrieve SMTP configuration from the loaded settings.
    smtp_server = settings.get('smtp_server')
    smtp_port_str = settings.get('smtp_port', '587') # Default to 587 if not set.
    smtp_user = settings.get('smtp_username', '')
    smtp_password = settings.get('smtp_password', '') # Password is not logged for security.
    from_email = settings.get('smtp_from_email', 'no-reply@example.com') # Default 'from' address.
    use_tls = settings.get('smtp_use_tls', '0') == '1' # Check if TLS is enabled.

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        logger.error(f"Invalid SMTP port configured: '{smtp_port_str}'. Using default 587 for this attempt.",
                     extra={'recipient_email': to_email, 'subject': subject})
        smtp_port = 587


    log_extra = {
        'recipient_email': to_email,
        'subject': subject,
        'smtp_server': smtp_server,
        'smtp_port': smtp_port,
        'from_email': from_email,
        'smtp_user': smtp_user, # Log username, but not password.
        'use_tls': use_tls
    }

    if not smtp_server or not from_email: # Basic check for essential SMTP config.
        logger.warning(
            "Email notification skipped: SMTP server or 'From Email' address is not configured in settings.",
            extra=log_extra
        )
        return

    try:
        # Create the email message.
        msg = MIMEText(body, 'plain', 'utf-8') # Specify plain text and UTF-8 encoding.
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        # Connect to the SMTP server and send the email.
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server: # Added timeout.
            if use_tls: # If TLS is enabled in settings.
                server.starttls()
            if smtp_user and smtp_password: # Login if credentials are provided.
                server.login(smtp_user, smtp_password)
            server.send_message(msg) # Send the composed message.

        logger.info("Email notification sent successfully.", extra=log_extra)
    except Exception as e:
        logger.error("Failed to send email notification.", extra=log_extra, exc_info=True)

def send_pushover_notification(user_key, api_token, title, message):
    """
    Sends a notification via the Pushover service.

    Args:
        user_key (str): The Pushover user key of the recipient.
        api_token (str): The Pushover API token for your application.
        title (str): The title of the Pushover notification.
        message (str): The main content of the Pushover notification.
    """
    logger = current_app.logger
    # Be cautious about logging user_key and api_token if they are considered highly sensitive.
    # For debugging, they are included here but might be partially masked or omitted in production logs.
    log_extra = {'pushover_user_key_present': bool(user_key), 'title': title}
    
    if not user_key or not api_token:
        logger.warning("Pushover notification skipped: User key or API token is missing.", extra=log_extra)
        return

    try:
        response = requests.post('https://api.pushover.net/1/messages.json', data={
            'token': api_token,
            'user': user_key,
            'title': title,
            'message': message,
            # Optional parameters like 'priority', 'sound', 'url', 'url_title' can be added here.
        }, timeout=10) # Added timeout for the HTTP request.
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx).
        logger.info("Pushover notification sent successfully.", extra=log_extra)
    except requests.RequestException as e:
        # This catches network errors, timeouts, and HTTP error responses.
        logger.error("Pushover notification failed.", extra=log_extra, exc_info=True)

def send_apprise_notification(apprise_url, title, body):
    """
    Sends a notification using the Apprise library, which supports various services.

    Args:
        apprise_url (str): The Apprise service URL (e.g., "mailto://user:pass@host", "discord://webhook_id/webhook_token").
        title (str): The title of the notification.
        body (str): The main content of the notification.
    """
    logger = current_app.logger
    # Apprise URLs can contain sensitive information (credentials, tokens).
    # Log only the presence or a sanitized version in production if needed.
    log_extra = {'apprise_url_configured': bool(apprise_url), 'title': title}

    if not apprise_url:
        logger.warning("Apprise notification skipped: Apprise URL is not configured.", extra=log_extra)
        return

    try:
        apobj = Apprise()
        # Add the service URL to the Apprise instance.
        # Apprise handles parsing and routing to the correct notification service.
        if not apobj.add(apprise_url):
            logger.error(f"Failed to add Apprise URL: '{apprise_url}'. It might be invalid or unsupported.", extra=log_extra)
            return

        # Send the notification.
        success = apobj.notify(title=title, body=body)
        
        if success:
            logger.info("Apprise notification dispatched successfully (actual delivery depends on service).", extra=log_extra)
        else:
            # `apobj.notify` returns False if all notifications failed to dispatch.
            logger.warning("Apprise notification failed to dispatch to any service.", extra=log_extra)
    except Exception as e:
        # Catch any other exceptions during Apprise setup or notification sending.
        logger.error("An error occurred during Apprise notification.", extra=log_extra, exc_info=True)

def notify_assigned_user(ticket_id, event_type, triggering_user_id):
    """
    Orchestrates sending notifications to the user assigned to a ticket based on an event.

    Fetches ticket details and the assigned user's notification preferences.
    Constructs a message based on the `event_type` and dispatches notifications
    via enabled channels (Email, Pushover, Apprise) using background threads.
    It avoids notifying a user if they triggered the event themselves on their own assigned ticket.

    Args:
        ticket_id (int): The ID of the relevant ticket.
        event_type (str): The type of event that occurred (e.g., "assigned",
                          "status_update", "new_comment", "priority_update").
        triggering_user_id (int or None): The ID of the user who initiated the event.
                                          Can be None if the action was system-initiated (e.g., webhook).
    """
    logger = current_app.logger
    log_extra_base = {
        'ticket_id': ticket_id,
        'event_type': event_type,
        'triggering_user_id': triggering_user_id
    }

    try:
        # Fetch ticket details.
        ticket = db_manager.fetchone("SELECT id, title, status, priority, assigned_to FROM tickets WHERE id = ?", (ticket_id,))
        if not ticket:
            logger.warning("notify_assigned_user: Ticket not found, cannot send notification.", extra=log_extra_base)
            return
        if not ticket['assigned_to']: # No user is assigned to the ticket.
            logger.info("notify_assigned_user: Ticket is not assigned to any user, no notification sent.", extra=log_extra_base)
            return

        # Fetch details of the user assigned to the ticket.
        assigned_user = db_manager.fetchone("""
            SELECT id, username, email, pushover_user_key, pushover_api_token,
                   apprise_url, notify_email, notify_pushover, notify_apprise
            FROM users WHERE id = ?
        """, (ticket['assigned_to'],))

        if not assigned_user:
            logger.warning(
                "notify_assigned_user: Assigned user (ID from ticket) not found in users table.",
                extra={**log_extra_base, 'assigned_user_id_from_ticket': ticket['assigned_to']}
            )
            return
        
        # Add details of the user to be notified to the log context.
        log_extra_base['notified_user_id'] = assigned_user['id']
        log_extra_base['notified_username'] = assigned_user['username']

        # Avoid self-notification: If the user who triggered the event is the one assigned to the ticket.
        if triggering_user_id is not None and triggering_user_id == assigned_user['id']:
            logger.info(
                "notify_assigned_user: Triggering user is the same as the assigned user. "
                "Skipping self-notification.",
                extra=log_extra_base
            )
            return

        # --- Construct notification subject and message based on event type ---
        subject = ""
        message_body = "" # Renamed from 'message' to avoid conflict with logger message.
        ticket_url = url_for('tickets_bp.ticket_detail', ticket_id=ticket_id, _external=True) # Link to the ticket.

        if event_type == "assigned" or event_type == "assigned_on_creation":
            subject = f"Ticket #{ticket_id} Has Been Assigned To You"
            message_body = f"You have been assigned to ticket #{ticket_id}: '{ticket['title']}'.\nView: {ticket_url}"
        elif event_type == "status_update": # Renamed from "status" for clarity
            subject = f"Status Update on Ticket #{ticket_id}"
            message_body = f"The status of ticket #{ticket_id} ('{ticket['title']}') has been updated to '{ticket['status']}'.\nView: {ticket_url}"
        elif event_type == "priority_update": # Renamed from "priority"
            subject = f"Priority Update on Ticket #{ticket_id}"
            message_body = f"The priority of ticket #{ticket_id} ('{ticket['title']}') has been updated to '{ticket['priority']}'.\nView: {ticket_url}"
        elif event_type == "new_comment":
            subject = f"New Comment on Ticket #{ticket_id}"
            message_body = f"A new comment has been added to ticket #{ticket_id} ('{ticket['title']}').\nView: {ticket_url}"
        else:
            logger.warning(f"notify_assigned_user: Unknown event_type '{event_type}'. No notification sent.", extra=log_extra_base)
            return

        logger.info(
            f"Preparing to send notifications for event '{event_type}' on ticket #{ticket_id} to user '{assigned_user['username']}'.",
            extra=log_extra_base
        )
        
        app_instance = current_app._get_current_object() # Get the actual Flask app instance for context runner.

        # --- Dispatch notifications based on user's preferences ---
        if assigned_user['notify_pushover'] and assigned_user['pushover_user_key'] and assigned_user['pushover_api_token']:
            logger.info("Queuing Pushover notification.", extra={**log_extra_base, 'method': 'pushover'})
            run_in_app_context(
                app_instance, send_pushover_notification,
                assigned_user['pushover_user_key'], assigned_user['pushover_api_token'],
                subject, message_body
            )

        if assigned_user['notify_email'] and assigned_user['email']:
            logger.info("Queuing Email notification.", extra={**log_extra_base, 'method': 'email', 'recipient_email': assigned_user['email']})
            run_in_app_context(
                app_instance, send_email_notification,
                subject, message_body, assigned_user['email']
            )

        if assigned_user['notify_apprise'] and assigned_user['apprise_url']:
            logger.info("Queuing Apprise notification.", extra={**log_extra_base, 'method': 'apprise'})
            run_in_app_context(
                app_instance, send_apprise_notification,
                assigned_user['apprise_url'], subject, message_body
            )
    except Exception as e:
        # Catch-all for unexpected errors during the notification preparation process.
        logger.error(
            f"An unexpected error occurred in notify_assigned_user before dispatching notifications: {e}",
            extra=log_extra_base, exc_info=True
        )
        # Depending on the error, one might want to return or re-raise.
        # For now, logging and preventing a crash of the calling code.

def test_smtp_connection():
    """
    Tests the SMTP connection using settings configured in the application.

    Fetches SMTP server details, port, credentials from the database settings.
    Attempts to connect to the SMTP server, perform EHLO, optionally STARTTLS,
    and login if credentials are provided.

    Returns:
        bool: True if the connection test is successful.

    Raises:
        ValueError: If essential SMTP settings (server) are not configured.
        RuntimeError: If the SMTP connection test fails for any reason (e.g.,
                      connection error, authentication failure, timeout).
    """
    logger = current_app.logger
    try:
        settings_rows = db_manager.fetchall("SELECT key, value FROM settings")
        settings = {row['key']: row['value'] for row in settings_rows}
    except Exception as e:
        logger.error(f"Failed to load settings from database for SMTP test: {e}", exc_info=True)
        raise ValueError("Could not load SMTP settings from the database for testing.")

    smtp_server = settings.get("smtp_server")
    smtp_port_str = settings.get("smtp_port", "587") # Default to 587 if not set.
    smtp_user = settings.get("smtp_username", "")
    smtp_password = settings.get("smtp_password", "") # Not logged for security.
    smtp_use_tls = settings.get("smtp_use_tls", "0") == "1" # Convert '0'/'1' string to boolean.

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        logger.error(f"Invalid SMTP port configured for testing: '{smtp_port_str}'.")
        raise ValueError(f"Invalid SMTP port: '{smtp_port_str}'. Must be a number.")

    log_extra_smtp_test = {
        'smtp_server': smtp_server,
        'smtp_port': smtp_port,
        'smtp_user': smtp_user, # Username is generally safe to log.
        'smtp_use_tls': smtp_use_tls
    }

    if not smtp_server:
        logger.error("SMTP connection test cannot proceed: SMTP server address is not set in settings.", extra=log_extra_smtp_test)
        raise ValueError("SMTP server address is not configured in application settings.")

    try:
        logger.info("Attempting SMTP connection test...", extra=log_extra_smtp_test)
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server: # 10-second timeout.
            server.ehlo() # Initial greeting to the server.
            if smtp_use_tls:
                logger.debug("SMTP Test: Attempting STARTTLS.", extra=log_extra_smtp_test)
                server.starttls()
                server.ehlo() # Re-EHLO after STARTTLS.
            
            if smtp_user and smtp_password: # Login only if both username and password are provided.
                logger.debug(f"SMTP Test: Attempting login for user '{smtp_user}'.", extra=log_extra_smtp_test)
                server.login(smtp_user, smtp_password)
        logger.info("SMTP connection test successful.", extra=log_extra_smtp_test)
        return True
    except smtplib.SMTPAuthenticationError as auth_e:
        logger.error(f"SMTP connection test failed: Authentication error - {auth_e}", extra=log_extra_smtp_test)
        raise RuntimeError(f"SMTP Authentication Failed: {auth_e}. Check username/password and server settings.")
    except Exception as e: # Catch other smtplib errors, socket errors, timeouts etc.
        logger.error("SMTP connection test failed due to an unexpected error.", extra=log_extra_smtp_test, exc_info=True)
        raise RuntimeError(f"SMTP connection test failed: {e}")
