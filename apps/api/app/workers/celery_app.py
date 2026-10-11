"""Celery application and periodic schedule.

The scheduler (Celery Beat) and workers host all durable, retryable work:
follow-up dispatch, inbound-message processing, AI jobs, deadline monitoring
and escalation. None of this should block an HTTP webhook response.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "madhavbaug",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.app_timezone,
    enable_utc=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    # Reliability: acknowledge only after the task finishes, requeue if the
    # worker dies mid-task, and persist every task's outcome for a day.
    task_acks_late=True,
    task_acks_on_failure_or_timeout=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
    # Bound runaway work and hide tasks only for longer than any legitimate run
    # so a lost worker cannot cause duplicate delivery within the visibility
    # window.
    task_time_limit=60 * 15,
    task_soft_time_limit=60 * 13,
    task_default_retry_delay=30,
    broker_transport_options={"visibility_timeout": 60 * 60},
    task_annotations={"app.workers.tasks.*": {"max_retries": 5}},
    beat_schedule={
        "materialize-follow-ups": {
            "task": "app.workers.tasks.materialize_follow_ups",
            "schedule": crontab(minute="*/10"),
        },
        "process-due-follow-ups": {
            "task": "app.workers.tasks.process_due_follow_ups",
            "schedule": crontab(minute="*/2"),
        },
        "process-non-response": {
            "task": "app.workers.tasks.process_non_response",
            "schedule": crontab(minute="*/5"),
        },
        "dispatch-outbound-messages": {
            "task": "app.workers.tasks.dispatch_outbound_messages",
            "schedule": crontab(minute="*"),
        },
    },
)
