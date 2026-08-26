"""Build the message to send again out of what was logged."""

from email import message_from_bytes, policy
from typing import Any

from django.core.mail import EmailMultiAlternatives

from .models import EmailLog

HTML_MIMETYPE = "text/html"


def rebuild_message(log: EmailLog) -> EmailMultiAlternatives:
    """Rebuild a Django message from the log.

    The fields carry the envelope and the bodies; the attachments are lifted back
    out of the stored MIME. A Django message rather than the raw MIME bytes,
    because backends that talk to an API instead of an SMTP server read the
    fields, not the MIME.
    """
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
    elif log.html_body:
        message.attach_alternative(log.html_body, HTML_MIMETYPE)

    for filename, content, content_type in extract_attachments(log.raw_message):
        message.attach(filename, content, content_type)
    return message


def extract_attachments(raw_message: bytes | None) -> list[tuple[str, Any, str]]:
    if raw_message is None:
        return []

    parsed = message_from_bytes(bytes(raw_message), policy=policy.default)
    return [
        (part.get_filename() or "", part.get_content(), part.get_content_type())
        for part in parsed.iter_attachments()
    ]
