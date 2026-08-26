from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from outbound_logger.http.models import HttpRequestLog
from outbound_logger.mail.models import EmailLog

from .base import MailTestCase, build_message
from .stubs import build_session

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
        self.client.force_login(self.staff)
        session = build_session()
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


class HtmlPreviewTests(MailTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("look", "look@example.com", "secret")

    def setUp(self):
        self.client.force_login(self.staff)

    def detail_of(self, message):
        message.send()
        log = EmailLog.objects.latest("pk")
        url = reverse("admin:outbound_mail_emaillog_change", args=[log.pk])
        return self.client.get(url)

    def test_an_html_body_is_shown_in_a_sandboxed_frame(self):
        message = build_message()
        message.attach_alternative("<p>Ciao</p>", "text/html")

        response = self.detail_of(message)

        self.assertContains(response, "<iframe sandbox")
        self.assertContains(response, "&lt;p&gt;Ciao&lt;/p&gt;")  # inside srcdoc

    def test_the_preview_cannot_smuggle_markup_into_the_admin(self):
        message = build_message()
        message.attach_alternative("<script>alert(1)</script>", "text/html")

        response = self.detail_of(message)

        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_a_message_without_html_says_so(self):
        response = self.detail_of(build_message())

        self.assertContains(response, "no HTML body")


class CustomisedAdminTests(MailTestCase):
    """Projects on django-unfold and friends re-register with their own base."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser("boss2", "boss2@example.com", "secret")

    def test_the_admin_classes_work_as_mixins(self):
        from django.contrib import admin

        from outbound_logger.mail.admin import EmailLogAdmin

        class TheirModelAdmin(admin.ModelAdmin):
            """Stands in for the ModelAdmin a theme ships."""

        class TheirEmailLogAdmin(EmailLogAdmin, TheirModelAdmin):
            pass

        admin.site.unregister(EmailLog)
        admin.site.register(EmailLog, TheirEmailLogAdmin)
        self.addCleanup(admin.site.register, EmailLog, EmailLogAdmin)
        self.addCleanup(admin.site.unregister, EmailLog)

        build_message().send()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:outbound_mail_emaillog_changelist"))

        self.assertContains(response, "to@example.com")
