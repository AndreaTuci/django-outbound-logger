"""The purge of the HTTP logs, for a scheduled task to call."""

from ..purge import purge_logs
from .models import HttpRequestLog


def purge_http_logs(older_than_days: int | None = None) -> int:
    """Delete the HTTP logs older than the window, and return how many went away.

    Without an argument the window is OUTBOUND_LOGGER["RETENTION_DAYS"].
    """
    return purge_logs(HttpRequestLog, older_than_days)
