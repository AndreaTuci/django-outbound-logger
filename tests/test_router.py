from django.core import mail
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings

from outbound_logger.conf import ROUTER, check_settings
from outbound_logger.mail.models import EmailLog
from outbound_logger.http.models import HttpRequestLog
from outbound_logger.routers import APP_LABELS, OutboundLoggerRouter

from .base import LOCMEM, LOGGING_BACKEND

LOG_DATABASE = "logs"
ROUTED = override_settings(
    EMAIL_BACKEND=LOGGING_BACKEND,
    DATABASE_ROUTERS=[ROUTER],
    OUTBOUND_LOGGER={"MAIL_BACKEND": LOCMEM, "DATABASE": LOG_DATABASE},
)


def send_one():
    mail.send_mail("Subject", "Body", "from@example.com", ["to@example.com"])


@ROUTED
class RoutingTests(TestCase):
    databases = {"default", LOG_DATABASE}

    def test_a_log_is_written_to_the_log_database(self):
        send_one()

        self.assertEqual(EmailLog.objects.using(LOG_DATABASE).count(), 1)
        self.assertEqual(EmailLog.objects.using("default").count(), 0)

    def test_the_attempts_follow_their_log(self):
        send_one()

        log = EmailLog.objects.get()
        self.assertEqual(log.attempts.count(), 1)

    def test_the_router_knows_the_app_labels_that_exist(self):
        """A renamed app label would leave the router quietly routing nothing."""
        self.assertEqual(
            APP_LABELS,
            {EmailLog._meta.app_label, HttpRequestLog._meta.app_label},
        )

    def test_only_the_logs_are_migrated_there(self):
        router = OutboundLoggerRouter()

        self.assertIs(router.allow_migrate(LOG_DATABASE, "outbound_mail"), True)
        self.assertIs(router.allow_migrate(LOG_DATABASE, "auth"), False)
        self.assertIs(router.allow_migrate("default", "outbound_mail"), False)
        self.assertIsNone(router.allow_migrate("default", "auth"))


@ROUTED
class RollbackTests(TransactionTestCase):
    databases = {"default", LOG_DATABASE}

    def test_the_log_of_a_sent_message_survives_the_rollback(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            send_one()
            raise RuntimeError("the caller changed its mind")

        self.assertEqual(EmailLog.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)


@override_settings(EMAIL_BACKEND=LOGGING_BACKEND)
class WithoutTheRouterTests(TransactionTestCase):
    """What the router is there to prevent, kept honest by a test."""

    def test_the_log_goes_down_with_the_transaction(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            send_one()
            raise RuntimeError("the caller changed its mind")

        self.assertEqual(EmailLog.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 1)  # the message went out all the same


class DatabaseCheckTests(TestCase):
    @override_settings(OUTBOUND_LOGGER={"DATABASE": "nowhere"})
    def test_an_unknown_alias_is_reported(self):
        self.assertEqual(
            [problem.id for problem in check_settings(app_configs=None)],
            ["outbound_logger.E004"],
        )

    @override_settings(OUTBOUND_LOGGER={"DATABASE": LOG_DATABASE}, DATABASE_ROUTERS=[])
    def test_an_alias_nobody_routes_to_is_reported(self):
        self.assertEqual(
            [problem.id for problem in check_settings(app_configs=None)],
            ["outbound_logger.W002"],
        )

    @ROUTED
    def test_a_routed_alias_is_fine(self):
        self.assertEqual(check_settings(app_configs=None), [])
