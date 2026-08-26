"""Send messages on one connection, recording the outcome of each on its log."""

import logging
import traceback
from typing import Sequence

from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

from .models import EmailLog

# A pair carries no log when the message could not be recorded: it is sent anyway.
Pairs = Sequence[tuple[EmailMessage, EmailLog | None]]

logger = logging.getLogger(__name__)

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
            if log is not None:
                log.mark_failed(error, trigger=trigger)
        if not fail_silently:
            raise
        return 0

    try:
        return deliver(delegate, pairs, trigger, fail_silently)
    finally:
        if new_connection:
            close(delegate)


def close(delegate: BaseEmailBackend) -> None:
    """Closing is cleanup: its failure is worth a log, never worth losing a send."""
    try:
        delegate.close()
    except Exception:
        logger.exception("could not close the connection to the mail server")


def deliver(
    delegate: BaseEmailBackend, pairs: Pairs, trigger: str, fail_silently: bool
) -> int:
    """One message at a time, so every log gets its own outcome."""
    sent = 0
    for message, log in pairs:
        try:
            delivered = delegate.send_messages([message])
        except Exception:
            if log is not None:
                log.mark_failed(traceback.format_exc(), trigger=trigger)
            if not fail_silently:
                raise
            continue

        if delivered:
            sent += 1
        if log is None:
            continue
        if delivered:
            log.mark_sent(trigger=trigger)
        else:
            log.mark_failed(NOTHING_SENT, trigger=trigger)
    return sent
