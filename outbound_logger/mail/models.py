from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

EMAIL_ADDRESS_MAX_LENGTH = 254  # RFC 5321
SUBJECT_MAX_LENGTH = 998  # RFC 5322 line length limit
MESSAGE_ID_MAX_LENGTH = 255
CHOICE_MAX_LENGTH = 16


class EmailLog(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")

    class BodyOmission(models.TextChoices):
        DISABLED = "disabled", _("Body storage disabled")
        TOO_LARGE = "too_large", _("Message above the size limit")

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    status = models.CharField(
        _("status"),
        max_length=CHOICE_MAX_LENGTH,
        choices=Status.choices,
        default=Status.PENDING,
    )
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    message_id = models.CharField(
        _("message id"), max_length=MESSAGE_ID_MAX_LENGTH, blank=True, db_index=True
    )

    from_email = models.CharField(_("from"), max_length=EMAIL_ADDRESS_MAX_LENGTH)
    to = models.JSONField(_("to"), default=list)
    cc = models.JSONField(_("cc"), default=list, blank=True)
    bcc = models.JSONField(_("bcc"), default=list, blank=True)
    reply_to = models.JSONField(_("reply to"), default=list, blank=True)
    subject = models.CharField(_("subject"), max_length=SUBJECT_MAX_LENGTH, blank=True)

    body = models.TextField(_("body"), blank=True)
    html_body = models.TextField(_("HTML body"), blank=True)
    headers = models.JSONField(_("headers"), default=dict, blank=True)
    attachments = models.JSONField(_("attachments"), default=list, blank=True)
    raw_message = models.BinaryField(
        _("raw MIME message"), null=True, blank=True, editable=False
    )
    body_omission = models.CharField(
        _("body omitted because"),
        max_length=CHOICE_MAX_LENGTH,
        choices=BodyOmission.choices,
        blank=True,
    )
    context = models.JSONField(_("context"), default=dict, blank=True)

    class Meta:
        verbose_name = _("email log")
        verbose_name_plural = _("email logs")
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("status", "created_at"))]

    def __str__(self):
        return f"{self.subject or '(no subject)'} -> {', '.join(self.to)}"

    def why_not_retriable(self):
        """What keeps this message from being sent again, or "" when nothing does."""
        if self.status != self.Status.FAILED:
            return _("only a failed message can be sent again")
        if self.body_omission == self.BodyOmission.DISABLED:
            return _("its body was not stored")
        if self.attachments and self.raw_message is None:
            return _("its attachments were not stored")
        return ""

    @property
    def can_retry(self):
        return not self.why_not_retriable()

    def mark_sent(self, trigger):
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=("status", "sent_at"))
        return self.attempts.create(succeeded=True, trigger=trigger)

    def mark_failed(self, error, trigger):
        self.status = self.Status.FAILED
        self.save(update_fields=("status",))
        return self.attempts.create(succeeded=False, error=error, trigger=trigger)


class EmailSendAttempt(models.Model):
    class Trigger(models.TextChoices):
        SEND = "send", _("Initial send")
        ADMIN = "admin", _("Retry from the admin")
        COMMAND = "command", _("Retry from a management command")
        CODE = "code", _("Retry from code")

    log = models.ForeignKey(
        EmailLog,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name=_("email log"),
    )
    started_at = models.DateTimeField(_("started at"), auto_now_add=True)
    trigger = models.CharField(
        _("trigger"), max_length=CHOICE_MAX_LENGTH, choices=Trigger.choices
    )
    succeeded = models.BooleanField(_("succeeded"))
    error = models.TextField(_("error"), blank=True)

    class Meta:
        verbose_name = _("send attempt")
        verbose_name_plural = _("send attempts")
        ordering = ("-started_at",)

    def __str__(self):
        outcome = _("succeeded") if self.succeeded else _("failed")
        return f"{self.get_trigger_display()}: {outcome}"
