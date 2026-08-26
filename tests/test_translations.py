from django.test import SimpleTestCase
from django.utils import translation

from outbound_logger.admin import RetentionFilter
from outbound_logger.http.models import HttpRequestLog
from outbound_logger.mail.models import EmailLog


class ItalianCatalogueTests(SimpleTestCase):
    """The catalogues are compiled files: a test keeps them from going stale."""

    def test_the_mail_log_is_translated(self):
        with translation.override("it"):
            self.assertEqual(str(EmailLog._meta.verbose_name), "log della mail")

    def test_the_http_log_is_translated(self):
        with translation.override("it"):
            self.assertEqual(str(HttpRequestLog._meta.verbose_name), "log della richiesta HTTP")

    def test_what_the_two_apps_share_is_translated_in_both(self):
        with translation.override("it"):
            self.assertEqual(str(RetentionFilter.title), "conservazione")

    def test_english_is_left_alone(self):
        with translation.override("en"):
            self.assertEqual(str(EmailLog._meta.verbose_name), "email log")
