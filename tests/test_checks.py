from django.test import SimpleTestCase, override_settings

from outbound_logger.conf import check_settings

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


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

    @override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": LOCMEM}, MAILERS={"default": {}})
    def test_a_mailers_project_without_a_mailer_is_warned(self):
        self.assertEqual(check_ids(), ["outbound_logger.W001"])
