import smtplib
from email.mime.text import MIMEText
import requests
import os
import logging
from apprise import Apprise
# Optional: Setup a simple logger
logger = logging.getLogger(__name__)

# Send an email notification
def send_email_notification(subject, body, to_email):
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')

    if not all([smtp_server, smtp_user, smtp_password]):
        logger.warning("SMTP settings are not fully configured. Skipping email notification.")
        return

    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = to_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        logger.info(f"Email sent successfully to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

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
