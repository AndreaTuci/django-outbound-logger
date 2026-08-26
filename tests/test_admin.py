from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from outbound_logger.http.models import HttpRequestLog
from outbound_logger.mail.models import EmailLog

from .base import MailTestCase
from .stubs import StubAdapter

CHANGELIST_URL = reverse("admin:outbound_mail_emaillog_changelist")


class EmailLogAdminTests(MailTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("staff", "staff@example.com", "secret")

    def setUp(self):
        self.client.force_login(self.staff)
        mail.send_mail(
            "Subject", "the body itself", "from@example.com", ["someone@example.com"]
        )
        self.log = EmailLog.objects.get()

    def test_the_changelist_lists_the_log(self):
        response = self.client.get(CHANGELIST_URL)

        self.assertContains(response, "someone@example.com")

    def test_the_search_finds_a_log_by_recipient(self):
        response = self.client.get(CHANGELIST_URL, {"q": "someone@example.com"})

        self.assertContains(response, "Subject")

    def test_the_search_ignores_unrelated_terms(self):
        response = self.client.get(CHANGELIST_URL, {"q": "nobody@example.com"})

        self.assertNotContains(response, "Subject")

    def test_the_detail_page_is_read_only(self):
        url = reverse("admin:outbound_mail_emaillog_change", args=[self.log.pk])

        response = self.client.get(url)

        self.assertContains(response, "the body itself")  # the value, not the label
        self.assertNotContains(response, 'name="subject"')

    def test_the_change_page_refuses_a_post(self):
        url = reverse("admin:outbound_mail_emaillog_change", args=[self.log.pk])

        response = self.client.post(url, {"subject": "rewritten"})

        self.assertEqual(response.status_code, 403)
        self.log.refresh_from_db()
        self.assertEqual(self.log.subject, "Subject")


class HttpRequestLogAdminTests(MailTestCase):
    changelist_url = reverse("admin:outbound_http_httprequestlog_changelist")

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("staff", "staff@example.com", "secret")

    def setUp(self):
        from outbound_logger.http.session import LoggedSession

        self.client.force_login(self.staff)
        session = LoggedSession()
        session.mount("https://", StubAdapter())
        session.get("https://api.example.com/things")
        session.get("https://api.example.com/unrelated")
        self.log = HttpRequestLog.objects.filter(url__endswith="things").get()

    def test_the_changelist_lists_the_call(self):
        response = self.client.get(self.changelist_url)

        self.assertContains(response, "api.example.com/things")

    def test_the_search_finds_a_call_by_url(self):
        response = self.client.get(self.changelist_url, {"q": "unrelated"})

        self.assertContains(response, "api.example.com/unrelated")
        self.assertNotContains(response, "api.example.com/things")

    def test_the_detail_page_is_read_only(self):
        url = reverse("admin:outbound_http_httprequestlog_change", args=[self.log.pk])

        response = self.client.get(url)

        self.assertContains(response, "&quot;ok&quot;: true")  # the response body
        self.assertNotContains(response, 'name="url"')
