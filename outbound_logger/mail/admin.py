from django.contrib import admin
from django.db.models import TextField
from django.db.models.functions import Cast
from django.template.defaultfilters import filesizeformat
from django.utils.translation import gettext_lazy as _

from ..admin import ReadOnlyLogAdmin
from .models import EmailLog, EmailSendAttempt

RECIPIENTS_SEARCH_FIELD = "_recipients"


class EmailSendAttemptInline(admin.TabularInline):
    model = EmailSendAttempt
    extra = 0
    can_delete = False
    fields = ("started_at", "trigger", "succeeded", "error")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EmailLog)
class EmailLogAdmin(ReadOnlyLogAdmin):
    date_hierarchy = "created_at"
    list_display = ("created_at", "status", "from_email", "recipients", "subject")
    list_filter = ("status", "created_at")
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

    def get_queryset(self, request):
        # Recipients live in a JSON list: cast it to text so that admin search
        # can run its LIKE over it on every database backend.
        annotation = {RECIPIENTS_SEARCH_FIELD: Cast("to", TextField())}
        return super().get_queryset(request).annotate(**annotation)

    @admin.display(description=_("to"))
    def recipients(self, log):
        return ", ".join(log.to)

    @admin.display(description=_("raw MIME size"))
    def raw_message_size(self, log):
        if log.raw_message is None:
            return log.get_body_omission_display() or _("not stored")
        return filesizeformat(len(log.raw_message))
