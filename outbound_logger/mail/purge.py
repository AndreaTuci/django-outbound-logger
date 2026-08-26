"""The purge of the email logs, for a scheduled task to call."""

from ..purge import purge_logs
from .models import EmailLog


def purge_email_logs(older_than_days: int | None = None) -> int:
    """Delete the email logs older than the window, and return how many went away.

    Without an argument the window is OUTBOUND_LOGGER["RETENTION_DAYS"].
    """
    return purge_logs(EmailLog, older_than_days)
