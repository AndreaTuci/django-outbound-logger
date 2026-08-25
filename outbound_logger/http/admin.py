from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from ..admin import ReadOnlyLogAdmin, RetentionFilter
from .models import HttpRequestAttempt, HttpRequestLog


class HttpRequestAttemptInline(admin.TabularInline):
    model = HttpRequestAttempt
    extra = 0
    can_delete = False
    fields = ("started_at", "trigger", "status_code", "error")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HttpRequestLog)
class HttpRequestLogAdmin(ReadOnlyLogAdmin):
    date_hierarchy = "created_at"
    list_display = (
        "created_at",
        "method",
        "url",
        "status",
        "status_code",
        "duration_ms",
        "retriable",
    )
    list_filter = ("status", "method", "retriable", "created_at", RetentionFilter)
    search_fields = ("url", "reason")
    inlines = (HttpRequestAttemptInline,)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "created_at",
                    "status",
                    "duration_ms",
                    "retriable",
                    "context",
                )
            },
        ),
        (
            _("Request"),
            {
                "fields": (
                    "method",
                    "url",
                    "request_headers",
                    "request_body",
                    "request_body_omission",
                )
            },
        ),
        (
            _("Response"),
            {
                "fields": (
                    "status_code",
                    "reason",
                    "response_headers",
                    "response_body",
                    "response_body_omission",
                    "response_truncated",
                )
            },
        ),
    )
