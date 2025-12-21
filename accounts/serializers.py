from rest_framework import serializers

from accounts.models import AccessLog


class RequestOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=32)


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class AccessLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessLog
        fields = [
            "id",
            "path",
            "method",
            "query_string",
            "started_at",
            "ended_at",
            "duration_seconds",
            "status_code",
            "token_jti",
        ]

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
