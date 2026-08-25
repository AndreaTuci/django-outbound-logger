"""Backends that stand in for a mail server having a bad day."""

from smtplib import SMTPException

from django.core.mail.backends.base import BaseEmailBackend

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
