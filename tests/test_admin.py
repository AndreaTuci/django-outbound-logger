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
        mail.send_mail("Subject", "Body", "from@example.com", ["someone@example.com"])
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

        self.assertContains(response, "Body")
        self.assertNotContains(response, 'name="subject"')


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
        self.log = HttpRequestLog.objects.get()

    def test_the_changelist_lists_the_call(self):
        response = self.client.get(self.changelist_url)

        self.assertContains(response, "api.example.com/things")

    def test_the_search_finds_a_call_by_url(self):
        response = self.client.get(self.changelist_url, {"q": "api.example.com"})

        self.assertContains(response, "GET")

    def test_the_detail_page_is_read_only(self):
        url = reverse("admin:outbound_http_httprequestlog_change", args=[self.log.pk])

        response = self.client.get(url)

        self.assertContains(response, "ok")
        self.assertNotContains(response, 'name="url"')
