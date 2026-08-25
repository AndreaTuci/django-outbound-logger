"""What a retry reports, whatever it retried."""

from typing import NamedTuple


class RetryReport(NamedTuple):
    succeeded: list
    failed: list
    skipped: list  # (log, reason) pairs
