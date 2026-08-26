from django.contrib import admin
from django.db.models import QuerySet, TextField
from django.db.models.functions import Cast
from django.http import HttpRequest
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from ..admin import ReadOnlyLogAdmin, RetentionFilter, message_retry_report
from .models import EmailLog, EmailSendAttempt
from .retry import retry_emails

RECIPIENTS_SEARCH_FIELD = "_recipients"
DEFERRED_FIELDS = ("raw_message", "body", "html_body")


class EmailSendAttemptInline(admin.TabularInline):
    model = EmailSendAttempt
    extra = 0
    can_delete = False
    fields = ("started_at", "trigger", "succeeded", "error")
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: EmailLog | None = None) -> bool:
        return False


@admin.register(EmailLog)
class EmailLogAdmin(ReadOnlyLogAdmin):
    date_hierarchy = "created_at"
    actions = ("retry_selected",)
    list_display = (
        "created_at",
        "status",
        "from_email",
        "recipients",
        "subject",
        "attempt_count",
    )
    list_filter = ("status", "created_at", RetentionFilter)
    search_fields = ("subject", "from_email", "message_id", RECIPIENTS_SEARCH_FIELD)
    inlines = (EmailSendAttemptInline,)
    readonly_fields = ("raw_message_size",)
    fieldsets = (
        (None, {"fields": ("created_at", "status", "sent_at", "message_id", "context")}),
        (
            _("Envelope"),
            {"fields": ("from_email", "to", "cc", "bcc", "reply_to", "subject")},
        ),
        (
            _("Content"),
            {
                "fields": (
                    "body",
                    "html_body",
                    "headers",
                    "attachments",
                    "body_omission",
                    "raw_message_size",
                )
            },
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        # Recipients live in a JSON list: cast it to text so that admin search
        # can run its LIKE over it on every database backend.
        # The payloads are megabytes the changelist never shows: the detail page
        # loads the one row it needs.
        annotation = {RECIPIENTS_SEARCH_FIELD: Cast("to", TextField())}
        return super().get_queryset(request).defer(*DEFERRED_FIELDS).annotate(**annotation)

    @admin.action(
        description=_("Send the selected messages again"), permissions=["retry"]
    )
    def retry_selected(self, request: HttpRequest, queryset: QuerySet) -> None:
        report = retry_emails(queryset, trigger=EmailSendAttempt.Trigger.ADMIN)
        message_retry_report(self, request, report)

    @admin.display(description=_("to"))
    def recipients(self, log: EmailLog) -> str:
        return ", ".join(log.to)

    @admin.display(description=_("raw MIME size"))
    def raw_message_size(self, log: EmailLog) -> str:
        if log.raw_message is None:
            return log.get_body_omission_display() or _("not stored")
        return filesizeformat(len(log.raw_message))
