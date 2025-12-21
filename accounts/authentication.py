# accounts/authentication.py

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken
from accounts.models import AllowedEmail  # ← your model


class CustomJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        try:
            validated_token = UntypedToken(raw_token)
        except InvalidToken:
            return None

        # Extract claims
        payload = validated_token.payload
        email = payload.get("email")
        allowed_email_id = payload.get("allowed_email_id")

        # Try to fetch the AllowedEmail object and attach it to request
        allowed_email_obj = None
        if email and allowed_email_id:
            try:
                allowed_email_obj = AllowedEmail.objects.get(
                    id=allowed_email_id,
                    email__iexact=email,
                    is_active=True
                )
            except (AllowedEmail.DoesNotExist, ValueError):
                pass

        # Attach it exactly the way your /me view expects
        request.allowed_email = allowed_email_obj

        # Dummy user so IsAuthenticated permission is happy
        class DummyUser:
            is_authenticated = True

        return (DummyUser(), validated_token)