from django.core.management.base import BaseCommand

from ....purge import cutoff, expired
from ...models import EmailLog
from ...purge import purge_email_logs


class Command(BaseCommand):
    help = "Delete the email logs older than the retention window."

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        days = options["days"]
        older_than = f"older than {cutoff(days):%Y-%m-%d %H:%M}"

        if options["dry_run"]:
            count = expired(EmailLog.objects.all(), days).count()
            self.stdout.write(f"{count} log(s) {older_than} would be deleted.")
            return

        deleted = purge_email_logs(days)
        self.stdout.write(self.style.SUCCESS(f"{deleted} log(s) {older_than} deleted."))
