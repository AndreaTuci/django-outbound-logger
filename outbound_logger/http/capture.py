"""Turn an outgoing request and its outcome into a log row."""

from typing import Any

from requests import PreparedRequest, Response

from ..conf import get_setting
from ..text import clean, fit
from .models import (
    METHOD_MAX_LENGTH,
    REASON_MAX_LENGTH,
    BodyOmission,
    HttpRequestLog,
)
from .redaction import redact, redact_url


def record_response(
    response: Response,
    *,
    streamed: bool,
    duration_ms: int,
    retriable: bool,
    context: dict[str, Any],
    trigger: str,
) -> HttpRequestLog:
    log = HttpRequestLog.objects.create(
        status=HttpRequestLog.Status.COMPLETED,
        duration_ms=duration_ms,
        retriable=retriable,
        context=context,
        **describe_request(response.request),
        **describe_response(response, streamed),
    )
    log.attempts.create(trigger=trigger, status_code=response.status_code)
    return log


def record_failure(
    method: str,
    url: str,
    prepared: PreparedRequest | None,
    error: str,
    *,
    duration_ms: int,
    retriable: bool,
    context: dict[str, Any],
    trigger: str,
) -> HttpRequestLog:
    log = HttpRequestLog.objects.create(
        status=HttpRequestLog.Status.FAILED,
        duration_ms=duration_ms,
        retriable=retriable,
        context=context,
        **describe_request(prepared, method=method, url=url),
    )
    log.attempts.create(trigger=trigger, error=error)
    return log


def describe_request(
    prepared: PreparedRequest | None, method: str = "", url: str = ""
) -> dict[str, Any]:
    """What was really sent, or just method and url when nothing was prepared."""
    if prepared is None:
        # Nothing was prepared, so nothing can be replayed faithfully: say so,
        # or the retry would send the request stripped of its body.
        return {
            "method": fit(method, METHOD_MAX_LENGTH),
            "url": redact_url(url),
            "request_body_omission": BodyOmission.UNPREPARED,
        }

    body, omission = capture_request_body(prepared.body)
    return {
        "method": fit(prepared.method or method, METHOD_MAX_LENGTH),
        "url": redact_url(prepared.url or url),
        "request_headers": redact(prepared.headers),
        "request_body": body,
        "request_body_omission": omission,
    }


def describe_response(response: Response, streamed: bool) -> dict[str, Any]:
    body, omission, truncated = capture_response_body(response, streamed)
    return {
        "status_code": response.status_code,
        "reason": fit(response.reason or "", REASON_MAX_LENGTH),
        "response_headers": redact(response.headers),
        "response_body": body,
        "response_body_omission": omission,
        "response_truncated": truncated,
    }


def capture_request_body(raw: Any) -> tuple[str, str]:
    """Whole or nothing: a body that cannot be replayed exactly is not stored."""
    if not get_setting("STORE_BODY"):
        return "", BodyOmission.DISABLED
    if not raw:
        return "", ""
    if not isinstance(raw, (bytes, str)):
        return "", BodyOmission.STREAMED

    data = raw.encode() if isinstance(raw, str) else raw
    if len(data) > get_setting("MAX_BODY_BYTES"):
        return "", BodyOmission.TOO_LARGE
    try:
        return clean(data.decode("utf-8")), ""
    except UnicodeDecodeError:
        return "", BodyOmission.BINARY


def capture_response_body(response: Response, streamed: bool) -> tuple[str, str, bool]:
    """Read, not replayed: above the limit it is cut and said to be cut."""
    if not get_setting("STORE_BODY"):
        return "", BodyOmission.DISABLED, False
    if streamed:
        # Reading it here would consume the stream the caller asked for.
        return "", BodyOmission.STREAMED, False
    if not response.content:
        return "", "", False

    max_bytes = get_setting("MAX_BODY_BYTES")
    truncated = len(response.content) > max_bytes
    data = response.content[:max_bytes]
    try:
        # The cut can land inside a character: only then are stray bytes dropped.
        text = data.decode("utf-8", "ignore" if truncated else "strict")
        return clean(text), "", truncated
    except UnicodeDecodeError:
        return "", BodyOmission.BINARY, False
