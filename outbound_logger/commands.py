"""Management command bases shared by the logs."""

from datetime import timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Count, Model, QuerySet
from django.utils import timezone

from .purge import cutoff, expired, purge_logs
from .retry import RetryReport


class PurgeLogsCommand(BaseCommand):
    """Deletes the logs of `model` that are older than the retention window."""

    model: type[Model]

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            metavar="DAYS",
            help="how long a log is kept, overriding OUTBOUND_LOGGER['RETENTION_DAYS']",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="count what would be deleted, delete nothing",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        days = options["days"]
        older_than = f"older than {timezone.localtime(cutoff(days)):%Y-%m-%d %H:%M}"

        if options["dry_run"]:
            count = expired(self.model._default_manager.all(), days).count()
            self.stdout.write(f"{count} log(s) {older_than} would be deleted.")
            return

        deleted = purge_logs(self.model, days)
        self.stdout.write(self.style.SUCCESS(f"{deleted} log(s) {older_than} deleted."))


class RetryLogsCommand(BaseCommand):
    """Sends again what one of the logs recorded.

    A subclass says what it retries: `candidates()` for the rows worth trying,
    `retry()` for how, and `succeeded_line` for what to call them afterwards.
    """

    model: type[Model]
    trigger: str
    succeeded_line = "{count} sent again."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--since",
            type=int,
            metavar="DAYS",
            help="only what was logged in the last DAYS days",
        )
        parser.add_argument(
            "--max-attempts",
            type=int,
            metavar="N",
            help="skip what was already tried N times or more",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="list what would be sent again, send nothing",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        logs = list(
            narrow(
                self.candidates(**options), options["since"], options["max_attempts"]
            )
        )

        if options["dry_run"]:
            for log in logs:
                self.stdout.write(self.describe(log))
            self.stdout.write(f"{len(logs)} would be sent again.")
            return

        self.write_report(self.retry(logs, trigger=self.trigger))

    def candidates(self, **options: Any) -> QuerySet:
        """The rows this command would send again, before the shared narrowing."""
        raise NotImplementedError

    def retry(self, logs: list[Model], trigger: str) -> RetryReport:
        raise NotImplementedError

    def describe(self, log: Model) -> str:
        return f"{log.pk}\t{log}"

    def write_report(self, report: RetryReport) -> None:
        count = len(report.succeeded)
        self.stdout.write(self.style.SUCCESS(self.succeeded_line.format(count=count)))
        if report.failed:
            self.stdout.write(self.style.ERROR(f"{len(report.failed)} failed again."))
        for log, reason in report.skipped:
            self.stdout.write(self.style.WARNING(f"{log.pk} skipped: {reason}"))


def narrow(logs: QuerySet, since_days: int | None, max_attempts: int | None) -> QuerySet:
    """The two limits every retry command offers."""
    if since_days is not None:
        logs = logs.filter(created_at__gte=timezone.now() - timedelta(days=since_days))
    if max_attempts is not None:
        logs = logs.annotate(attempt_count=Count("attempts")).filter(
            attempt_count__lt=max_attempts
        )
    return logs.order_by("created_at")
