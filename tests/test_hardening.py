"""What the adversarial review turned up: the package must never be the reason
a message or a request fails, must never store more than a column can hold, and
must never send again what it cannot rebuild."""

from email.message import MIMEPart
from io import StringIO

import django
from django.contrib.auth.models import Permission, User
from django.core import mail
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from requests.exceptions import ConnectionError

from outbound_logger.conf import ROUTER, check_settings
from outbound_logger.http.models import BodyOmission, HttpRequestLog
from outbound_logger.http.session import LoggedSession
from outbound_logger.mail.capture import describe_attachment
from outbound_logger.mail.models import SUBJECT_MAX_LENGTH, EmailLog
from outbound_logger.http.retry import retry_requests
from outbound_logger.mail.retry import retry_emails
from outbound_logger.routers import OutboundLoggerRouter

from .base import LOCMEM, LOGGING_BACKEND, MailTestCase
from .stubs import StubAdapter, build_stub_session

URL = "https://api.example.com/things"
EXPLODING = "tests.backends.ExplodingBackend"


class BareFailure(Exception):
    """An error carrying no .request, as anything but requests would raise."""


def build_message(**kwargs):
    kwargs.setdefault("subject", "Subject")
    kwargs.setdefault("body", "Body")
    kwargs.setdefault("from_email", "from@example.com")
    kwargs.setdefault("to", ["to@example.com"])
    return mail.EmailMultiAlternatives(**kwargs)


def logged_session(adapter=None, **options):
    session = LoggedSession(**options)
    session.mount("https://", adapter or StubAdapter())
    return session


class TheLoggerNeverStopsTheMailTests(MailTestCase):
    def test_a_message_that_cannot_be_logged_still_goes_out(self):
        good, bad = build_message(subject="good"), build_message(subject="bad\nheader")

        with self.assertLogs("outbound_logger.mail.backends", level="ERROR"):
            mail.get_connection(fail_silently=True).send_messages([good, bad])

        self.assertEqual([message.subject for message in mail.outbox], ["good"])
        self.assertEqual([log.subject for log in EmailLog.objects.all()], ["good"])

    @override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": "tests.backends.UnclosableBackend"})
    def test_a_connection_that_fails_to_close_does_not_sink_the_send(self):
        with self.assertLogs("outbound_logger.mail.delivery", level="ERROR"):
            sent = build_message().send()

        self.assertEqual(sent, 1)
        self.assertEqual(EmailLog.objects.get().status, EmailLog.Status.SENT)


@override_settings(EMAIL_BACKEND=LOGGING_BACKEND)
class DjangoMailersTests(TestCase):
    """Django 6.1 hands its own private keywords down with the connection options."""

    @override_settings(
        MAILERS={
            "default": {"BACKEND": LOGGING_BACKEND},
            "sender": {"BACKEND": LOCMEM},
        },
        OUTBOUND_LOGGER={"MAIL_MAILER": "sender"},
    )
    def test_a_silenced_send_works_with_mailers(self):
        if django.VERSION < (6, 1):
            self.skipTest("MAILERS arrived in Django 6.1")

        mail.send_mail("Subject", "Body", "from@example.com", ["to@example.com"], fail_silently=True)

        self.assertEqual(EmailLog.objects.get().status, EmailLog.Status.SENT)


class AttachmentTests(SimpleTestCase):
    def test_a_mime_part_attachment_is_described_not_crashed(self):
        part = MIMEPart()
        part.set_content("a,b\n", subtype="csv")
        part.add_header("Content-Disposition", "attachment", filename="report.csv")

        described = describe_attachment(part)

        self.assertEqual(described["filename"], "report.csv")
        self.assertEqual(described["content_type"], "text/csv")


class ColumnTests(MailTestCase):
    def test_a_subject_longer_than_its_column_is_cut(self):
        build_message(subject="x" * 2000).send()

        self.assertEqual(len(EmailLog.objects.get().subject), SUBJECT_MAX_LENGTH)

    def test_a_nul_byte_never_reaches_the_database(self):
        logged_session(StubAdapter(content=b'{"a\x00b": 1}')).get(URL)

        self.assertEqual(HttpRequestLog.objects.get().response_body, '{"ab": 1}')


class WhatCannotBeReplayedTests(TestCase):
    def test_a_request_that_was_never_prepared_is_not_retriable(self):
        session = logged_session(StubAdapter(error=BareFailure))

        with self.assertRaises(BareFailure):
            session.put(URL, data="a body that is now lost")

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.request_body_omission, BodyOmission.UNPREPARED)
        self.assertFalse(log.can_retry)

    def test_a_replayed_post_is_not_downgraded_by_a_redirect(self):
        """Following it would turn the POST into a bodyless GET, and its 200 would
        hide the failure being retried."""
        logged_session(retriable=True).post(URL, json={"name": "thing"})
        log = HttpRequestLog.objects.get()
        redirecting = StubAdapter(
            status_code=302, headers={"Location": "https://api.example.com/elsewhere"}
        )

        report = retry_requests([log], session=build_stub_session_with(redirecting))

        self.assertEqual(len(redirecting.received), 1)  # not followed
        self.assertEqual(report.succeeded, [log])
        log.refresh_from_db()
        self.assertEqual(log.status_code, 302)


