from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from ...models import EmailLog, EmailSendAttempt
from ...retry import retry_emails


class Command(BaseCommand):
    help = "Send failed messages again."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            type=int,
            metavar="DAYS",
            help="only messages logged in the last DAYS days",
        )
        parser.add_argument(
            "--max-attempts",
            type=int,
            metavar="N",
            help="skip messages already tried N times or more",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="list what would be sent again, send nothing",
        )

    def handle(self, *args, **options):
        logs = list(select_logs(options["since"], options["max_attempts"]))

        if options["dry_run"]:
            for log in logs:
                self.stdout.write(f"{log.pk}\t{log.created_at:%Y-%m-%d %H:%M}\t{log}")
            self.stdout.write(f"{len(logs)} message(s) would be sent again.")
            return

        report = retry_emails(logs, trigger=EmailSendAttempt.Trigger.COMMAND)
        self.stdout.write(self.style.SUCCESS(f"{len(report.succeeded)} message(s) sent again."))
        if report.failed:
            self.stdout.write(self.style.ERROR(f"{len(report.failed)} failed again."))
        for log, reason in report.skipped:
            self.stdout.write(self.style.WARNING(f"{log.pk} skipped: {reason}"))


def select_logs(since_days, max_attempts):
    logs = EmailLog.objects.filter(status=EmailLog.Status.FAILED).order_by("created_at")
    if since_days:
        logs = logs.filter(created_at__gte=timezone.now() - timedelta(days=since_days))
    if max_attempts:
        logs = logs.annotate(attempt_count=Count("attempts")).filter(
            attempt_count__lt=max_attempts
        )
    return logs
