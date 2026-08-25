from ....commands import PurgeLogsCommand
from ...models import HttpRequestLog


class Command(PurgeLogsCommand):
    help = "Delete the HTTP request logs older than the retention window."
    model = HttpRequestLog
