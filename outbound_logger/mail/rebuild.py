"""Build the message to send again out of what was logged."""

from email import message_from_bytes, policy
from typing import Any

from django.core.mail import EmailMultiAlternatives

from .capture import HTML_MIMETYPE
from .models import EmailLog


def rebuild_message(log: EmailLog) -> EmailMultiAlternatives:
    """Rebuild a Django message from the log.

    The fields carry the envelope and the bodies; the attachments are lifted back
    out of the stored MIME. A Django message rather than the raw MIME bytes,
    because backends that talk to an API instead of an SMTP server read the
    fields, not the MIME.
    """
    parsed = parse(log.raw_message)
    message = EmailMultiAlternatives(
        subject=log.subject,
        body=log.body or log.html_body,
        from_email=log.from_email,
        to=log.to,
        cc=log.cc,
        bcc=log.bcc,
        reply_to=log.reply_to,
        headers=dict(log.headers),
    )

    if log.html_body and not log.body:
        message.content_subtype = "html"

    if log.html_body and log.body:
        message.attach_alternative(log.html_body, HTML_MIMETYPE)

    # The fields hold the HTML one exactly; anything else - a calendar invitation,
    # say - only exists in the stored MIME.
    for content, mimetype in extract_alternatives(parsed):
        if mimetype != HTML_MIMETYPE:
            message.attach_alternative(content, mimetype)

    for filename, content, content_type in extract_attachments(parsed):
        message.attach(filename, content, content_type)
    return message


def parse(raw_message: bytes | None) -> Any:
    """The stored MIME, read once for whoever needs a part of it."""
    if raw_message is None:
        return None
    return message_from_bytes(bytes(raw_message), policy=policy.default)


def extract_alternatives(parsed: Any) -> list[tuple[Any, str]]:
    """Every alternative of the stored MIME but the plain body."""
    if parsed is None:
        return []

    plain = parsed.get_body(preferencelist=("plain",))
    return [
        (part.get_content(), part.get_content_type())
        for part in alternative_parts(parsed)
        if part is not plain
    ]


def alternative_parts(parsed: Any) -> list[Any]:
    for part in parsed.walk():
        if part.get_content_type() == "multipart/alternative":
            return list(part.iter_parts())
    return []


def extract_attachments(parsed: Any) -> list[tuple[str, Any, str]]:
    if parsed is None:
        return []

    return [
        (part.get_filename() or "", part.get_content(), part.get_content_type())
        for part in parsed.iter_attachments()
    ]
