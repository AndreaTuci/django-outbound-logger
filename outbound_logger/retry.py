"""What a retry reports, whatever it retried."""

from typing import NamedTuple, Sequence

from django.db.models import Model


class RetryReport(NamedTuple):
    succeeded: Sequence[Model]
    failed: Sequence[Model]
    skipped: Sequence[tuple[Model, str]]
