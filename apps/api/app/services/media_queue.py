"""Dispatch inbound media downloads off the webhook request path.

The webhook stores the message and enqueues the download here; a Celery worker
fetches the bytes so a slow or large media transfer can never delay the webhook
response.
"""

from __future__ import annotations

import uuid

from app.core.logging import get_logger

logger = get_logger(__name__)


def enqueue_inbound_media(message_id: uuid.UUID) -> None:
    """Enqueue a best-effort media download for a stored inbound message.

    A broker outage must never fail a webhook, so enqueue errors are logged and
    swallowed; the message itself is already stored.
    """
    # Imported lazily so importing this module never pulls Celery into the
    # request path, and so tests can import it without a broker.
    from app.workers.tasks import store_inbound_message_media

    try:
        store_inbound_message_media.delay(str(message_id))
    except Exception as exc:  # pragma: no cover - depends on broker availability
        logger.warning("media_enqueue_failed", message_id=str(message_id), error=str(exc))
