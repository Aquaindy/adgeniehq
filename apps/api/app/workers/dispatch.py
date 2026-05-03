"""Sync/async dispatch helper.

Call sites that want to optionally run on a worker do:

    result = run_or_dispatch(my_task, arg1, arg2)

When `WORKERS_ENABLED=1`, the task is queued and a celery `AsyncResult` is
returned (the caller can await it or fire-and-forget). When workers are off
(default — including in tests), the task body runs inline in the current
request and the result is returned immediately. This lets the same code
path work for both deployment shapes without conditional logic at every
call site."""

from __future__ import annotations

from typing import Any

from celery.app.task import Task

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class SyncDispatchResult:
    """A drop-in shim that mimics the bits of celery's AsyncResult that we
    actually use, so call sites don't have to branch on workers_enabled."""

    def __init__(self, value: Any) -> None:
        self._value = value
        self.id = "sync"
        self.status = "SUCCESS"

    def get(self, timeout: float | None = None) -> Any:  # noqa: ARG002
        return self._value

    @property
    def successful(self) -> bool:
        return True


def run_or_dispatch(task: Task, *args: Any, **kwargs: Any):
    """Queue `task` if workers are enabled, otherwise run it inline.

    Returns either a celery `AsyncResult` or a `SyncDispatchResult`, both of
    which expose `.get()` and `.id`. Pass `_force_sync=True` in kwargs to
    pin to inline execution regardless of the flag (useful in tests)."""

    force_sync = kwargs.pop("_force_sync", False)
    if settings.workers_enabled and not force_sync:
        log.debug("worker.dispatch", task=task.name)
        return task.apply_async(args=args, kwargs=kwargs)
    log.debug("worker.run_inline", task=task.name)
    # `task.run` is the underlying function — bypass celery's apply machinery.
    return SyncDispatchResult(task.run(*args, **kwargs))
