from requests.exceptions import ConnectionError

from django.test import TestCase, override_settings

from outbound_logger.http.models import BodyOmission, HttpRequestAttempt, HttpRequestLog
from outbound_logger.http.redaction import REDACTED

from .stubs import URL, StubAdapter, build_session


class RequestLoggingTests(TestCase):
    def test_a_call_is_logged_with_its_response(self):
        build_session().get(URL)

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.status, HttpRequestLog.Status.COMPLETED)
        self.assertEqual(log.method, "GET")
        self.assertEqual(log.url, URL)
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.response_body, '{"ok": true}')
        self.assertIsNotNone(log.duration_ms)

    def test_the_call_leaves_an_attempt_behind(self):
        build_session().get(URL)

        attempt = HttpRequestAttempt.objects.get()
        self.assertEqual(attempt.trigger, HttpRequestAttempt.Trigger.REQUEST)
        self.assertEqual(attempt.status_code, 200)

    def test_the_request_body_is_stored(self):
        build_session().post(URL, json={"name": "thing"})

        self.assertEqual(HttpRequestLog.objects.get().request_body, '{"name": "thing"}')

    def test_credentials_never_reach_the_database(self):
        build_session().get(URL, headers={"Authorization": "Bearer super-secret"})

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.request_headers["Authorization"], REDACTED)
        self.assertEqual(log.response_headers["Set-Cookie"], REDACTED)
        self.assertNotIn("super-secret", str(log.request_headers))

    def test_a_failure_is_logged_and_raised_again(self):
        session = build_session(StubAdapter(error=ConnectionError))

        with self.assertRaises(ConnectionError):
            session.get(URL)

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.status, HttpRequestLog.Status.FAILED)
        self.assertEqual(log.method, "GET")
        self.assertIsNone(log.status_code)
        self.assertIn("ConnectionError", log.attempts.get().error)


class RetriableTests(TestCase):
    def test_an_idempotent_method_is_retriable(self):
        build_session().get(URL)

        self.assertTrue(HttpRequestLog.objects.get().retriable)

    def test_a_post_is_not(self):
        build_session().post(URL, json={})

        self.assertFalse(HttpRequestLog.objects.get().retriable)

    def test_a_single_call_can_say_otherwise(self):
        build_session().post(URL, json={}, retriable=True)

        self.assertTrue(HttpRequestLog.objects.get().retriable)

    def test_a_session_can_say_otherwise(self):
        build_session(retriable=False).get(URL)

        self.assertFalse(HttpRequestLog.objects.get().retriable)


class ContextTests(TestCase):
    def test_the_session_context_and_the_call_context_are_merged(self):
        build_session(context={"integration": "crm"}).get(URL, context={"contact_id": 12})

        self.assertEqual(
            HttpRequestLog.objects.get().context,
            {"integration": "crm", "contact_id": 12},
        )


class BodyStorageTests(TestCase):
    @override_settings(OUTBOUND_LOGGER={"STORE_BODY": False})
    def test_nothing_is_stored_when_the_bodies_are_turned_off(self):
        build_session().post(URL, json={"name": "thing"})

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.request_body, "")
        self.assertEqual(log.response_body, "")
        self.assertEqual(log.request_body_omission, BodyOmission.DISABLED)
        self.assertEqual(log.response_body_omission, BodyOmission.DISABLED)

    @override_settings(OUTBOUND_LOGGER={"MAX_BODY_BYTES": 4})
    def test_a_long_response_is_cut_and_said_to_be_cut(self):
        build_session().get(URL)

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.response_body, '{"ok')
        self.assertTrue(log.response_truncated)

    @override_settings(OUTBOUND_LOGGER={"MAX_BODY_BYTES": 4})
    def test_a_long_request_body_is_dropped_whole(self):
        build_session().post(URL, json={"name": "thing"})

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.request_body, "")
        self.assertEqual(log.request_body_omission, BodyOmission.TOO_LARGE)

    def test_a_binary_response_is_not_stored_as_text(self):
        build_session(StubAdapter(content=b"\xff\xfe\x00")).get(URL)

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.response_body, "")
        self.assertEqual(log.response_body_omission, BodyOmission.BINARY)

    def test_a_streamed_response_is_left_alone(self):
        build_session().get(URL, stream=True)

        log = HttpRequestLog.objects.get()
        self.assertEqual(log.response_body_omission, BodyOmission.STREAMED)
        self.assertEqual(log.status_code, 200)
