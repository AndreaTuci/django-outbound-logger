"""Django's test runner points EMAIL_BACKEND at locmem, which would bypass the
logging backend: these cases put ours back."""

from django.core import mail
from django.test import TestCase, override_settings

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
LOGGING_BACKEND = "outbound_logger.mail.backends.LoggingEmailBackend"
EXPLODING = "tests.backends.ExplodingBackend"
HTML = "<p>Hello</p>"


def build_message(**kwargs):
    """The message the mail tests send, unless they say otherwise."""
    kwargs.setdefault("subject", "Subject")
    kwargs.setdefault("body", "Body")
    kwargs.setdefault("from_email", "from@example.com")
    kwargs.setdefault("to", ["to@example.com"])
    return mail.EmailMultiAlternatives(**kwargs)


@override_settings(EMAIL_BACKEND=LOGGING_BACKEND)
class MailTestCase(TestCase):
    pass
