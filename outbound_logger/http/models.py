from typing import Any

from django.db import models
from django.utils.translation import gettext_lazy as _

METHOD_MAX_LENGTH = 10
REASON_MAX_LENGTH = 255
CHOICE_MAX_LENGTH = 16


class BodyOmission(models.TextChoices):
    DISABLED = "disabled", _("Body storage disabled")
    TOO_LARGE = "too_large", _("Body above the size limit")
    BINARY = "binary", _("Body is not text")
    STREAMED = "streamed", _("Body was streamed")


# What a log holds when no response ever came back.
NO_RESPONSE: dict[str, Any] = {
    "status_code": None,
    "reason": "",
    "response_headers": {},
    "response_body": "",
    "response_body_omission": "",
    "response_truncated": False,
}


class HttpRequestLog(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    status = models.CharField(
        _("status"), max_length=CHOICE_MAX_LENGTH, choices=Status.choices
    )
    duration_ms = models.PositiveIntegerField(_("duration (ms)"), null=True, blank=True)

    method = models.CharField(_("method"), max_length=METHOD_MAX_LENGTH)
    url = models.TextField(_("url"))
    request_headers = models.JSONField(_("request headers"), default=dict, blank=True)
    request_body = models.TextField(_("request body"), blank=True)
    request_body_omission = models.CharField(
        _("request body omitted because"),
        max_length=CHOICE_MAX_LENGTH,
        choices=BodyOmission.choices,
        blank=True,
    )
    retriable = models.BooleanField(_("retriable"), default=False)
    context = models.JSONField(_("context"), default=dict, blank=True)

    status_code = models.PositiveSmallIntegerField(
        _("status code"), null=True, blank=True
    )
    reason = models.CharField(_("reason"), max_length=REASON_MAX_LENGTH, blank=True)
    response_headers = models.JSONField(_("response headers"), default=dict, blank=True)
    response_body = models.TextField(_("response body"), blank=True)
    response_body_omission = models.CharField(
        _("response body omitted because"),
        max_length=CHOICE_MAX_LENGTH,
        choices=BodyOmission.choices,
        blank=True,
    )
    response_truncated = models.BooleanField(_("response truncated"), default=False)

    class Meta:
        verbose_name = _("HTTP request log")
        verbose_name_plural = _("HTTP request logs")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("status_code",)),
        ]

    def __str__(self) -> str:
        return f"{self.method} {self.url}"

    @property
    def is_error(self) -> bool:
        return self.status == self.Status.FAILED or (self.status_code or 0) >= 400

    def why_not_retriable(self) -> str:
        """What keeps this request from being sent again, or "" when nothing does."""
        if not self.retriable:
            return _("this request is not marked as retriable")
        if self.request_body_omission:
            return _("its body was not stored")
        return ""

    @property
    def can_retry(self) -> bool:
        return not self.why_not_retriable()

    def mark_completed(
        self, response_fields: dict[str, Any], duration_ms: int, trigger: str
    ) -> "HttpRequestAttempt":
        self.update(
            status=self.Status.COMPLETED, duration_ms=duration_ms, **response_fields
        )
        return self.attempts.create(trigger=trigger, status_code=self.status_code)

    def mark_failed(
        self, error: str, duration_ms: int, trigger: str
    ) -> "HttpRequestAttempt":
        self.update(status=self.Status.FAILED, duration_ms=duration_ms, **NO_RESPONSE)
        return self.attempts.create(trigger=trigger, error=error)

    def update(self, **fields: Any) -> None:
        for name, value in fields.items():
            setattr(self, name, value)
        self.save()


class HttpRequestAttempt(models.Model):
    class Trigger(models.TextChoices):
        REQUEST = "request", _("Initial request")
        ADMIN = "admin", _("Retry from the admin")
        COMMAND = "command", _("Retry from a management command")
        CODE = "code", _("Retry from code")

    log = models.ForeignKey(
        HttpRequestLog,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name=_("HTTP request log"),
    )
    started_at = models.DateTimeField(_("started at"), auto_now_add=True)
    trigger = models.CharField(
        _("trigger"), max_length=CHOICE_MAX_LENGTH, choices=Trigger.choices
    )
    status_code = models.PositiveSmallIntegerField(
        _("status code"), null=True, blank=True
    )
    error = models.TextField(_("error"), blank=True)

    class Meta:
        verbose_name = _("request attempt")
        verbose_name_plural = _("request attempts")
        ordering = ("-started_at",)

    def __str__(self) -> str:
        outcome = self.status_code or _("no response")
        return f"{self.get_trigger_display()}: {outcome}"
