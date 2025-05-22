import smtplib
from email.mime.text import MIMEText
import requests
from apprise import Apprise
from app.db import db_manager # Import db_manager instance
from utils.context_runner import run_in_app_context
from flask import current_app

def send_email_notification(subject, body, to_email):
    logger = current_app.logger
    try:
        # Fetch settings using db_manager
        settings_rows = db_manager.fetchall("SELECT key, value FROM settings")
        settings = {row['key']: row['value'] for row in settings_rows}
    except Exception as e:
        logger.error(f"Failed to load settings for email notification: {e}", exc_info=True)
        return # Cannot proceed without settings

    smtp_server = settings.get('smtp_server')
    smtp_port = int(settings.get('smtp_port', 587))
    smtp_user = settings.get('smtp_username', '')
    smtp_password = settings.get('smtp_password', '') # Avoid logging this
    from_email = settings.get('smtp_from_email', 'no-reply@example.com')

    log_extra = {
        'recipient_email': to_email,
        'subject': subject,
        'smtp_server': smtp_server,
        'smtp_port': smtp_port,
        'from_email': from_email
    }

    if not smtp_server:
        logger.warning(
            "Missing SMTP server config – skipping email.",
            extra=log_extra
        )
        return

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            if smtp_user and smtp_password: # Check if credentials are provided
                server.starttls()
                server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info(
            "Email sent successfully",
            extra=log_extra
        )
    except Exception as e:
        logger.error(
            "Failed to send email",
            extra=log_extra,
            exc_info=True # Include stack trace
        )

def send_pushover_notification(user_key, api_token, title, message):
    logger = current_app.logger
    log_extra = {
        'pushover_user_key': user_key, # Be mindful if this is sensitive
        'title': title
    }
    try:
        response = requests.post('https://api.pushover.net/1/messages.json', data={
            'token': api_token, # Be mindful if this is sensitive
            'user': user_key,
            'title': title,
            'message': message,
        })
        response.raise_for_status()
        logger.info("Pushover notification sent successfully", extra=log_extra)
    except requests.RequestException as e:
        logger.error(
            "Pushover notification failed",
            extra=log_extra,
            exc_info=True
        )

def send_apprise_notification(apprise_url, title, body):
    logger = current_app.logger
    log_extra = {
        'apprise_url': apprise_url, # Be mindful if this contains sensitive parts
        'title': title
    }
    try:
        apobj = Apprise()
        apobj.add(apprise_url)
        success = apobj.notify(title=title, body=body)
        if success:
            logger.info("Apprise notification sent successfully", extra=log_extra)
        else:
            logger.warning("Apprise notification failed to send (returned false)", extra=log_extra)
    except Exception as e:
        logger.error(
            "Apprise notification error",
            extra=log_extra,
            exc_info=True
        )

