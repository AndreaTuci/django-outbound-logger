"""Send messages on one connection, recording the outcome of each on its log."""

import traceback

from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

from .models import EmailLog

Pairs = list[tuple[EmailMessage, EmailLog]]

NOTHING_SENT = "The backend accepted the message but reported nothing sent."


def send_and_record(
    delegate: BaseEmailBackend, pairs: Pairs, trigger: str, fail_silently: bool
) -> int:
    """Send every (message, log) pair on a single connection, return how many went out.

    Every outcome lands on its log. With fail_silently off, a failure is re-raised
    once it has been recorded.
    """
    if not pairs:
        return 0

    try:
        new_connection = delegate.open()
    except Exception:
        error = traceback.format_exc()
        for _message, log in pairs:
            log.mark_failed(error, trigger=trigger)
        if not fail_silently:
            raise
        return 0

    try:
        return deliver(delegate, pairs, trigger, fail_silently)
    finally:
        if new_connection:
            delegate.close()


def deliver(
    delegate: BaseEmailBackend, pairs: Pairs, trigger: str, fail_silently: bool
) -> int:
    """One message at a time, so every log gets its own outcome."""
    sent = 0
    for message, log in pairs:
        try:
            delivered = delegate.send_messages([message])
        except Exception:
            log.mark_failed(traceback.format_exc(), trigger=trigger)
            if not fail_silently:
                raise
            continue

        if delivered:
            log.mark_sent(trigger=trigger)
            sent += 1
        else:
            log.mark_failed(NOTHING_SENT, trigger=trigger)
    return sent
