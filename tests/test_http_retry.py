from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from requests.exceptions import ConnectionError

from outbound_logger.http.models import BodyOmission, HttpRequestAttempt, HttpRequestLog
from outbound_logger.http.retry import retry_requests
from outbound_logger.http.session import LoggedSession

from .stubs import StubAdapter, build_stub_session

URL = "https://api.example.com/things"
CHANGELIST_URL = reverse("admin:outbound_http_httprequestlog_changelist")
WITH_FACTORY = override_settings(
    OUTBOUND_LOGGER={"HTTP_SESSION_FACTORY": "tests.stubs.build_stub_session"}
)


def failed_call(method="get", **kwargs):
    """Make a call that never reaches anybody, and return its log."""
    session = LoggedSession()
    session.mount("https://", StubAdapter(error=ConnectionError))
    try:
        getattr(session, method)(URL, **kwargs)
    except ConnectionError:
        pass
    return HttpRequestLog.objects.latest("pk")


def stub_session(adapter=None):
    session = build_stub_session()
    if adapter:
        session.mount("https://", adapter)
    return session


class RetryTests(TestCase):
    def test_a_failed_request_is_answered_the_second_time(self):
        log = failed_call()

        report = retry_requests([log], session=stub_session())

        self.assertEqual(report.succeeded, [log])
        self.assertEqual(HttpRequestLog.objects.count(), 1)  # the retry reuses the row
        log.refresh_from_db()
        self.assertEqual(log.status, HttpRequestLog.Status.COMPLETED)
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.response_body, '{"ok": true}')

    def test_both_tries_are_kept(self):
        log = failed_call()

        retry_requests([log], session=stub_session())

        self.assertEqual(
            list(log.attempts.order_by("pk").values_list("trigger", "status_code")),
            [(HttpRequestAttempt.Trigger.REQUEST, None), (HttpRequestAttempt.Trigger.CODE, 200)],
        )

    def test_the_session_puts_the_credentials_back(self):
        log = failed_call()
        log.request_headers["Authorization"] = "[redacted]"
        log.save()
        adapter = StubAdapter()

        retry_requests([log], session=stub_session(adapter))

        sent = adapter.received[-1]
        self.assertEqual(sent.headers["Authorization"], "Bearer the-real-one")

    def test_a_server_error_counts_as_a_failure(self):
        log = failed_call()

        report = retry_requests([log], session=stub_session(StubAdapter(status_code=503)))

        self.assertEqual(report.failed, [log])
        log.refresh_from_db()
        self.assertEqual(log.status_code, 503)

    def test_a_request_that_never_answers_stays_failed(self):
        log = failed_call()

        report = retry_requests(
            [log], session=stub_session(StubAdapter(error=ConnectionError))
        )

        self.assertEqual(report.failed, [log])
        log.refresh_from_db()
        self.assertEqual(log.status, HttpRequestLog.Status.FAILED)
        self.assertIsNone(log.status_code)

    def test_a_post_is_skipped_unless_it_was_marked(self):
        log = failed_call("post", json={"name": "thing"})

        report = retry_requests([log], session=stub_session())

        self.assertEqual(report.skipped[0][0], log)

    def test_a_marked_post_is_replayed_with_its_body(self):
        log = failed_call("post", json={"name": "thing"}, retriable=True)
        adapter = StubAdapter()

        report = retry_requests([log], session=stub_session(adapter))

        self.assertEqual(report.succeeded, [log])
        self.assertEqual(adapter.received[-1].body, b'{"name": "thing"}')

    def test_a_request_without_its_body_is_skipped(self):
        log = failed_call("put", data="x" * 100)
        log.request_body = ""
        log.request_body_omission = BodyOmission.TOO_LARGE
        log.save()

        report = retry_requests([log], session=stub_session())

        self.assertEqual(report.skipped[0][0], log)


@WITH_FACTORY
class RetryCommandTests(TestCase):
    def test_it_sends_the_failed_requests_again(self):
        log = failed_call()

        call_command("retry_failed_requests", stdout=StringIO())

        log.refresh_from_db()
        self.assertEqual(log.status, HttpRequestLog.Status.COMPLETED)

    def test_a_dry_run_sends_nothing(self):
        log = failed_call()

        call_command("retry_failed_requests", dry_run=True, stdout=StringIO())

        log.refresh_from_db()
        self.assertEqual(log.status, HttpRequestLog.Status.FAILED)

    def test_server_errors_are_left_alone_unless_asked_for(self):
        log = failed_call()
        log.mark_completed(
            {"status_code": 503, "reason": "Service Unavailable"},
            1,
            HttpRequestAttempt.Trigger.REQUEST,
        )

        call_command("retry_failed_requests", stdout=StringIO())
        log.refresh_from_db()
        self.assertEqual(log.status_code, 503)

        call_command("retry_failed_requests", include_server_errors=True, stdout=StringIO())
        log.refresh_from_db()
        self.assertEqual(log.status_code, 200)


@WITH_FACTORY
class RetryActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("staff", "staff@example.com", "secret")

    def test_the_admin_action_sends_the_selection_again(self):
        log = failed_call()
        self.client.force_login(self.staff)

        self.client.post(
            CHANGELIST_URL,
            {"action": "retry_selected", "_selected_action": [log.pk]},
            follow=True,
        )

        log.refresh_from_db()
        self.assertEqual(log.status, HttpRequestLog.Status.COMPLETED)