def notify_assigned_user(ticket_id, event_type, user_id):
    logger = current_app.logger
    log_extra_base = {
        'ticket_id': ticket_id,
        'event_type': event_type,
        'triggering_user_id': user_id
    }

    try:
        ticket = db_manager.fetchone("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        if not ticket:
            logger.warning("notify_assigned_user: Ticket not found", extra=log_extra_base)
            return
        if not ticket['assigned_to']:
            logger.info("notify_assigned_user: Ticket not assigned", extra=log_extra_base)
            return

        assigned_user = db_manager.fetchone("""
            SELECT id, username, email, pushover_user_key, pushover_api_token,
                   apprise_url, notify_email, notify_pushover, notify_apprise
            FROM users WHERE id = ?
        """, (ticket['assigned_to'],))

        if not assigned_user:
            logger.warning("notify_assigned_user: Assigned user not found",
                           extra={**log_extra_base, 'assigned_user_id_from_ticket': ticket['assigned_to']})
            return
        
        log_extra_base['notified_user_id'] = assigned_user['id']
        log_extra_base['notified_username'] = assigned_user['username']

        if user_id == assigned_user['id']: # User performed action on their own ticket
            logger.info(
                "notify_assigned_user: User performed action on their own assigned ticket, no notification needed",
                extra=log_extra_base
            )
            return

        subject = ""
        message = ""

        if event_type == "assigned":
            subject = f"Ticket #{ticket_id} Assigned to You"
            message = f"You have been assigned to ticket #{ticket_id}: {ticket['title']}"
        elif event_type == "status":
            subject = f"Ticket #{ticket_id} Status Updated"
            message = f"The status of ticket #{ticket_id} has changed to '{ticket['status']}'"
        elif event_type == "priority":
            subject = f"Ticket #{ticket_id} Priority Updated"
            message = f"The priority of ticket #{ticket_id} has changed to '{ticket['priority']}'"
        elif event_type == "new_comment":
            subject = f"New Comment on Ticket #{ticket_id}"
            message = f"A new comment was added to ticket #{ticket_id}."
        else:
            logger.warning(f"notify_assigned_user: Unknown event_type '{event_type}'", extra=log_extra_base)
            return


        logger.info(
            f"Preparing to send notifications for event '{event_type}' on ticket #{ticket_id} to user {assigned_user['username']}",
            extra=log_extra_base
        )
        # Queue notifications with app context
        if assigned_user['notify_pushover'] and assigned_user['pushover_user_key'] and assigned_user['pushover_api_token']:
            logger.info("Queuing Pushover notification", extra={**log_extra_base, 'method': 'pushover'})
            run_in_app_context(
                current_app._get_current_object(),
                send_pushover_notification,
                assigned_user['pushover_user_key'],
                assigned_user['pushover_api_token'],
                subject,
                message
            )

        if assigned_user['notify_email'] and assigned_user['email']:
            logger.info("Queuing Email notification", extra={**log_extra_base, 'method': 'email', 'recipient_email': assigned_user['email']})
            run_in_app_context(
                current_app._get_current_object(),
                send_email_notification,
                subject,
                message,
                assigned_user['email']
            )

        if assigned_user['notify_apprise'] and assigned_user['apprise_url']:
            logger.info("Queuing Apprise notification", extra={**log_extra_base, 'method': 'apprise', 'apprise_url_used': assigned_user['apprise_url']})
            run_in_app_context(
                current_app._get_current_object(),
                send_apprise_notification,
                assigned_user['apprise_url'],
                subject,
                message
            )
    except Exception as e:
        logger.error(f"Error in notify_assigned_user before sending notifications: {e}", extra=log_extra_base, exc_info=True)
        # Depending on the error, you might want to return or re-raise
        # For now, just logging and preventing a crash.


def test_smtp_connection():
    logger = current_app.logger
    try:
        # Fetch settings using db_manager
        settings_rows = db_manager.fetchall("SELECT key, value FROM settings")
        settings = {row['key']: row['value'] for row in settings_rows}
    except Exception as e:
        logger.error(f"Failed to load settings for SMTP test: {e}", exc_info=True)
        raise ValueError("Could not load SMTP settings from database.")


    smtp_server = settings.get("smtp_server")
    smtp_port = int(settings.get("smtp_port", 587))
    smtp_user = settings.get("smtp_username", "")
    smtp_password = settings.get("smtp_password", "") # Avoid logging
    smtp_use_tls = bool(int(settings.get("smtp_use_tls", 0)))

    log_extra = {
        'smtp_server': smtp_server,
        'smtp_port': smtp_port,
        'smtp_user': smtp_user, # Username might be okay, but not password
        'smtp_use_tls': smtp_use_tls
    }

    if not smtp_server:
        logger.error("SMTP test_smtp_connection: SMTP server is not set.", extra=log_extra)
        raise ValueError("SMTP server is not set.")

    try:
        logger.info("Attempting SMTP connection test", extra=log_extra)
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.ehlo()
            if smtp_use_tls:
                server.starttls()
                server.ehlo()

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
        logger.info("SMTP connection test successful", extra=log_extra)
        return True
    except Exception as e:
        logger.error("SMTP connection test failed", extra=log_extra, exc_info=True)
        raise RuntimeError(f"SMTP test failed: {e}")
