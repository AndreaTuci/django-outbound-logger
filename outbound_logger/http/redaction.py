"""Keep credentials out of the log."""

from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from ..conf import get_setting

REDACTED = "[redacted]"


def redact(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Return the headers as a plain dict, with the sensitive values replaced."""
    hidden = {name.lower() for name in get_setting("HTTP_REDACT_HEADERS")}
    return {
        name: REDACTED if name.lower() in hidden else as_text(value)
        for name, value in (headers or {}).items()
    }


def as_text(value: Any) -> str:
    """requests hands bytes headers through untouched: str() would store their repr."""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)


def redact_url(url: str) -> str:
    """Drop the credentials some clients put in the url itself.

    https://user:secret@host/path is a password in a database column otherwise.
    Secrets passed as query parameters are not touched: their names differ from
    one API to the next, and guessing would hide the wrong things.
    """
    if "@" not in url:
        return url

    parts = urlsplit(url)
    if not parts.username and not parts.password:
        return url

    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit(parts._replace(netloc=f"{REDACTED}@{host}"))
