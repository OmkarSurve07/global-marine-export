import jwt
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from .serializers import RequestOTPSerializer, VerifyOTPSerializer, RefreshSerializer, AccessLogSerializer, \
    LogoutSerializer
from .models import AllowedEmail, EmailOTP, RevokedToken, AccessLog
from .utils import generate_plain_otp, hmac_hash_otp, send_otp_email, make_jwt_tokens_for_allowed_email


class AccountViewSet(viewsets.ViewSet):
    """
    ViewSet providing:
      POST /accounts/request_otp/   -> request OTP
      POST /accounts/verify_otp/    -> verify OTP -> returns tokens
      POST /accounts/refresh/       -> refresh access token using refresh token
    """
    permission_classes = [AllowAny, ]

    @action(detail=False, methods=["post"], url_path="request-otp")
    def request_otp(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        try:
            allowed = AllowedEmail.objects.get(email__iexact=email, is_active=True)
        except AllowedEmail.DoesNotExist:
            return Response({"detail": "Email not registered for access."}, status=status.HTTP_403_FORBIDDEN)

        otp_plain = generate_plain_otp()
        otp_hash_val = hmac_hash_otp(otp_plain)
        expiry = timezone.now() + timedelta(seconds=getattr(settings, "OTP_EXPIRY_SECONDS", 300))

        # cleanup previous unused OTPs (optional)
        EmailOTP.objects.filter(email__iexact=email, used=False).delete()

        EmailOTP.objects.create(email=email, otp_hash=otp_hash_val, expires_at=expiry)

        print("DEFAULT_FROM_EMAIL:", settings.DEFAULT_FROM_EMAIL)

        # send OTP (sync; queue in prod)
        send_otp_email(email, otp_plain)

        return Response({"detail": "OTP sent to email."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="verify-otp")
    def verify_otp(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        otp = serializer.validated_data["otp"]

        try:
            allowed = AllowedEmail.objects.get(email__iexact=email, is_active=True)
        except AllowedEmail.DoesNotExist:
            return Response({"detail": "Email not registered for access."}, status=status.HTTP_403_FORBIDDEN)

        otp_obj = EmailOTP.objects.filter(email__iexact=email, used=False).order_by("-created_at").first()
        if not otp_obj:
            return Response({"detail": "No OTP request found. Request a new OTP."}, status=status.HTTP_400_BAD_REQUEST)

        if otp_obj.attempts >= getattr(settings, "OTP_MAX_ATTEMPTS", 5):
            return Response({"detail": "Too many attempts. Request a new OTP."}, status=status.HTTP_400_BAD_REQUEST)

        if otp_obj.is_expired():
            return Response({"detail": "OTP expired. Request a new OTP."}, status=status.HTTP_400_BAD_REQUEST)

        if hmac_hash_otp(otp) != otp_obj.otp_hash:
            otp_obj.attempts += 1
            otp_obj.save(update_fields=["attempts"])
            return Response({"detail": "Invalid OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # success
        otp_obj.mark_used()

        tokens = make_jwt_tokens_for_allowed_email(allowed)

        # optional: store refresh jti in RevokedToken? (only for revocation handling)
        # Not revoking now — but ensure you check RevokedToken on refresh in refresh endpoint

        return Response({
            "access": tokens["access"],
            "refresh": tokens["refresh"],
            "email": allowed.email,
            "allowed_email_id": str(allowed.id),
            "access_jti": tokens["access_jti"],
            "refresh_jti": tokens["refresh_jti"],
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="refresh")
    def refresh(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data["refresh"]

        import jwt
        try:
            payload = jwt.decode(refresh_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return Response({"detail": "Refresh token expired"}, status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError:
            return Response({"detail": "Invalid refresh token"}, status=status.HTTP_401_UNAUTHORIZED)

        if payload.get("type") != "refresh":
            return Response({"detail": "Invalid token type"}, status=status.HTTP_400_BAD_REQUEST)

        # check revocation
        jti = payload.get("jti")
        if jti and RevokedToken.objects.filter(jti=jti).exists():
            return Response({"detail": "Refresh token revoked"}, status=status.HTTP_401_UNAUTHORIZED)

        # validate allowed email exists & active
        try:
            allowed = AllowedEmail.objects.get(id=payload.get("allowed_email_id"), email__iexact=payload.get("email"),
                                               is_active=True)
        except AllowedEmail.DoesNotExist:
            return Response({"detail": "No such allowed email"}, status=status.HTTP_401_UNAUTHORIZED)

        tokens = make_jwt_tokens_for_allowed_email(allowed)
        return Response({"access": tokens["access"], "refresh": tokens["refresh"], "access_jti": tokens["access_jti"],
                         "refresh_jti": tokens["refresh_jti"]})

    @action(detail=False, methods=["get"], url_path="me", permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        Return basic profile info for the authenticated allowed_email.
        Requires Authorization: Bearer <access_token>
        """
        # simple user-like object from SimpleJWT is request.user
        # we prefer request.allowed_email (set by your JWT auth). Fallback to email claim if missing.
        allowed = getattr(request, "allowed_email", None)
        if not allowed:
            # fallback: try to locate by email claim in token payload if your JWT auth sets token payload on request
            token_payload = getattr(request, "token_payload", None)
            if token_payload:
                try:
                    allowed = AllowedEmail.objects.get(id=token_payload.get("allowed_email_id"),
                                                       email__iexact=token_payload.get("email"))
                except AllowedEmail.DoesNotExist:
                    allowed = None

        if not allowed:
            return Response({"detail": "Allowed email not found"}, status=status.HTTP_401_UNAUTHORIZED)

        # compute last login (last request start time) from AccessLog
        last_log = AccessLog.objects.filter(allowed_email=allowed).order_by("-started_at").first()
        total_requests = AccessLog.objects.filter(allowed_email=allowed).count()

        data = {
            "email": allowed.email,
            "allowed_email_id": str(allowed.id),
            "is_active": allowed.is_active,
            "created_at": allowed.created_at,
            "last_request_at": last_log.started_at if last_log else None,
            "last_request_path": last_log.path if last_log else None,
            "total_requests": total_requests,
        }
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="logs", permission_classes=[IsAuthenticated])
    def logs(self, request):
        """
        Return recent AccessLog entries for the authenticated allowed_email.
        Query params:
          - limit (int, default 50)
          - since (ISO datetime string)  e.g. 2025-12-11T00:00:00Z
        """
        allowed = getattr(request, "allowed_email", None)
        if not allowed:
            token_payload = getattr(request, "token_payload", None)
            if token_payload:
                try:
                    allowed = AllowedEmail.objects.get(id=token_payload.get("allowed_email_id"),
                                                       email__iexact=token_payload.get("email"))
                except AllowedEmail.DoesNotExist:
                    allowed = None

        if not allowed:
            return Response({"detail": "Allowed email not found"}, status=status.HTTP_401_UNAUTHORIZED)

        # parse query params
        try:
            limit = int(request.query_params.get("limit", 50))
            if limit <= 0 or limit > 1000:
                limit = 50
        except (ValueError, TypeError):
            limit = 50

        since = request.query_params.get("since")
        qs = AccessLog.objects.filter(allowed_email=allowed).order_by("-started_at")
        if since:
            dt = parse_datetime(since)
            if dt is None:
                # try naive parsing by django parse_datetime returns None on some inputs; ignore invalid
                return Response({"detail": "Invalid 'since' datetime. Use ISO format: YYYY-MM-DDTHH:MM:SSZ"},
                                status=status.HTTP_400_BAD_REQUEST)
            # ensure timezone-aware comparison
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone=timezone.get_current_timezone())
            qs = qs.filter(started_at__gte=dt)

        qs = qs[:limit]
        serializer = AccessLogSerializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="logout", permission_classes=[IsAuthenticated],)
    def logout(self, request):
        """
        Logout by revoking refresh token.
        Access token will expire naturally.
        """
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh"]

        try:
            payload = jwt.decode(
                refresh_token,
                settings.JWT_SECRET,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            return Response(
                {"detail": "Refresh token already expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except jwt.InvalidTokenError:
            return Response(
                {"detail": "Invalid refresh token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if payload.get("token_type") != "refresh":
            return Response(
                {"detail": "Invalid token type"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        jti = payload.get("jti")
        if not jti:
            return Response(
                {"detail": "Token missing jti"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # idempotent revoke
        RevokedToken.objects.get_or_create(jti=jti)

        return Response(
            {"detail": "Logged out successfully"},
            status=status.HTTP_200_OK,
        )
