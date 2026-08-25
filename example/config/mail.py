"""The mail server of the example: a console backend with a bad day."""

from smtplib import SMTPException

from django.core.mail.backends.base import BaseEmailBackend

FLAKY_RECIPIENT = "flaky@example.com"

# The flaky server refuses each message once and accepts it on the second try,
# which is exactly what the retry needs to be worth watching.
refused_once = set()


class FlakyBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        for message in email_messages:
            if FLAKY_RECIPIENT in message.to and message.subject not in refused_once:
                refused_once.add(message.subject)
                raise SMTPException("the server refused the message, try again later")
            print(message.message().as_string())
        return len(email_messages)
