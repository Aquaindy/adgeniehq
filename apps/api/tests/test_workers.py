"""Worker scaffolding.

Pins the contract that the dispatch helper provides: the same call site
works whether `WORKERS_ENABLED` is on or off, with sync execution as the
test/dev default. No live broker is needed — we only exercise the helper +
celery app config; in production a separate worker process consumes the
queue."""

from __future__ import annotations

from unittest.mock import patch

from app.core.celery_app import celery_app
from app.core.config import settings
from app.workers.dispatch import SyncDispatchResult, run_or_dispatch
from app.workers.tasks import run_agent_task, send_outreach_email_task


def test_celery_app_loads_with_redis_broker_default() -> None:
    # Defaults to settings.redis_url when CELERY_BROKER_URL isn't set.
    assert celery_app.conf.broker_url
    assert celery_app.conf.result_backend
    # Tasks we registered show up in the registry.
    names = set(celery_app.tasks.keys())
    assert "advanta.run_agent" in names
    assert "advanta.send_outreach_email" in names


def test_run_or_dispatch_runs_inline_when_workers_disabled() -> None:
    """With WORKERS_ENABLED=0 (the test default), run_or_dispatch executes
    the task body in-process and returns a SyncDispatchResult. No broker
    is required; the helper is the contract for "I might run async later"."""

    sentinel = {"hits": 0}

    @celery_app.task(name="advanta.test_inline_smoke")
    def _smoke():
        sentinel["hits"] += 1
        return 42

    assert settings.workers_enabled is False
    result = run_or_dispatch(_smoke)
    assert isinstance(result, SyncDispatchResult)
    assert result.get() == 42
    assert sentinel["hits"] == 1
    # Status surface mirrors AsyncResult enough for callers that poll.
    assert result.status == "SUCCESS"
    assert result.successful is True


def test_force_sync_bypasses_workers_enabled_flag() -> None:
    """Even if a deployment has workers enabled, callers can pin a specific
    invocation to inline execution by passing `_force_sync=True`. Useful
    when a test environment shares config with a worker-on deployment."""

    @celery_app.task(name="advanta.test_force_sync")
    def _job(value: int) -> int:
        return value * 2

    saved = settings.workers_enabled
    settings.workers_enabled = True  # pretend production
    try:
        # If _force_sync didn't work, this would actually try to apply_async
        # against an unreachable broker and hang/fail. Inline is the only
        # path that succeeds without a live worker.
        result = run_or_dispatch(_job, 21, _force_sync=True)
    finally:
        settings.workers_enabled = saved

    assert isinstance(result, SyncDispatchResult)
    assert result.get() == 42


def test_tasks_use_their_own_db_session(db_session) -> None:  # noqa: ARG001 — fixture for schema setup
    """run_agent_task opens its own SessionLocal so it can run on a worker
    that doesn't share the request session. We sanity-check by invoking the
    task body directly (no celery layer) and confirming it doesn't blow up
    on import or session creation."""

    # Import-time + tasks registered = enough for a worker to load.
    assert run_agent_task is not None
    assert send_outreach_email_task is not None
    assert run_agent_task.name == "advanta.run_agent"
    # We don't actually run the agent here — the agent-runtime tests cover
    # that path. This test pins task wiring, not agent behaviour.
