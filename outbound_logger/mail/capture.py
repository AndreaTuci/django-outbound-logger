"""Turn an outgoing message into its EmailLog row, right before it is sent."""

import json
from typing import Any, Iterable

from django.core.mail import EmailMessage, make_msgid
from django.core.mail.utils import DNS_NAME
from django.utils.encoding import force_str

from ..conf import get_setting
from ..text import clean, fit
from .models import (
    EMAIL_ADDRESS_MAX_LENGTH,
    MESSAGE_ID_MAX_LENGTH,
    SUBJECT_MAX_LENGTH,
    EmailLog,
)

CONTEXT_ATTRIBUTE = "outbound_context"
CONTEXT_HEADER = "X-Outbound-Context"
HTML_MIMETYPE = "text/html"


def create_log(message: EmailMessage) -> EmailLog:
    """Save the log row for `message`. Mutates it: pins the Message-ID, drops our header."""
    message_id = pin_message_id(message)
    context = pop_context(message)
    raw_message, body_omission = capture_raw_message(message)
    stores_body = body_omission != EmailLog.BodyOmission.DISABLED
    body, html_body = split_bodies(message) if stores_body else ("", "")

    return EmailLog.objects.create(
        message_id=fit(message_id, MESSAGE_ID_MAX_LENGTH),
        from_email=fit(force_str(message.from_email), EMAIL_ADDRESS_MAX_LENGTH),
        to=addresses(message.to),
        cc=addresses(message.cc),
        bcc=addresses(message.bcc),
        reply_to=addresses(message.reply_to),
        subject=fit(force_str(message.subject), SUBJECT_MAX_LENGTH),
        body=clean(body),
        html_body=clean(html_body),
        headers={force_str(k): force_str(v) for k, v in message.extra_headers.items()},
        attachments=describe_attachments(message),
        raw_message=raw_message,
        body_omission=body_omission,
        context=context,
    )


def pin_message_id(message: EmailMessage) -> str:
    """Django mints a new Message-ID on every message() call: fix one so the log and
    the delivered mail carry the same identifier."""
    for name, value in message.extra_headers.items():
        if name.lower() == "message-id":
            return force_str(value)

    message_id = make_msgid(domain=DNS_NAME)
    message.extra_headers["Message-ID"] = message_id
    return message_id


def pop_context(message: EmailMessage) -> dict[str, Any]:
    """Read the caller's correlation data, from the attribute and from the header.

    The header is removed here: it is ours, the recipient has no business seeing it.
    """
    context = dict(getattr(message, CONTEXT_ATTRIBUTE, None) or {})
    for name in list(message.extra_headers):
        if name.lower() != CONTEXT_HEADER.lower():
            continue
        raw = message.extra_headers.pop(name)
        try:
            from_header = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"{CONTEXT_HEADER} must hold a JSON object: {error}")
        if not isinstance(from_header, dict):
            raise ValueError(f"{CONTEXT_HEADER} must hold a JSON object, not a list or a scalar.")
        context |= from_header
    return context


def split_bodies(message: EmailMessage) -> tuple[str, str]:
    """Return the text body and the HTML one, wherever the sender put them."""
    body = force_str(message.body or "")
    if getattr(message, "content_subtype", "plain") == "html":
        return "", body

    for alternative in getattr(message, "alternatives", ()):
        content, mimetype = alternative
        if mimetype == HTML_MIMETYPE:
            return body, force_str(content)
    return body, ""


def capture_raw_message(message: EmailMessage) -> tuple[bytes | None, str]:
    """Return the MIME bytes to store, and the reason when we store none."""
    if not get_setting("STORE_BODY"):
        return None, EmailLog.BodyOmission.DISABLED

    raw_message = message.message().as_bytes()
    max_bytes = get_setting("MAX_BODY_BYTES")
    if max_bytes is not None and len(raw_message) > max_bytes:
        return None, EmailLog.BodyOmission.TOO_LARGE
    return raw_message, ""


def describe_attachments(message: EmailMessage) -> list[dict[str, Any]]:
    return [describe_attachment(attachment) for attachment in message.attachments]


def describe_attachment(attachment: Any) -> dict[str, Any]:
    # Django accepts a whole MIME part as an attachment, and not only a MIMEBase:
    # anything that answers like a part is described as one.
    if hasattr(attachment, "get_content_type"):
        content = attachment.as_bytes()
        return {
            "filename": force_str(attachment.get_filename() or ""),
            "content_type": attachment.get_content_type(),
            "size": len(content),
        }

    filename, content, content_type = attachment
    return {
        "filename": force_str(filename or ""),
        "content_type": content_type or "",
        "size": len(content if isinstance(content, bytes) else force_str(content).encode()),
    }


def addresses(values: Iterable[str] | None) -> list[str]:
    return [force_str(value) for value in values or ()]
