import smtplib
from email.mime.text import MIMEText
import logging

def send_email(config, recipient_email: str, subject: str, body: str):
    """Send an email using Gmail's SMTP SSL."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config["from_email"]
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(config["smtp_username"], config["smtp_password"])
            server.send_message(msg)
        logging.info(f"Email sent to {recipient_email} with subject: {subject}")
    except Exception as e:
        logging.error(f"Email sending failed to {recipient_email}: {e}") 