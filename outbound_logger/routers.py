"""Keep the logs on a database connection of their own."""

from typing import Any

from django.db.models import Model

from .conf import get_setting

APP_LABELS = frozenset({"outbound_mail", "outbound_http"})


class OutboundLoggerRouter:
    """Sends the logs to OUTBOUND_LOGGER["DATABASE"], and keeps everything else out.

    With that alias pointing at a second connection to the same database, a log is
    written outside the transaction the caller may be in: a rollback can no longer
    erase the row saying a message really went out.
    """

    def db_for_read(self, model: type[Model], **hints: Any) -> str | None:
        return self.alias() if model._meta.app_label in APP_LABELS else None

    def db_for_write(self, model: type[Model], **hints: Any) -> str | None:
        return self.alias() if model._meta.app_label in APP_LABELS else None

    def allow_migrate(self, db: str, app_label: str, **hints: Any) -> bool | None:
        alias = self.alias()
        if not alias:
            return None
        if app_label in APP_LABELS:
            return db == alias
        return False if db == alias else None

    def alias(self) -> str | None:
        return get_setting("DATABASE")
