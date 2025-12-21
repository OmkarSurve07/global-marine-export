from django.contrib import admin

from accounts.models import AllowedEmail, EmailOTP, AccessLog, RevokedToken


class AllowedEmailAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'is_active', 'created_at',)
    list_filter = ('is_active',)
    search_fields = ('email',)
    ordering = ('-created_at',)


class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'otp_hash', 'created_at', 'expires_at', 'attempts', 'used',)
    list_filter = ('used',)
    search_fields = ('email',)
    ordering = ('-created_at',)


class AccessLogAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'allowed_email', 'path', 'method', 'query_string', 'started_at', 'ended_at', 'duration_seconds',
        'status_code', 'token_jti',
    )
    list_filter = ('status_code',)
    search_fields = ('allowed_email__email', 'path', 'method', 'query_string',)
    ordering = ('-started_at',)


class RevokedTokenAdmin(admin.ModelAdmin):
    list_display = ('id', 'jti', 'revoked_at', 'expires_at',)
    search_fields = ('jti',)
    ordering = ('-revoked_at',)


admin.site.register(AllowedEmail, AllowedEmailAdmin)
admin.site.register(EmailOTP, EmailOTPAdmin)
admin.site.register(AccessLog, AccessLogAdmin)
admin.site.register(RevokedToken, RevokedTokenAdmin)
