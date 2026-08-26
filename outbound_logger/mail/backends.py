"""The email backend that logs, then delegates to the one that really sends."""

import logging
from typing import Any

import django
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.module_loading import import_string

from ..conf import LOGGING_MAIL_BACKEND, get_setting
from .capture import create_log
from .delivery import send_and_record
from .models import EmailSendAttempt

# Django 6.1 warns when a built-in backend is built without an `alias` keyword.
# Passing alias=None asks for the settings-driven behaviour without the warning;
# older versions ignore the keyword.
SUPPORTS_ALIAS = django.VERSION >= (6, 1)

logger = logging.getLogger(__name__)


def build_delegate(**options: Any) -> BaseEmailBackend:
    """Build the backend that really sends, from MAIL_MAILER or from MAIL_BACKEND."""
    mailer_alias = get_setting("MAIL_MAILER")
    if mailer_alias:
        if options:
            raise ImproperlyConfigured(
                f"Options {sorted(options)} cannot be applied to the mailer "
                f"{mailer_alias!r}: declare them in its MAILERS entry instead."
            )
        from django.core.mail import mailers

        return mailers[mailer_alias]

    backend_path = get_setting("MAIL_BACKEND")
    if backend_path == LOGGING_MAIL_BACKEND:
        raise ImproperlyConfigured(
            "OUTBOUND_LOGGER['MAIL_BACKEND'] delegates to the logging backend itself. "
            "Point it at the backend that really sends."
        )

    backend_options = {**get_setting("MAIL_BACKEND_OPTIONS"), **options}
    if SUPPORTS_ALIAS:
        backend_options.setdefault("alias", None)
    return import_string(backend_path)(**backend_options)


class LoggingEmailBackend(BaseEmailBackend):
    """Log every message to the database, with the outcome of its delivery."""

    def __init__(
        self, fail_silently: bool = False, *, alias: str | None = None, **options: Any
    ) -> None:
        # Django hands its own private keywords (_ignore_unknown_kwargs) down with
        # the connection options: they belong to the base class, not to the delegate.
        private = {name: options.pop(name) for name in list(options) if name.startswith("_")}
        super().__init__(alias=alias, **private)
        # Set here rather than left to the base class: Django 6.1 deprecated its
        # own fail_silently and asks subclasses to own the attribute.
        self.fail_silently = fail_silently
        self.delegate = build_delegate(**options)

    def open(self) -> bool | None:
        return self.delegate.open()

    def close(self) -> None:
        self.delegate.close()

    def send_messages(self, email_messages: list[EmailMessage]) -> int:
        # Logged before the connection is opened: a mail server that is down must
        # leave rows behind, not a hole.
        pairs = [(message, self.log_message(message)) for message in email_messages]
        return send_and_record(
            self.delegate,
            pairs,
            trigger=EmailSendAttempt.Trigger.SEND,
            fail_silently=self.fail_silently,
        )

    def log_message(self, message: EmailMessage) -> Any:
        """A message this package cannot record still has to go out."""
        try:
            return create_log(message)
        except Exception:
            logger.exception("could not log a message; sending it unlogged")
            return None
