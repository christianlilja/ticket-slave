import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
import requests
import os
import logging
from apprise import Apprise
from app.db import get_db
from flask import current_app

# Optional: Setup a simple logger
logger = logging.getLogger(__name__)

# Send an email notification
def send_email_notification(subject, body, to_email):
    with current_app.app_context():  # <- Push context here

        with get_db() as conn:
            settings = {
                row['key']: row['value']
                for row in conn.execute("SELECT key, value FROM settings").fetchall()
            }

        smtp_server = settings.get('smtp_server')
        smtp_port = int(settings.get('smtp_port', 587))
        smtp_user = settings.get('smtp_username', '')
        smtp_password = settings.get('smtp_password', '')
        from_email = settings.get('smtp_from_email', '')

        if not smtp_server:
            current_app.logger.warning("Missing SMTP server config – skipping email.")
            return

        if not from_email:
            from_email = 'no-reply@example.com'

        try:
            from email.mime.text import MIMEText

            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = from_email
            msg['To'] = to_email

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                if smtp_user and smtp_password:
                    server.starttls()
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)

            current_app.logger.info(f"Email sent successfully to {to_email}")
        except Exception as e:
            current_app.logger.error(f"Failed to send email: {e}")

# Send a Pushover notification
def send_pushover_notification(user_key, api_token, title, message):
    try:
        response = requests.post('https://api.pushover.net/1/messages.json', data={
            'token': api_token,
            'user': user_key,
            'title': title,
            'message': message,
        })
        response.raise_for_status()  # Raises exception if bad response
    except requests.RequestException as e:
        print(f"Pushover notification failed: {e}")

def send_apprise_notification(apprise_url, title, body):
    try:
        apobj = Apprise()
        apobj.add(apprise_url)
        success = apobj.notify(
            title=title,
            body=body
        )
        
        if not success:
            print("Apprise notification failed to send.")
    except Exception as e:
        print(f"Apprise notification error: {e}")

def notify_assigned_user(ticket_id, event_type, user_id):
    with get_db() as conn:
        ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not ticket or not ticket['assigned_to']:
            return

        assigned_user = conn.execute("""
            SELECT id, username, email, pushover_user_key, pushover_api_token, 
                   apprise_url, notify_email, notify_pushover, notify_apprise
            FROM users WHERE id = ?
        """, (ticket['assigned_to'],)).fetchone()

        if not assigned_user or user_id == assigned_user['id']:
            return  # Don't notify the person who triggered the action

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

        # Send Pushover if enabled
        if assigned_user['notify_pushover'] == 1 and assigned_user['pushover_user_key'] and assigned_user['pushover_api_token']:
            send_pushover_notification(
                assigned_user['pushover_user_key'],
                assigned_user['pushover_api_token'],
                title=subject,
                message=message
            )

        if assigned_user['notify_email'] == 1 and assigned_user['email']:
            send_email_notification(
                subject=subject,
                body=message,
                to_email=assigned_user['email']
            )


        # Send Apprise if enabled
        if assigned_user['notify_apprise'] == 1 and assigned_user['apprise_url']:
            send_apprise_notification(
                apprise_url=assigned_user['apprise_url'],
                title=subject,
                body=message
            )

def test_smtp_connection():

    with get_db() as conn:
        settings = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM settings").fetchall()
        }

    smtp_server = settings.get("smtp_server")
    smtp_port = int(settings.get("smtp_port", 587))
    smtp_user = settings.get("smtp_username", "")
    smtp_password = settings.get("smtp_password", "")
    smtp_use_tls = bool(int(settings.get("smtp_use_tls", 0)))

    if not smtp_server:
        raise ValueError("SMTP server is not set.")

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.ehlo()
            if smtp_use_tls:
                server.starttls()
                server.ehlo()

            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)

        return True  # Success

    except Exception as e:
        raise RuntimeError(f"SMTP test failed: {e}")