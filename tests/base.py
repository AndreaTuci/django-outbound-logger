"""Django's test runner points EMAIL_BACKEND at locmem, which would bypass the
logging backend: these cases put ours back."""

from django.test import TestCase, override_settings

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
LOGGING_BACKEND = "outbound_logger.mail.backends.LoggingEmailBackend"


@override_settings(EMAIL_BACKEND=LOGGING_BACKEND)
class MailTestCase(TestCase):
    pass
