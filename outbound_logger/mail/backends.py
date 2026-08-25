"""The email backend that logs, then delegates to the one that really sends."""

import traceback

import django
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend
from django.utils.module_loading import import_string

from ..conf import LOGGING_MAIL_BACKEND, get_setting
from .capture import create_log
from .models import EmailSendAttempt

# Django 6.1 warns when a built-in backend is built without an `alias` keyword.
# Passing alias=None asks for the settings-driven behaviour without the warning;
# older versions ignore the keyword.
SUPPORTS_ALIAS = django.VERSION >= (6, 1)

NOTHING_SENT = "The backend accepted the message but reported nothing sent."
TRIGGER = EmailSendAttempt.Trigger.SEND


def build_delegate(**options):
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

    def __init__(self, fail_silently=False, *, alias=None, **options):
        super().__init__(alias=alias)
        # Set here rather than left to the base class: Django 6.1 deprecated its
        # own fail_silently and asks subclasses to own the attribute.
        self.fail_silently = fail_silently
        self.delegate = build_delegate(**options)

    def open(self):
        return self.delegate.open()

    def close(self):
        self.delegate.close()

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        # Logged before opening the connection: a mail server that is down must
        # leave a row behind, not a hole.
        logs = [create_log(message) for message in email_messages]

        try:
            new_connection = self.delegate.open()
        except Exception:
            error = traceback.format_exc()
            for log in logs:
                log.mark_failed(error, trigger=TRIGGER)
            if not self.fail_silently:
                raise
            return 0

        try:
            return self.deliver(email_messages, logs)
        finally:
            if new_connection:
                self.delegate.close()

    def deliver(self, email_messages, logs):
        """One message at a time, so every log gets its own outcome."""
        sent = 0
        for message, log in zip(email_messages, logs):
            try:
                delivered = self.delegate.send_messages([message])
            except Exception:
                log.mark_failed(traceback.format_exc(), trigger=TRIGGER)
                if not self.fail_silently:
                    raise
                continue

            if delivered:
                log.mark_sent(trigger=TRIGGER)
                sent += 1
            else:
                log.mark_failed(NOTHING_SENT, trigger=TRIGGER)
        return sent
