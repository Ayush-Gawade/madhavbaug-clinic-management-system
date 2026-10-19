"""Dispatch auto-reply work off the analysis path.

The analysis worker decides that a message qualifies and enqueues the reply
generation here; a Celery worker performs the model call and the send so a slow
provider can never delay analysis, and so a send failure can never roll back an
observation or an alert that already succeeded.
"""

from __future__ import annotations

import uuid

from app.core.logging import get_logger

logger = get_logger(__name__)


def enqueue_auto_reply(source_message_id: uuid.UUID) -> None:
    """Queue reply generation for a stored inbound message.

    A broker outage must never fail analysis, so enqueue errors are logged and
    swallowed: the observation and the alert are already written and the alert
    alone is enough to page a clinician.
    """
    # Imported lazily so importing this module never pulls Celery into the
    # analysis path, and so tests can import it without a broker.
    from app.workers.tasks import generate_auto_reply

    try:
        generate_auto_reply.delay(str(source_message_id))
    except Exception as exc:  # pragma: no cover - depends on broker availability
        logger.warning(
            "auto_reply_enqueue_failed",
            source_message_id=str(source_message_id),
            error=str(exc),
        )


def enqueue_doctor_notification(auto_reply_id: uuid.UUID) -> None:
    """Queue the urgent-reading notification for an already-recorded reply.

    Kept as its own task so an unreachable doctor number cannot roll back the
    patient-facing reply that was already delivered.
    """
    # Imported lazily so importing this module never pulls Celery into the
    # request path, and so tests can import it without a broker.
    from app.workers.tasks import notify_doctor_of_critical_reading

    try:
        notify_doctor_of_critical_reading.delay(str(auto_reply_id))
    except Exception as exc:  # pragma: no cover - depends on broker availability
        logger.warning(
            "doctor_notification_enqueue_failed",
            auto_reply_id=str(auto_reply_id),
            error=str(exc),
        )
