#!/usr/bin/env python3
"""
Send email reports via SMTP (Fastmail).

Usage:
    python3 send_email.py <html_file> <recipient> [subject]
"""

import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

# Load .env from script directory
load_dotenv(Path(__file__).parent / '.env')


def send_email(html_file: str, recipient: str, subject: str = None) -> bool:
    """Send an HTML file as an email."""
    # Get SMTP settings from environment
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.fastmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    from_email = os.environ.get('FROM_EMAIL', smtp_user)

    if not smtp_user or not smtp_password:
        print("Error: SMTP_USER and SMTP_PASSWORD must be set in .env")
        return False

    # Read the HTML file
    html_path = Path(html_file)
    if not html_path.exists():
        print(f"Error: File not found: {html_file}")
        return False

    html_content = html_path.read_text()

    # Default subject from filename
    if not subject:
        subject = f"CiteCheck Report: {html_path.stem}"

    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = recipient

    # Create plain text version (simple extraction)
    import re
    plain_text = re.sub(r'<[^>]+>', ' ', html_content)
    plain_text = ' '.join(plain_text.split())[:500] + "...\n\n[See HTML version for full report]"

    # Attach both versions
    msg.attach(MIMEText(plain_text, 'plain'))
    msg.attach(MIMEText(html_content, 'html'))

    # Send the email
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print(f"Email sent to {recipient}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    html_file = sys.argv[1]
    recipient = sys.argv[2]
    subject = sys.argv[3] if len(sys.argv) > 3 else None

    success = send_email(html_file, recipient, subject)
    sys.exit(0 if success else 1)
