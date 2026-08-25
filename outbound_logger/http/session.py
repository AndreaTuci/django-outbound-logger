"""A requests session that writes every call to the database."""

import time
import traceback

import requests

from .capture import record_failure, record_response
from .models import HttpRequestAttempt

# RFC 9110: repeating these has the same effect as making them once.
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS", "TRACE"})


class LoggedSession(requests.Session):
    """Sends like a requests session and leaves a row behind for every call.

    Failures are logged and raised again: what to do with them is the caller's call.
    Both `context` and `retriable` can be set for the whole session here, or for a
    single call as keyword arguments to any of the request methods.
    """

    def __init__(self, *, context=None, retriable=None):
        super().__init__()
        self.context = context or {}
        self.retriable = retriable

    def request(self, method, url, *, context=None, retriable=None, **kwargs):
        options = {
            "retriable": self.resolve_retriable(method, retriable),
            "context": {**self.context, **(context or {})},
            "trigger": HttpRequestAttempt.Trigger.REQUEST,
        }
        started = time.monotonic()

        try:
            response = super().request(method, url, **kwargs)
        except Exception as error:
            record_failure(
                method,
                url,
                getattr(error, "request", None),
                traceback.format_exc(),
                duration_ms=elapsed_ms(started),
                **options,
            )
            raise

        record_response(
            response,
            streamed=bool(kwargs.get("stream")),
            duration_ms=elapsed_ms(started),
            **options,
        )
        return response

    def resolve_retriable(self, method, retriable):
        """The call decides, then the session, then the method itself."""
        if retriable is not None:
            return retriable
        if self.retriable is not None:
            return self.retriable
        return method.upper() in IDEMPOTENT_METHODS


def elapsed_ms(started):
    return round((time.monotonic() - started) * 1000)
