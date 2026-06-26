"""Founding super-admin bootstrap.

Promotes the users listed in ``INITIAL_SUPERUSER_EMAILS`` to
``is_superuser=True`` on API startup. is_superuser grants /admin access and
bypasses every plan limit (unlimited AI credits, seats, writes), so this is the
"make me Super Admin" switch.

Design:
  * **Idempotent** — a user already a superuser is skipped.
  * **Additive only** — it never demotes. Removing an email from the env does
    NOT revoke access; do that in the DB / a future admin action.
  * **Re-runs every boot** — a freshly restored database re-promotes the
    founding admins without manual SQL.
  * **Case-insensitive** match; the user must already have registered (we only
    promote existing accounts, never create them).
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User

log = get_logger(__name__)


def ensure_initial_superusers(db: Session) -> list[str]:
    """Promote configured emails to superuser. Returns the list of emails that
    were newly promoted this call (empty if none / all already superusers)."""
    emails = [
        e.strip().lower()
        for e in (settings.initial_superuser_emails or [])
        if e and e.strip()
    ]
    if not emails:
        return []

    promoted: list[str] = []
    for email in emails:
        user = db.query(User).filter(func.lower(User.email) == email).first()
        if user is None:
            log.info("superuser.bootstrap.user_not_found", email=email)
            continue
        if not user.is_superuser:
            user.is_superuser = True
            promoted.append(user.email)
            log.info("superuser.bootstrap.promoted", email=user.email)
    if promoted:
        db.commit()
    return promoted


def run_superuser_bootstrap() -> None:
    """Startup entrypoint. Opens its own session and never raises — a DB hiccup
    at boot must not crash the API; the next deploy/restart retries."""
    if not (settings.initial_superuser_emails or []):
        return
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        ensure_initial_superusers(db)
    except Exception as exc:  # noqa: BLE001 — boot must survive a transient DB error
        log.warning("superuser.bootstrap.failed", error=str(exc))
    finally:
        db.close()
