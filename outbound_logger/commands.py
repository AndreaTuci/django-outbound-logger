"""Management command bases shared by the logs."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Model

from .purge import cutoff, expired, purge_logs


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
        older_than = f"older than {cutoff(days):%Y-%m-%d %H:%M}"

        if options["dry_run"]:
            count = expired(self.model._default_manager.all(), days).count()
            self.stdout.write(f"{count} log(s) {older_than} would be deleted.")
            return

        deleted = purge_logs(self.model, days)
        self.stdout.write(self.style.SUCCESS(f"{deleted} log(s) {older_than} deleted."))
