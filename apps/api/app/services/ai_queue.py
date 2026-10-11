"""Dispatch inbound AI analysis off the webhook request path.

The webhook handler stores the message and enqueues analysis here; a Celery
worker performs the model call so a slow provider can never delay the webhook
response (PRD FR-018; audit finding: AI awaited inline).
"""

from __future__ import annotations

import uuid


def enqueue_inbound_analysis(message_id: uuid.UUID) -> None:
    """Enqueue deferred analysis for a stored inbound message."""
    # Imported lazily so importing this module never pulls Celery into the
    # request path, and so tests can import it without a broker.
    from app.workers.tasks import analyze_inbound_message

    analyze_inbound_message.delay(str(message_id))
