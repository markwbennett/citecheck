import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jose import jwt
from datetime import datetime, timedelta
from .config import get_settings

settings = get_settings()


def create_verification_token(email: str) -> str:
    """Create a JWT token for email verification."""
    expire = datetime.utcnow() + timedelta(hours=24)  # Token valid for 24 hours
    to_encode = {
        "email": email,
        "exp": expire
    }
    token = jwt.encode(to_encode, settings.secret_key, algorithm="HS256")
    return token


def verify_token(token: str) -> str:
    """Verify a JWT token and return the email address."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        email = payload.get("email")
        if email is None:
            raise ValueError("Invalid token")
        return email
    except jwt.JWTError:
        raise ValueError("Invalid or expired token")


def send_verification_email(email: str):
    """Send a verification email to the user."""
    token = create_verification_token(email)
    verification_link = f"{settings.frontend_url}/verify?token={token}"

    # Create the email message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'CiteCheck - Verify Your Email'
    msg['From'] = settings.from_email
    msg['To'] = email

    # Create HTML and plain text versions
    text_body = f"""
    Welcome to CiteCheck!

    Please verify your email address by clicking the link below:

    {verification_link}

    This link will expire in 24 hours.

    If you did not request this verification, please ignore this email.

    ---
    CiteCheck - Legal Brief Analysis
    """

    html_body = f"""
    <html>
      <head></head>
      <body>
        <h2>Welcome to CiteCheck!</h2>
        <p>Please verify your email address by clicking the button below:</p>
        <p>
          <a href="{verification_link}"
             style="background-color: #4CAF50; color: white; padding: 14px 20px;
                    text-decoration: none; display: inline-block; border-radius: 4px;">
            Verify Email Address
          </a>
        </p>
        <p>Or copy and paste this link into your browser:</p>
        <p><a href="{verification_link}">{verification_link}</a></p>
        <p><small>This link will expire in 24 hours.</small></p>
        <p><small>If you did not request this verification, please ignore this email.</small></p>
        <hr>
        <p><small>CiteCheck - Legal Brief Analysis</small></p>
      </body>
    </html>
    """

    # Attach both versions
    part1 = MIMEText(text_body, 'plain')
    part2 = MIMEText(html_body, 'html')
    msg.attach(part1)
    msg.attach(part2)

    # Send the email
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        raise Exception(f"Failed to send verification email: {str(e)}")
