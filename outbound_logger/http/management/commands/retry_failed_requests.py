from typing import Any

from django.core.management.base import CommandParser
from django.db.models import Q, QuerySet

from ....commands import RetryLogsCommand
from ...models import HttpRequestAttempt, HttpRequestLog
from ...retry import SERVER_ERROR, retry_requests


class Command(RetryLogsCommand):
    help = "Send failed requests again. Only retriable ones are considered."
    model = HttpRequestLog
    trigger = HttpRequestAttempt.Trigger.COMMAND
    succeeded_line = "{count} request(s) answered."

    def add_arguments(self, parser: CommandParser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--include-server-errors",
            action="store_true",
            help=f"also retry the ones answered with {SERVER_ERROR} or above",
        )

    def candidates(self, **options: Any) -> QuerySet:
        unanswered = Q(status=HttpRequestLog.Status.FAILED)
        if options["include_server_errors"]:
            unanswered |= Q(status_code__gte=SERVER_ERROR)
        return HttpRequestLog.objects.filter(retriable=True).filter(unanswered)

    def retry(self, logs, trigger):
        return retry_requests(logs, trigger=trigger)

    def describe(self, log: HttpRequestLog) -> str:
        return f"{log.pk}\t{log.status_code or '---'}\t{log}"
