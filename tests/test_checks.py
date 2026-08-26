from django.test import SimpleTestCase, override_settings

from outbound_logger.conf import check_settings

from .base import LOCMEM, LOGGING_BACKEND


def check_ids():
    return [problem.id for problem in check_settings(app_configs=None)]


class CheckTests(SimpleTestCase):
    @override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": LOCMEM})
    def test_a_sane_configuration_reports_nothing(self):
        self.assertEqual(check_ids(), [])

    @override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": LOCMEM, "STORE_BODIES": True})
    def test_a_misspelled_setting_is_reported(self):
        self.assertEqual(check_ids(), ["outbound_logger.E001"])

    @override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": LOCMEM, "MAIL_MAILER": "smtp"})
    def test_two_delegates_are_reported(self):
        self.assertEqual(check_ids(), ["outbound_logger.E002"])

    @override_settings(
        OUTBOUND_LOGGER={"MAIL_BACKEND": "outbound_logger.mail.backends.LoggingEmailBackend"}
    )
    def test_delegating_to_itself_is_reported(self):
        self.assertEqual(check_ids(), ["outbound_logger.E003"])

    @override_settings(
        OUTBOUND_LOGGER={"MAIL_BACKEND": LOCMEM},
        MAILERS={"default": {"BACKEND": LOGGING_BACKEND}},
    )
    def test_a_mailers_project_without_a_mailer_is_warned(self):
        self.assertEqual(check_ids(), ["outbound_logger.W001"])


class MailBackendCheckTests(SimpleTestCase):
    """The one mistake nothing else would reveal: installed, migrated, idle."""

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend")
    def test_a_project_that_forgot_the_backend_is_warned(self):
        self.assertIn("outbound_logger.W003", check_ids())

    @override_settings(EMAIL_BACKEND="outbound_logger.mail.backends.LoggingEmailBackend")
    def test_the_logging_backend_is_fine(self):
        self.assertNotIn("outbound_logger.W003", check_ids())

    @override_settings(EMAIL_BACKEND="tests.backends.SubclassedLoggingBackend")
    def test_a_subclass_of_it_is_fine_too(self):
        self.assertNotIn("outbound_logger.W003", check_ids())

    @override_settings(EMAIL_BACKEND=LOCMEM)
    def test_the_backend_the_test_runner_installs_is_not_worth_a_warning(self):
        self.assertNotIn("outbound_logger.W003", check_ids())

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        MAILERS={
            "default": {"BACKEND": "outbound_logger.mail.backends.LoggingEmailBackend"}
        },
    )
    def test_a_mailers_project_is_read_from_mailers(self):
        self.assertNotIn("outbound_logger.W003", check_ids())
