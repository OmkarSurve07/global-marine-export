import uuid
from django.db import models
from django.utils import timezone


class AllowedEmail(models.Model):
    """
    Emails allowed to login (managed via admin / CSV import).
    We keep an is_active flag so admin can disable access without deleting.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class EmailOTP(models.Model):
    """
    One-time password requests for an email.
    We store a hashed/hmaced otp (otp_hash) — do NOT store plaintext in production.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)             # the email the OTP was requested for
    otp_hash = models.CharField(max_length=128)          # store HMAC/SHA256 hex
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)            # incorrect verify attempts
    used = models.BooleanField(default=False)            # set true once OTP is consumed

    class Meta:
        indexes = [
            models.Index(fields=["email", "-created_at"]),
        ]

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def mark_used(self):
        self.used = True
        self.save(update_fields=["used"])

    def __str__(self):
        return f"OTP for {self.email} (used={self.used})"


class AccessLog(models.Model):
    """
    Tracks authenticated requests for activity monitoring.
    This links to AllowedEmail (not Django User) and optionally stores token jti.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    allowed_email = models.ForeignKey(AllowedEmail, null=True, blank=True, on_delete=models.SET_NULL)
    path = models.CharField(max_length=1000)
    method = models.CharField(max_length=10)
    query_string = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    token_jti = models.CharField(max_length=255, blank=True, null=True)   # optional JWT jti claim

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.allowed_email} {self.method} {self.path} @ {self.started_at}"


class RevokedToken(models.Model):
    """
    Optional: store revoked refresh token identifiers (jti) or full token strings to support logout/revocation.
    If you include a 'jti' claim in your JWTs, store jti here to mark tokens invalid.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jti = models.CharField(max_length=255, unique=True)   # token identifier (if using jti claim)
    revoked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # store original expiry for cleanup

    def __str__(self):
        return f"Revoked {self.jti}"
