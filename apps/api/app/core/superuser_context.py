"""Per-request 'is this a superuser' flag.

Plan-limit assertions consult this flag to decide whether to enforce caps.
Set by `get_current_user` after loading the User row; resets automatically
at request boundaries (FastAPI runs each request in a fresh asyncio task,
which gets its own copy of the contextvar).

Background tasks (Celery workers, scheduled jobs) do NOT inherit this
flag — they always enforce limits, which is the safe default.
"""

from __future__ import annotations

from contextvars import ContextVar


_superuser_bypass_var: ContextVar[bool] = ContextVar(
    "advanta_superuser_bypass", default=False
)


def is_superuser_request() -> bool:
    """Return True when the current request was made by a superuser.

    Plan-limit helpers short-circuit when this is True so back-office
    staff (Anthropic-style internal admins) can operate without bumping
    into per-tenant caps. The action itself is still audit-logged via
    the normal audit_service path."""
    return _superuser_bypass_var.get()


def set_superuser_request(flag: bool):
    """Set the request-scoped flag. Returns a Token the caller can use
    to reset, though typical FastAPI request lifecycles handle reset
    automatically."""
    return _superuser_bypass_var.set(flag)
