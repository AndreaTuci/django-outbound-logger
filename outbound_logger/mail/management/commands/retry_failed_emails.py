from typing import Any

from django.db.models import QuerySet

from ....commands import RetryLogsCommand
from ...models import EmailLog, EmailSendAttempt
from ...retry import retry_emails


class Command(RetryLogsCommand):
    help = "Send failed messages again."
    model = EmailLog
    trigger = EmailSendAttempt.Trigger.COMMAND
    succeeded_line = "{count} message(s) sent again."

    def candidates(self, **options: Any) -> QuerySet:
        return EmailLog.objects.filter(status=EmailLog.Status.FAILED)

    def retry(self, logs, trigger):
        return retry_emails(logs, trigger=trigger)

    def describe(self, log: EmailLog) -> str:
        return f"{log.pk}\t{log.created_at:%Y-%m-%d %H:%M}\t{log}"
