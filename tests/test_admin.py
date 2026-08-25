from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse

from outbound_logger.mail.models import EmailLog

from .base import MailTestCase

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
