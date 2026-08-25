"""Send logged messages again."""

from ..retry import RetryReport
from .backends import build_delegate
from .delivery import send_and_record
from .models import EmailLog, EmailSendAttempt
from .rebuild import rebuild_message


def retry_emails(logs, trigger=EmailSendAttempt.Trigger.CODE):
    """Send every retriable log again on one connection, and say how it went.

    Nothing is raised: a log that cannot be rebuilt lands in `skipped` with its
    reason, one that goes out again in `succeeded`, one that fails again in
    `failed` with the error recorded as a new attempt.
    """
    pairs = []
    skipped = []
    for log in logs:
        reason = log.why_not_retriable()
        if reason:
            skipped.append((log, reason))
        else:
            pairs.append((rebuild_message(log), log))

    if pairs:
        send_and_record(build_delegate(), pairs, trigger=trigger, fail_silently=True)

    return RetryReport(
        succeeded=[log for _message, log in pairs if log.status == EmailLog.Status.SENT],
        failed=[log for _message, log in pairs if log.status != EmailLog.Status.SENT],
        skipped=skipped,
    )
