"""Admin pieces shared by the logs."""

from collections import Counter
from typing import Any

from django.contrib import admin, messages
from django.db.models import Model, QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from .purge import expired
from .retry import RetryReport


class ReadOnlyLogAdmin(admin.ModelAdmin):
    """A log records what happened: the admin reads it, nothing edits it."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return False


class RetentionFilter(admin.SimpleListFilter):
    """Selects what the purge would delete, so that the standard delete action can."""

    title = _("retention")
    parameter_name = "expired"
    EXPIRED = "expired"

    def lookups(self, request: HttpRequest, model_admin: admin.ModelAdmin) -> tuple[tuple[str, Any], ...]:
        return ((self.EXPIRED, _("Older than the retention window")),)

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        if self.value() == self.EXPIRED:
            return expired(queryset)
        return queryset


def message_retry_report(
    model_admin: admin.ModelAdmin, request: HttpRequest, report: RetryReport
) -> None:
    """Turn what a retry reported into admin messages."""
    if report.succeeded:
        model_admin.message_user(
            request,
            _("%(count)d sent again.") % {"count": len(report.succeeded)},
            messages.SUCCESS,
        )
    if report.failed:
        model_admin.message_user(
            request,
            _("%(count)d failed again.") % {"count": len(report.failed)},
            messages.ERROR,
        )
    for reason, count in Counter(reason for _log, reason in report.skipped).items():
        model_admin.message_user(
            request,
            _("%(count)d skipped: %(reason)s") % {"count": count, "reason": reason},
            messages.WARNING,
        )
