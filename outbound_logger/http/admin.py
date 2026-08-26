from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from ..admin import ReadOnlyLogAdmin, RetentionFilter, message_retry_report
from .models import HttpRequestAttempt, HttpRequestLog
from .retry import retry_requests

ATTEMPT_COUNT_FIELD = "_attempt_count"


class HttpRequestAttemptInline(admin.TabularInline):
    model = HttpRequestAttempt
    extra = 0
    can_delete = False
    fields = ("started_at", "trigger", "status_code", "error")
    readonly_fields = fields

    def has_add_permission(
        self, request: HttpRequest, obj: HttpRequestLog | None = None
    ) -> bool:
        return False


@admin.register(HttpRequestLog)
class HttpRequestLogAdmin(ReadOnlyLogAdmin):
    date_hierarchy = "created_at"
    actions = ("retry_selected",)
    list_display = (
        "created_at",
        "method",
        "url",
        "status",
        "status_code",
        "duration_ms",
        "retriable",
        "attempt_count",
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

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        annotation = {ATTEMPT_COUNT_FIELD: Count("attempts")}
        return super().get_queryset(request).annotate(**annotation)

    @admin.display(description=_("attempts"), ordering=ATTEMPT_COUNT_FIELD)
    def attempt_count(self, log: HttpRequestLog) -> int:
        return getattr(log, ATTEMPT_COUNT_FIELD)

    @admin.action(description=_("Send the selected requests again"))
    def retry_selected(self, request: HttpRequest, queryset: QuerySet) -> None:
        report = retry_requests(queryset, trigger=HttpRequestAttempt.Trigger.ADMIN)
        message_retry_report(self, request, report)
