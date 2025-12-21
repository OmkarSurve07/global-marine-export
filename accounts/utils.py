import random
import hmac
import hashlib
import threading

import jwt
import secrets
from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

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
        subject = "Your login OTP"
        expires_min = int(getattr(settings, "OTP_EXPIRY_SECONDS", 300) / 60)
        message = f"Your OTP: {otp}. Expires in {expires_min} minute(s)."

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        print("OTP email failed")


def send_otp_email(email: str, otp: str):
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
