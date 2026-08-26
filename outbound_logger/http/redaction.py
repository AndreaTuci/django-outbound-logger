"""Keep credentials out of the log."""

from typing import Any, Mapping

from ..conf import get_setting

REDACTED = "[redacted]"


def redact(headers: Mapping[str, Any] | None) -> dict[str, str]:
    """Return the headers as a plain dict, with the sensitive values replaced."""
    hidden = {name.lower() for name in get_setting("HTTP_REDACT_HEADERS")}
    return {
        name: REDACTED if name.lower() in hidden else str(value)
        for name, value in (headers or {}).items()
    }
