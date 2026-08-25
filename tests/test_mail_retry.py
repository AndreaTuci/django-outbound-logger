from datetime import timedelta
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from django.urls import reverse

from outbound_logger.mail.models import EmailLog, EmailSendAttempt
from outbound_logger.mail.rebuild import rebuild_message
from outbound_logger.mail.retry import retry_emails

from .base import LOCMEM, MailTestCase

EXPLODING = "tests.backends.ExplodingBackend"
HTML = "<p>Hello</p>"


def build_message(**kwargs):
    kwargs.setdefault("subject", "Subject")
    kwargs.setdefault("body", "Body")
    kwargs.setdefault("from_email", "from@example.com")
    kwargs.setdefault("to", ["to@example.com"])
    return mail.EmailMultiAlternatives(**kwargs)


def fail_one(message=None, **settings):
    """Send a message through a backend that refuses it, and return its log."""
    with override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": EXPLODING, **settings}):
        (message or build_message()).send(fail_silently=True)
    return EmailLog.objects.latest("pk")


class RebuildTests(MailTestCase):
    def test_the_envelope_and_the_bodies_come_back(self):
        message = build_message(cc=["cc@example.com"], reply_to=["reply@example.com"])
        message.attach_alternative(HTML, "text/html")

        rebuilt = rebuild_message(fail_one(message))

        self.assertEqual(rebuilt.subject, "Subject")
        self.assertEqual(rebuilt.body, "Body")
        self.assertEqual(rebuilt.to, ["to@example.com"])
        self.assertEqual(rebuilt.cc, ["cc@example.com"])
        self.assertEqual(rebuilt.reply_to, ["reply@example.com"])
        self.assertEqual(rebuilt.alternatives[0][0], HTML)

    def test_the_attachment_comes_back_out_of_the_stored_mime(self):
        message = build_message()
        message.attach("report.csv", "a,b\n", "text/csv")

        rebuilt = rebuild_message(fail_one(message))

        self.assertEqual(len(rebuilt.attachments), 1)
        filename, content, content_type = rebuilt.attachments[0]
        self.assertEqual(filename, "report.csv")
        self.assertEqual(content, "a,b\n")
        self.assertEqual(content_type, "text/csv")

    def test_an_html_only_message_stays_html_only(self):
        message = build_message(body=HTML)
        message.content_subtype = "html"

        rebuilt = rebuild_message(fail_one(message))

        self.assertEqual(rebuilt.content_subtype, "html")
        self.assertEqual(rebuilt.body, HTML)
        self.assertEqual(rebuilt.alternatives, [])


class RetryTests(MailTestCase):
    def test_a_failed_message_goes_out_and_the_log_records_both_tries(self):
        log = fail_one()

        report = retry_emails([log])

        self.assertEqual(report.succeeded, [log])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailLog.objects.count(), 1)  # the retry reuses the row
        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.SENT)
        self.assertEqual(
            list(log.attempts.order_by("pk").values_list("trigger", "succeeded")),
            [(EmailSendAttempt.Trigger.SEND, False), (EmailSendAttempt.Trigger.CODE, True)],
        )

    def test_the_message_keeps_its_identifier(self):
        log = fail_one()

        retry_emails([log])

        self.assertEqual(mail.outbox[0].message()["Message-ID"], log.message_id)

    def test_a_message_that_fails_again_stays_failed(self):
        log = fail_one()

        with override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": EXPLODING}):
            report = retry_emails([log])

        self.assertEqual(report.failed, [log])
        self.assertEqual(log.attempts.count(), 2)
        self.assertIn("SMTPException", log.attempts.latest("pk").error)

    def test_a_sent_message_is_never_sent_twice(self):
        build_message().send()
        log = EmailLog.objects.get()

        report = retry_emails([log])

        self.assertEqual(report.succeeded, [])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(report.skipped[0][0], log)

    def test_a_message_without_a_stored_body_is_skipped(self):
        log = fail_one(STORE_BODY=False)

        report = retry_emails([log])

        self.assertEqual(report.skipped[0][0], log)
        self.assertEqual(mail.outbox, [])

    def test_a_message_without_its_stored_attachments_is_skipped(self):
        message = build_message()
        message.attach("report.csv", "a,b\n", "text/csv")
        log = fail_one(message, MAX_BODY_BYTES=10)

        report = retry_emails([log])

        self.assertEqual(report.skipped[0][0], log)
        self.assertEqual(mail.outbox, [])


class RetryCommandTests(MailTestCase):
    def test_it_sends_the_failed_messages_again(self):
        log = fail_one()

        call_command("retry_failed_emails", stdout=StringIO())

        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.SENT)

    def test_a_dry_run_sends_nothing(self):
        log = fail_one()

        call_command("retry_failed_emails", dry_run=True, stdout=StringIO())

        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.FAILED)
        self.assertEqual(mail.outbox, [])

    def test_it_skips_messages_already_tried_enough_times(self):
        log = fail_one()

        call_command("retry_failed_emails", max_attempts=1, stdout=StringIO())

        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.FAILED)

    def test_it_only_looks_at_the_requested_window(self):
        log = fail_one()
        EmailLog.objects.filter(pk=log.pk).update(
            created_at=timezone.now() - timedelta(days=5)
        )

        call_command("retry_failed_emails", since=1, stdout=StringIO())

        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.FAILED)


class RetryActionTests(MailTestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        cls.staff = User.objects.create_superuser("staff", "staff@example.com", "secret")

    def test_the_admin_action_sends_the_selection_again(self):
        log = fail_one()
        self.client.force_login(self.staff)

        self.client.post(
            reverse("admin:outbound_mail_emaillog_changelist"),
            {"action": "retry_selected", "_selected_action": [log.pk]},
            follow=True,
        )

        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.SENT)
