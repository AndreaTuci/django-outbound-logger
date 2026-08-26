"""The OUTBOUND_LOGGER setting: defaults, access and validation."""

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error
from django.core.checks import Warning as CheckWarning
from django.core.exceptions import ImproperlyConfigured

SETTING_NAME = "OUTBOUND_LOGGER"
ROUTER = "outbound_logger.routers.OutboundLoggerRouter"
LOGGING_MAIL_BACKEND = "outbound_logger.mail.backends.LoggingEmailBackend"
DEFAULT_MAX_BODY_BYTES = 5 * 1024 * 1024
DEFAULT_RETENTION_DAYS = 90
DEFAULT_RETRY_TIMEOUT = 30
DEFAULT_REDACT_HEADERS = (
    "Authorization",
    "Proxy-Authorization",
    "Cookie",
    "Set-Cookie",
    "X-Api-Key",
    "X-Auth-Token",
)

DEFAULTS: dict[str, Any] = {
    # The real backend messages are delegated to, as a dotted path.
    "MAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    # Keyword arguments for it, when it cannot read its own settings.
    "MAIL_BACKEND_OPTIONS": {},
    # A MAILERS alias to delegate to instead (Django 6.1+). Excludes MAIL_BACKEND.
    "MAIL_MAILER": None,
    # Store the message body and its MIME bytes, or only the metadata.
    "STORE_BODY": True,
    # Above this size the MIME bytes are dropped: no retry for that message.
    "MAX_BODY_BYTES": DEFAULT_MAX_BODY_BYTES,
    # How long a log is kept, for the purge to act on. Nothing is deleted until
    # the purge is called: from the admin, from the command or from a task.
    "RETENTION_DAYS": DEFAULT_RETENTION_DAYS,
    # Request and response headers whose value is replaced before it is stored.
    "HTTP_REDACT_HEADERS": DEFAULT_REDACT_HEADERS,
    # Dotted path to a callable returning a configured requests.Session. The retry
    # prepares on top of it, so the credentials the log does not hold come back.
    "HTTP_SESSION_FACTORY": None,
    # Seconds a retried request waits before giving up.
    "HTTP_RETRY_TIMEOUT": DEFAULT_RETRY_TIMEOUT,
    # Database alias the logs live on, through the router. A second connection to
    # the same database is enough, and keeps the logs out of the caller's
    # transaction.
    "DATABASE": None,
}


def get_setting(name: str) -> Any:
    """Return one OUTBOUND_LOGGER value, falling back to the packaged default."""
    if name not in DEFAULTS:
        raise ImproperlyConfigured(f"{SETTING_NAME} has no setting named {name!r}.")
    return getattr(settings, SETTING_NAME, {}).get(name, DEFAULTS[name])


def is_set(name: str) -> bool:
    """True when the project spells the setting out, whatever its value."""
    return name in getattr(settings, SETTING_NAME, {})


def check_settings(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """A misspelled setting is silently ignored otherwise, which is worse than loud."""
    unknown = sorted(set(getattr(settings, SETTING_NAME, {})) - set(DEFAULTS))
    problems: list[CheckMessage] = [
        Error(
            f"Unknown {SETTING_NAME} setting {name!r}.",
            hint=f"Known settings: {', '.join(sorted(DEFAULTS))}.",
            id="outbound_logger.E001",
        )
        for name in unknown
    ]

    if get_setting("MAIL_MAILER") and is_set("MAIL_BACKEND"):
        problems.append(
            Error(
                "MAIL_MAILER and MAIL_BACKEND both name the backend to delegate to.",
                hint="Keep MAIL_MAILER on projects using MAILERS, MAIL_BACKEND elsewhere.",
                id="outbound_logger.E002",
            )
        )

    if get_setting("MAIL_BACKEND") == LOGGING_MAIL_BACKEND:
        problems.append(
            Error(
                "MAIL_BACKEND delegates to the logging backend itself.",
                hint="Point it at the backend that really sends, e.g. the SMTP one.",
                id="outbound_logger.E003",
            )
        )

    problems += check_database(get_setting("DATABASE"))

    if hasattr(settings, "MAILERS") and not get_setting("MAIL_MAILER"):
        problems.append(
            CheckWarning(
                "This project uses MAILERS but MAIL_MAILER is not set.",
                hint=(
                    "Add the mailer alias that really sends to MAIL_MAILER, otherwise "
                    "the delegate is built from the deprecated EMAIL_* settings."
                ),
                id="outbound_logger.W001",
            )
        )

    return problems


def check_database(alias: str | None) -> list[CheckMessage]:
    """A log database nobody routes to is a setting that quietly does nothing."""
    if not alias:
        return []

    if alias not in settings.DATABASES:
        return [
            Error(
                f"DATABASE names {alias!r}, which is not one of the DATABASES.",
                hint="Add the alias to DATABASES, pointing at the same database.",
                id="outbound_logger.E004",
            )
        ]

    if ROUTER not in getattr(settings, "DATABASE_ROUTERS", []):
        return [
            CheckWarning(
                f"DATABASE names {alias!r} but nothing routes the logs to it.",
                hint=(
                    f"Add {ROUTER!r} to DATABASE_ROUTERS. If you subclassed the "
                    "router, silence this check instead."
                ),
                id="outbound_logger.W002",
            )
        ]

    return []
