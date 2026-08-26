"""Backends that stand in for a mail server having a bad day."""

from smtplib import SMTPException

from django.core.mail.backends.base import BaseEmailBackend

from outbound_logger.mail.backends import LoggingEmailBackend

FAILURE_MESSAGE = "the server said no"


class ExplodingBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise SMTPException(FAILURE_MESSAGE)


class UnopenableBackend(BaseEmailBackend):
    def open(self):
        raise SMTPException(FAILURE_MESSAGE)

    def send_messages(self, email_messages):
        raise AssertionError("send_messages must not run on an unopened connection")


class SilentBackend(BaseEmailBackend):
    """Accepts everything and sends nothing, like a misconfigured relay."""

    def send_messages(self, email_messages):
        return 0


class UnclosableBackend(BaseEmailBackend):
    """Sends fine, then raises on the way out, like a server erroring on QUIT."""

    def open(self):
        return True

    def send_messages(self, email_messages):
        return len(email_messages)

    def close(self):
        raise SMTPException(FAILURE_MESSAGE)


class SubclassedLoggingBackend(LoggingEmailBackend):
    """What a project wrapping the logging backend would look like."""
