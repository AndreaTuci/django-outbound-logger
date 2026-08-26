"""Delete the logs that are older than the retention window."""

from datetime import datetime, timedelta

from django.db.models import Model, QuerySet
from django.utils import timezone

from .conf import get_setting


def cutoff(older_than_days: int | None = None) -> datetime:
    """The instant before which logs are old enough to be deleted."""
    days = get_setting("RETENTION_DAYS") if older_than_days is None else older_than_days
    return timezone.now() - timedelta(days=days)


def expired(queryset: QuerySet, older_than_days: int | None = None) -> QuerySet:
    return queryset.filter(created_at__lt=cutoff(older_than_days))


def purge_logs(model: type[Model], older_than_days: int | None = None) -> int:
    """Delete the expired logs and return how many of them went away.

    Only the logs are counted: what cascades with them is not.
    """
    _total, by_model = expired(model._default_manager.all(), older_than_days).delete()
    return by_model.get(model._meta.label, 0)
