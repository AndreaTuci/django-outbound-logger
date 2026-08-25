from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from ...models import HttpRequestAttempt, HttpRequestLog
from ...retry import SERVER_ERROR, retry_requests


class Command(BaseCommand):
    help = "Send failed requests again. Only retriable ones are considered."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            type=int,
            metavar="DAYS",
            help="only requests logged in the last DAYS days",
        )
        parser.add_argument(
            "--max-attempts",
            type=int,
            metavar="N",
            help="skip requests already tried N times or more",
        )
        parser.add_argument(
            "--include-server-errors",
            action="store_true",
            help=f"also retry the ones answered with {SERVER_ERROR} or above",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="list what would be sent again, send nothing",
        )

    def handle(self, *args, **options):
        logs = list(
            select_logs(
                options["since"],
                options["max_attempts"],
                options["include_server_errors"],
            )
        )

        if options["dry_run"]:
            for log in logs:
                self.stdout.write(f"{log.pk}\t{log.status_code or '---'}\t{log}")
            self.stdout.write(f"{len(logs)} request(s) would be sent again.")
            return

        report = retry_requests(logs, trigger=HttpRequestAttempt.Trigger.COMMAND)
        self.stdout.write(
            self.style.SUCCESS(f"{len(report.succeeded)} request(s) answered.")
        )
        if report.failed:
            self.stdout.write(self.style.ERROR(f"{len(report.failed)} failed again."))
        for log, reason in report.skipped:
            self.stdout.write(self.style.WARNING(f"{log.pk} skipped: {reason}"))


def select_logs(since_days, max_attempts, include_server_errors):
    unanswered = Q(status=HttpRequestLog.Status.FAILED)
    if include_server_errors:
        unanswered |= Q(status_code__gte=SERVER_ERROR)

    logs = (
        HttpRequestLog.objects.filter(retriable=True)
        .filter(unanswered)
        .order_by("created_at")
    )
    if since_days:
        logs = logs.filter(created_at__gte=timezone.now() - timedelta(days=since_days))
    if max_attempts:
        logs = logs.annotate(attempt_count=Count("attempts")).filter(
            attempt_count__lt=max_attempts
        )
    return logs
