from ....commands import PurgeLogsCommand
from ...models import EmailLog


class Command(PurgeLogsCommand):
    help = "Delete the email logs older than the retention window."
    model = EmailLog
