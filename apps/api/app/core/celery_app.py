"""Celery application factory.

The factory exists even when `WORKERS_ENABLED` is off — code that wants to
dispatch a task imports `celery_app` and uses `task.delay(...)` or
`task.apply_async(...)`. With workers disabled, callers should use
`run_or_dispatch` from `app.workers.dispatch` to fall back to sync execution
in the request handler.

The broker + result backend default to the configured `redis_url` so a
single Redis instance covers caching, rate limiting, and queues. Set
`CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` explicitly when those need to
diverge (e.g., RQ-style separation, or a managed broker)."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


def _broker_url() -> str:
    return settings.celery_broker_url or settings.redis_url


def _backend_url() -> str:
    return settings.celery_result_backend or settings.redis_url


celery_app = Celery(
    "advanta",
    broker=_broker_url(),
    backend=_backend_url(),
    include=[
        # Each worker module registers its tasks via `@celery_app.task`.
        "app.workers.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=4,
    # Keep results around briefly so the API can poll for completion if it
    # ever needs to block on a worker result. 1 hour is plenty.
    result_expires=3600,
    task_default_queue="default",
    # Per-task time limit so a runaway provider call doesn't pin a worker.
    task_time_limit=300,        # hard kill at 5 minutes
    task_soft_time_limit=240,   # SoftTimeLimitExceeded at 4 minutes
)


# Beat schedule. Pick up these jobs by running:
#   celery -A app.core.celery_app.celery_app beat
# alongside (or in the same process as) the worker.
celery_app.conf.beat_schedule = {
    "prune-idempotency-keys-daily": {
        "task": "advanta.prune_idempotency_keys",
        "schedule": 24 * 60 * 60.0,  # every 24h
        # 90-day retention: idempotency keys guard money-moving execution
        # replays, so the window must comfortably outlast any provider retry /
        # delayed redelivery. 24h was too short for that guarantee.
        "kwargs": {"hours": 24 * 90},
    },
    "outreach-auto-followups-hourly": {
        "task": "advanta.outreach_auto_followups",
        "schedule": 60 * 60.0,  # every hour
    },
    "autopilot-scan-every-15min": {
        "task": "advanta.autopilot_scan",
        "schedule": 15 * 60.0,
    },
    # Run fees roll up monthly: 02:00 UTC on the 1st, billing the month that
    # just closed (so real synced spend is in).
    "monthly-run-fee-accrual": {
        "task": "advanta.monthly_run_fee_accrual",
        "schedule": crontab(hour=2, minute=0, day_of_month=1),
    },
}
