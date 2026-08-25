"""Send logged requests again."""

import time
import traceback

import requests
from django.utils.module_loading import import_string

from ..conf import get_setting
from ..retry import RetryReport
from .capture import describe_response
from .models import HttpRequestAttempt
from .redaction import REDACTED
from .session import elapsed_ms

SERVER_ERROR = 500
# requests works these out from the url and from the body it is handed.
RECOMPUTED_HEADERS = frozenset({"content-length", "host"})


def build_session():
    """The session a replay is prepared on: the project's own, when it names one."""
    factory = get_setting("HTTP_SESSION_FACTORY")
    return import_string(factory)() if factory else requests.Session()


def retry_requests(logs, trigger=HttpRequestAttempt.Trigger.CODE, session=None):
    """Send every retriable request again, and say how it went.

    Nothing is raised: what cannot be replayed lands in `skipped` with its reason,
    what came back with an answer in `succeeded`, the rest in `failed`.
    """
    session = session or build_session()
    succeeded, failed, skipped = [], [], []

    for log in logs:
        reason = log.why_not_retriable()
        if reason:
            skipped.append((log, reason))
        elif replay(log, session, trigger):
            succeeded.append(log)
        else:
            failed.append(log)

    return RetryReport(succeeded, failed, skipped)


def replay(log, session, trigger):
    """Send the logged request again. True when the endpoint gave a real answer:
    no response and a server error are both the failure we were retrying."""
    started = time.monotonic()
    timeout = get_setting("HTTP_RETRY_TIMEOUT")

    try:
        response = session.send(prepare(log, session), timeout=timeout)
    except Exception:
        log.mark_failed(traceback.format_exc(), elapsed_ms(started), trigger)
        return False

    log.mark_completed(
        describe_response(response, streamed=False), elapsed_ms(started), trigger
    )
    return response.status_code < SERVER_ERROR


def prepare(log, session):
    request = requests.Request(
        method=log.method,
        url=log.url,
        headers=replayable_headers(log.request_headers),
        data=log.request_body.encode() or None,
    )
    return session.prepare_request(request)


def replayable_headers(headers):
    """Redacted values are dropped: the session puts its own credentials back."""
    return {
        name: value
        for name, value in headers.items()
        if value != REDACTED and name.lower() not in RECOMPUTED_HEADERS
    }
