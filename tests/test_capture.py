from django.core import mail
from django.test import override_settings

from outbound_logger.mail.capture import CONTEXT_ATTRIBUTE, CONTEXT_HEADER
from outbound_logger.mail.models import EmailLog

from .base import HTML, LOCMEM, MailTestCase, build_message

class CaptureTests(MailTestCase):
    def test_the_logged_message_id_is_the_delivered_one(self):
        build_message().send()

        log = EmailLog.objects.get()
        self.assertTrue(log.message_id)
        self.assertEqual(mail.outbox[0].message()["Message-ID"], log.message_id)

    def test_the_html_alternative_is_captured(self):
        message = build_message()
        message.attach_alternative(HTML, "text/html")
        message.send()

        log = EmailLog.objects.get()
        self.assertEqual(log.body, "Body")
        self.assertEqual(log.html_body, HTML)

    def test_an_html_only_message_is_captured_as_html(self):
        message = build_message(body=HTML)
        message.content_subtype = "html"
        message.send()

        log = EmailLog.objects.get()
        self.assertEqual(log.body, "")
        self.assertEqual(log.html_body, HTML)

    def test_attachments_are_described_and_kept_in_the_raw_message(self):
        message = build_message()
        message.attach("report.csv", b"a,b\n", "text/csv")
        message.send()

        log = EmailLog.objects.get()
        self.assertEqual(
            log.attachments,
            [{"filename": "report.csv", "content_type": "text/csv", "size": 4}],
        )
        self.assertIn(b"report.csv", bytes(log.raw_message))

    def test_the_envelope_is_captured_in_full(self):
        build_message(
            cc=["cc@example.com"], bcc=["bcc@example.com"], reply_to=["reply@example.com"]
        ).send()

        log = EmailLog.objects.get()
        self.assertEqual(log.cc, ["cc@example.com"])
        self.assertEqual(log.bcc, ["bcc@example.com"])
        self.assertEqual(log.reply_to, ["reply@example.com"])


class ContextTests(MailTestCase):
    def test_the_context_attribute_is_stored(self):
        message = build_message()
        setattr(message, CONTEXT_ATTRIBUTE, {"contact_id": 12})
        message.send()

        self.assertEqual(EmailLog.objects.get().context, {"contact_id": 12})

    def test_the_context_header_is_stored_and_never_delivered(self):
        build_message(headers={CONTEXT_HEADER: '{"contact_id": 12}'}).send()

        self.assertEqual(EmailLog.objects.get().context, {"contact_id": 12})
        self.assertIsNone(mail.outbox[0].message()[CONTEXT_HEADER])

    def test_a_malformed_context_header_does_not_stop_the_message(self):
        """The logger is never the reason a message fails to go out."""
        message = build_message(headers={CONTEXT_HEADER: "not json"})

        with self.assertLogs("outbound_logger.mail.backends", level="ERROR"):
            message.send()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailLog.objects.count(), 0)


@override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": LOCMEM, "STORE_BODY": False})
class BodyStorageDisabledTests(MailTestCase):
    def test_only_the_metadata_is_stored(self):
        build_message().send()

        log = EmailLog.objects.get()
        self.assertEqual(log.subject, "Subject")
        self.assertEqual(log.body, "")
        self.assertIsNone(log.raw_message)
        self.assertEqual(log.body_omission, EmailLog.BodyOmission.DISABLED)


@override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": LOCMEM, "MAX_BODY_BYTES": 10})
class BodySizeLimitTests(MailTestCase):
    def test_an_oversized_message_keeps_its_fields_but_loses_the_mime(self):
        build_message().send()

        log = EmailLog.objects.get()
        self.assertEqual(log.body, "Body")
        self.assertIsNone(log.raw_message)
        self.assertEqual(log.body_omission, EmailLog.BodyOmission.TOO_LARGE)
