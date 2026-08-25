from smtplib import SMTPException

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from outbound_logger.mail.backends import NOTHING_SENT, LoggingEmailBackend
from outbound_logger.mail.models import EmailLog, EmailSendAttempt

from .backends import FAILURE_MESSAGE
from .base import LOCMEM, MailTestCase


def send_one(fail_silently=False):
    return mail.send_mail(
        subject="Subject",
        message="Body",
        from_email="from@example.com",
        recipient_list=["to@example.com"],
        fail_silently=fail_silently,
    )


class SuccessfulSendTests(MailTestCase):
    def test_the_message_is_logged_as_sent(self):
        sent = send_one()

        log = EmailLog.objects.get()
        self.assertEqual(sent, 1)
        self.assertEqual(log.status, EmailLog.Status.SENT)
        self.assertIsNotNone(log.sent_at)
        self.assertEqual(log.from_email, "from@example.com")
        self.assertEqual(log.to, ["to@example.com"])
        self.assertEqual(log.subject, "Subject")
        self.assertEqual(log.body, "Body")

    def test_the_send_leaves_one_successful_attempt(self):
        send_one()

        attempt = EmailSendAttempt.objects.get()
        self.assertTrue(attempt.succeeded)
        self.assertEqual(attempt.trigger, EmailSendAttempt.Trigger.SEND)
        self.assertEqual(attempt.error, "")

    def test_every_message_of_a_batch_gets_its_own_log(self):
        messages = [
            mail.EmailMessage("One", "Body", "from@example.com", ["one@example.com"]),
            mail.EmailMessage("Two", "Body", "from@example.com", ["two@example.com"]),
        ]

        with mail.get_connection() as connection:
            connection.send_messages(messages)

        self.assertEqual(EmailLog.objects.count(), 2)
        self.assertEqual(EmailLog.objects.filter(status=EmailLog.Status.SENT).count(), 2)


@override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": "tests.backends.ExplodingBackend"})
class FailedSendTests(MailTestCase):
    def test_the_failure_is_logged_and_raised(self):
        with self.assertRaises(SMTPException):
            send_one()

        log = EmailLog.objects.get()
        self.assertEqual(log.status, EmailLog.Status.FAILED)
        self.assertIsNone(log.sent_at)
        self.assertIn(FAILURE_MESSAGE, log.attempts.get().error)

    def test_a_silenced_failure_is_still_logged(self):
        sent = send_one(fail_silently=True)

        self.assertEqual(sent, 0)
        self.assertEqual(EmailLog.objects.get().status, EmailLog.Status.FAILED)


@override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": "tests.backends.UnopenableBackend"})
class UnreachableServerTests(MailTestCase):
    def test_a_connection_that_never_opens_fails_every_message(self):
        messages = [
            mail.EmailMessage("One", "Body", "from@example.com", ["one@example.com"]),
            mail.EmailMessage("Two", "Body", "from@example.com", ["two@example.com"]),
        ]

        with self.assertRaises(SMTPException):
            mail.get_connection().send_messages(messages)

        self.assertEqual(EmailLog.objects.count(), 2)
        self.assertEqual(EmailLog.objects.filter(status=EmailLog.Status.FAILED).count(), 2)


@override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": "tests.backends.SilentBackend"})
class SilentBackendTests(MailTestCase):
    def test_a_backend_that_sends_nothing_is_a_failure(self):
        sent = send_one()

        log = EmailLog.objects.get()
        self.assertEqual(sent, 0)
        self.assertEqual(log.status, EmailLog.Status.FAILED)
        self.assertEqual(log.attempts.get().error, NOTHING_SENT)


class MisconfigurationTests(SimpleTestCase):
    @override_settings(
        OUTBOUND_LOGGER={"MAIL_BACKEND": "outbound_logger.mail.backends.LoggingEmailBackend"}
    )
    def test_delegating_to_itself_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            LoggingEmailBackend()

    @override_settings(OUTBOUND_LOGGER={"MAIL_MAILER": "smtp", "MAIL_BACKEND": LOCMEM})
    def test_per_connection_options_are_refused_with_a_mailer(self):
        with self.assertRaises(ImproperlyConfigured):
            LoggingEmailBackend(timeout=10)
