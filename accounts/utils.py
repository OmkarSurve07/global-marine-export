import os
import random
import hmac
import hashlib
import threading
import traceback

import jwt
import secrets
from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from sib_api_v3_sdk import Configuration, ApiClient, TransactionalEmailsApi, SendSmtpEmail
from sib_api_v3_sdk.rest import ApiException

from gme_backend import settings


def generate_plain_otp(length=None):
    length = length or getattr(settings, "OTP_LENGTH", 6)
    start = 10 ** (length - 1)
    end = (10 ** length) - 1
    return str(random.randint(start, end))


def hmac_hash_otp(otp: str):
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, otp.encode("utf-8"), hashlib.sha256).hexdigest()


def _send_otp_email(email: str, otp: str):
    try:
        # Configure API client with your Brevo API key
        configuration = Configuration()
        configuration.api_key['api-key'] = os.environ.get('BREVO_API_KEY')

        # Create API client instance
        api_client = ApiClient(configuration)
        api_instance = TransactionalEmailsApi(api_client)

        # Prepare email data
        subject = "Your login OTP"
        expires_min = int(getattr(settings, "OTP_EXPIRY_SECONDS", 300) / 60)
        message = f"Your OTP: {otp}. Expires in {expires_min} minute(s)."

        # Define the email payload
        send_smtp_email = SendSmtpEmail(
            to=[{"email": email}],
            sender={
                "name": os.environ.get("DEFAULT_FROM_NAME", "YourAppName"),
                "email": os.environ.get("DEFAULT_FROM_EMAIL")
            },
            subject=subject,
            text_content=message,
            # Optionally, use html_content for HTML emails
            # html_content=f"<p>Your OTP: <strong>{otp}</strong>. Expires in {expires_min} minute(s).</p>"
        )

        # Send the email
        response = api_instance.send_transac_email(send_smtp_email)

    except ApiException as e:
        raise Exception(f"Failed to send OTP email: {e}")
    except Exception as e:
        raise Exception(f"Failed to send OTP email: {e}")


def send_otp_email(email: str, otp: str):
    # Keep the background thread for async sending
    threading.Thread(
        target=_send_otp_email,
        args=(email, otp),
        daemon=True
    ).start()


def make_jwt_tokens_for_allowed_email(allowed_email):
    refresh = RefreshToken()
    refresh["user_id"] = None
    refresh["email"] = allowed_email.email.lower()
    refresh["allowed_email_id"] = str(allowed_email.id)

    access = refresh.access_token
    access["user_id"] = None
    access["email"] = allowed_email.email.lower()
    access["allowed_email_id"] = str(allowed_email.id)

    return {
        "access": str(access),
        "refresh": str(refresh),
        "access_jti": access["jti"],
        "refresh_jti": refresh["jti"],
    }
