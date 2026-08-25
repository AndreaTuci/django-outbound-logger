from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from outbound_logger.http.models import HttpRequestLog
from outbound_logger.http.purge import purge_http_logs
from outbound_logger.mail.models import EmailLog, EmailSendAttempt
from outbound_logger.mail.purge import purge_email_logs

CHANGELIST_URL = reverse("admin:outbound_mail_emaillog_changelist")


def log_created_days_ago(days, subject):
    log = EmailLog.objects.create(
        from_email="from@example.com", to=["to@example.com"], subject=subject
    )
    log.mark_failed("boom", trigger=EmailSendAttempt.Trigger.SEND)
    EmailLog.objects.filter(pk=log.pk).update(
        created_at=timezone.now() - timedelta(days=days)
    )
    return log


class PurgeTests(TestCase):
    def setUp(self):
        self.old = log_created_days_ago(120, "Old")
        self.recent = log_created_days_ago(10, "Recent")

    def test_it_deletes_what_is_past_the_default_window(self):
        deleted = purge_email_logs()

        self.assertEqual(deleted, 1)
        self.assertEqual(list(EmailLog.objects.all()), [self.recent])

    def test_the_attempts_go_with_their_log(self):
        purge_email_logs()

        self.assertEqual(EmailSendAttempt.objects.count(), 1)

    def test_the_window_can_be_given_explicitly(self):
        deleted = purge_email_logs(older_than_days=5)

        self.assertEqual(deleted, 2)
        self.assertEqual(EmailLog.objects.count(), 0)

    @override_settings(
        OUTBOUND_LOGGER={
            "MAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            "RETENTION_DAYS": 365,
        }
    )
    def test_a_longer_window_keeps_everything(self):
        self.assertEqual(purge_email_logs(), 0)
        self.assertEqual(EmailLog.objects.count(), 2)


class PurgeCommandTests(TestCase):
    def setUp(self):
        self.old = log_created_days_ago(120, "Old")
        self.recent = log_created_days_ago(10, "Recent")

    def test_it_deletes_the_expired_logs(self):
        out = StringIO()

        call_command("purge_email_logs", stdout=out)

        self.assertIn("1 log(s)", out.getvalue())
        self.assertEqual(list(EmailLog.objects.all()), [self.recent])

    def test_a_dry_run_deletes_nothing(self):
        out = StringIO()

        call_command("purge_email_logs", dry_run=True, stdout=out)

        self.assertIn("1 log(s)", out.getvalue())
        self.assertEqual(EmailLog.objects.count(), 2)

    def test_the_window_can_be_given_on_the_command_line(self):
        call_command("purge_email_logs", days=5, stdout=StringIO())

        self.assertEqual(EmailLog.objects.count(), 0)


class RetentionFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("staff", "staff@example.com", "secret")

    def setUp(self):
        self.client.force_login(self.staff)
        log_created_days_ago(120, "Old")
        log_created_days_ago(10, "Recent")

    def test_it_lists_only_the_logs_the_purge_would_delete(self):
        response = self.client.get(CHANGELIST_URL, {"expired": "expired"})

        self.assertContains(response, "Old")
        self.assertNotContains(response, "Recent")

    def test_without_it_everything_is_listed(self):
        response = self.client.get(CHANGELIST_URL)

        self.assertContains(response, "Old")
        self.assertContains(response, "Recent")

    def test_the_standard_delete_action_is_offered(self):
        response = self.client.get(CHANGELIST_URL)

        self.assertContains(response, "delete_selected")


def http_log_created_days_ago(days, url):
    log = HttpRequestLog.objects.create(
        status=HttpRequestLog.Status.FAILED, method="GET", url=url
    )
    HttpRequestLog.objects.filter(pk=log.pk).update(
        created_at=timezone.now() - timedelta(days=days)
    )
    return log


class HttpPurgeTests(TestCase):
    def setUp(self):
        self.old = http_log_created_days_ago(120, "https://api.example.com/old")
        self.recent = http_log_created_days_ago(10, "https://api.example.com/recent")

    def test_the_same_window_applies_to_the_http_logs(self):
        deleted = purge_http_logs()

        self.assertEqual(deleted, 1)
        self.assertEqual(list(HttpRequestLog.objects.all()), [self.recent])

    def test_the_command_deletes_them(self):
        call_command("purge_http_logs", stdout=StringIO())

        self.assertEqual(list(HttpRequestLog.objects.all()), [self.recent])

    def test_the_command_can_be_told_the_window(self):
        call_command("purge_http_logs", days=5, stdout=StringIO())

        self.assertEqual(HttpRequestLog.objects.count(), 0)