def build_stub_session_with(adapter):
    session = build_stub_session()
    session.mount("https://", adapter)
    return session


class SessionOptionsTests(TestCase):
    def test_a_session_wide_stream_is_honoured(self):
        session = logged_session()
        session.stream = True

        session.get(URL)

        self.assertEqual(
            HttpRequestLog.objects.get().response_body_omission, BodyOmission.STREAMED
        )

    def test_a_bytes_header_is_stored_as_text(self):
        logged_session().get(URL, headers={"X-Trace": b"abc"})

        self.assertEqual(HttpRequestLog.objects.get().request_headers["X-Trace"], "abc")


class RetryPermissionTests(MailTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user("viewer", password="secret", is_staff=True)
        cls.viewer.user_permissions.add(
            Permission.objects.get(codename="view_emaillog"),
        )

    def test_a_viewer_cannot_send_messages_again(self):
        with override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": EXPLODING}):
            build_message().send(fail_silently=True)
        log = EmailLog.objects.get()
        self.client.force_login(self.viewer)

        response = self.client.post(
            reverse("admin:outbound_mail_emaillog_changelist"),
            {"action": "retry_selected", "_selected_action": [log.pk]},
            follow=True,
        )

        log.refresh_from_db()
        self.assertEqual(log.status, EmailLog.Status.FAILED)
        self.assertEqual(mail.outbox, [])
        self.assertNotContains(response, "retry_selected")


class LogDatabaseTests(SimpleTestCase):
    @override_settings(OUTBOUND_LOGGER={"DATABASE": "default"}, DATABASE_ROUTERS=[ROUTER])
    def test_the_default_alias_is_refused(self):
        self.assertEqual(
            [problem.id for problem in check_settings(app_configs=None)],
            ["outbound_logger.E005"],
        )

    @override_settings(OUTBOUND_LOGGER={"DATABASE": "default"})
    def test_the_router_ignores_it_rather_than_blocking_every_app(self):
        router = OutboundLoggerRouter()

        self.assertIsNone(router.alias())
        self.assertIsNone(router.allow_migrate("default", "auth"))


class CommandLimitTests(MailTestCase):
    def test_max_attempts_zero_retries_nothing(self):
        with override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": EXPLODING}):
            build_message().send(fail_silently=True)

        call_command("retry_failed_emails", max_attempts=0, stdout=StringIO())

        self.assertEqual(EmailLog.objects.get().status, EmailLog.Status.FAILED)
        self.assertEqual(mail.outbox, [])


class AlternativeTests(MailTestCase):
    def test_a_calendar_invitation_survives_the_retry(self):
        message = build_message()
        message.attach_alternative("<p>Hi</p>", "text/html")
        message.attach_alternative("BEGIN:VCALENDAR\nEND:VCALENDAR", "text/calendar")
        with override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": EXPLODING}):
            message.send(fail_silently=True)
        log = EmailLog.objects.latest("pk")

        retry_emails([log])

        sent = mail.outbox[0]
        self.assertEqual(
            sorted(mimetype for _content, mimetype in sent.alternatives),
            ["text/calendar", "text/html"],
        )
        self.assertIn("VCALENDAR", str(sent.message()))


class UrlCredentialTests(TestCase):
    def test_credentials_in_the_url_are_not_stored(self):
        session = LoggedSession()
        session.mount("https://", StubAdapter())

        session.get("https://carl:hunter2@api.example.com/things")

        url = HttpRequestLog.objects.get().url
        self.assertNotIn("hunter2", url)
        self.assertEqual(url, "https://[redacted]@api.example.com/things")


class TheActionTouchesOnlyTheSelectionTests(MailTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("boss", "boss@example.com", "secret")

    def test_only_the_selected_message_is_sent_again(self):
        with override_settings(OUTBOUND_LOGGER={"MAIL_BACKEND": EXPLODING}):
            build_message(subject="chosen").send(fail_silently=True)
            build_message(subject="left alone").send(fail_silently=True)
        chosen = EmailLog.objects.get(subject="chosen")
        self.client.force_login(self.staff)

        self.client.post(
            reverse("admin:outbound_mail_emaillog_changelist"),
            {"action": "retry_selected", "_selected_action": [chosen.pk]},
            follow=True,
        )

        self.assertEqual([message.subject for message in mail.outbox], ["chosen"])
        self.assertEqual(
            EmailLog.objects.get(subject="left alone").status, EmailLog.Status.FAILED
        )
