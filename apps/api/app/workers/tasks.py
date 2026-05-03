"""Celery task definitions.

Each task creates its own DB session so it can run on a worker process that
doesn't share state with the request handler. Tasks are kept thin —
business logic lives in the service layer; tasks just orchestrate.

Adding a task:
  1. Define it here with `@celery_app.task(name="…")` and a stable name.
  2. Call it from the request handler with `run_or_dispatch(my_task, …)` so
     it runs inline when `WORKERS_ENABLED=0` and on a worker otherwise.
  3. No need to register elsewhere — `celery_app.include` already covers
     this module.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.core.celery_app import celery_app
from app.core.logging import get_logger

log = get_logger(__name__)


def _session():
    """Lazy SessionLocal lookup so tests can override the binding via
    `app.db.session.SessionLocal` after the worker module loads."""

    from app.db import session as db_session_module

    return db_session_module.SessionLocal()


@celery_app.task(name="advanta.run_agent", bind=True, ignore_result=False)
def run_agent_task(
    self,  # noqa: ARG001 — celery binds task instance as first arg
    *,
    workspace_id: str,
    agent_type: str,
    triggered_by_user_id: str,
    input_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an agent on a worker. Returns a small dict with the run id +
    status; the full record stays in Postgres for the request handler to
    fetch separately.

    UUIDs come over the wire as strings (JSON-safe); we parse them back."""

    from app.agents.runtime import run_agent  # local import — avoid worker
    # imports pulling in the FastAPI app at module load.

    with _session() as db:
        run = run_agent(
            db,
            workspace_id=UUID(workspace_id),
            agent_type=agent_type,
            triggered_by_user_id=UUID(triggered_by_user_id),
            input_payload=input_payload or {},
        )
        return {
            "run_id": str(run.id),
            "status": run.status.value,
            "agent_type": run.agent_type,
            "error_message": run.error_message,
        }


@celery_app.task(name="advanta.send_outreach_email", bind=True, ignore_result=False)
def send_outreach_email_task(
    self,  # noqa: ARG001
    *,
    workspace_id: str,
    email_id: str,
    actor_user_id: str,
    actor_role: str,
) -> dict[str, Any]:
    """Send an approved outreach email from a worker.

    Why: SMTP can hang for 10+ seconds on slow servers, blocking the request
    handler. With workers on, the user gets immediate feedback and the send
    runs in the background; the row's status flips to SENT/FAILED as usual."""

    from app.security.permissions import Role
    from app.services import outreach_service

    with _session() as db:
        email = outreach_service.send_approved_email(
            db,
            workspace_id=UUID(workspace_id),
            email_id=UUID(email_id),
            actor_user_id=UUID(actor_user_id),
            actor_role=Role(actor_role),
            request=None,
        )
        return {
            "email_id": str(email.id),
            "status": email.status.value,
        }


@celery_app.task(name="advanta.launch_ab_test", bind=True, ignore_result=False)
def launch_ab_test_task(
    self,  # noqa: ARG001
    *,
    workspace_id: str,
    test_id: str,
    actor_user_id: str,
    actor_role: str,
) -> dict[str, Any]:
    """Launch an A/B test from a worker.

    Why: ad-target tests POST one campaign per variant to the provider. A
    4-variant test is 4+ HTTP round-trips inside the request handler; that
    pins a FastAPI worker and risks hitting the upstream timeout."""

    from app.security.permissions import Role
    from app.services import ab_test_service

    with _session() as db:
        test = ab_test_service.launch_test(
            db,
            workspace_id=UUID(workspace_id),
            test_id=UUID(test_id),
            actor_user_id=UUID(actor_user_id),
            actor_role=Role(actor_role),
            request=None,
        )
        return {
            "test_id": str(test.id),
            "status": test.status.value,
        }


@celery_app.task(name="advanta.prune_idempotency_keys", bind=True, ignore_result=False)
def prune_idempotency_keys_task(self, *, hours: int = 24) -> dict[str, Any]:  # noqa: ARG001
    """Null out `idempotency_key` on rows older than `hours` so the table
    + index don't grow monotonically. Runs on the daily beat schedule."""

    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    from app.models.recommendation_execution import RecommendationExecution

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    with _session() as db:
        result = db.execute(
            update(RecommendationExecution)
            .where(
                RecommendationExecution.idempotency_key.is_not(None),
                RecommendationExecution.created_at < cutoff,
            )
            .values(idempotency_key=None)
        )
        db.commit()
        return {"pruned": result.rowcount or 0, "older_than_hours": hours}


@celery_app.task(name="advanta.outreach_auto_followups", bind=True, ignore_result=False)
def outreach_auto_followups_task(self) -> dict[str, Any]:  # noqa: ARG001
    """Draft follow-up emails for SENT outreach that's been silent past the
    configured threshold. Drafts only — Admin still approves before send."""

    from app.services import outreach_service

    with _session() as db:
        drafted = outreach_service.auto_draft_pending_followups(db)
        return {"drafted": drafted}


@celery_app.task(name="advanta.autopilot_scan", bind=True, ignore_result=False)
def autopilot_scan_task(self) -> dict[str, Any]:  # noqa: ARG001
    """Iterate every workspace whose AutopilotConfig.mode is AUTOPILOT and
    auto-approve every OPEN recommendation that passes the guardrails. Returns
    a per-workspace summary."""

    from app.models.autopilot_config import AutopilotConfig, AutopilotMode
    from app.models.workspace import Workspace
    from app.models.workspace_member import WorkspaceMember
    from app.security.permissions import Role
    from app.services import autopilot_service

    summaries: list[dict[str, Any]] = []
    with _session() as db:
        active_workspaces = (
            db.query(Workspace)
            .join(AutopilotConfig, AutopilotConfig.workspace_id == Workspace.id)
            .filter(AutopilotConfig.mode == AutopilotMode.AUTOPILOT)
            .all()
        )
        for workspace in active_workspaces:
            owner = (
                db.query(WorkspaceMember)
                .filter(
                    WorkspaceMember.workspace_id == workspace.id,
                    WorkspaceMember.role == Role.OWNER,
                )
                .order_by(WorkspaceMember.created_at.asc())
                .first()
            )
            if owner is None:
                continue  # safety: refuse to act without a real human owner.
            summary = autopilot_service.auto_approve_pending(
                db,
                workspace_id=workspace.id,
                system_actor_id=owner.user_id,
            )
            summaries.append(summary)
    return {"workspaces_scanned": len(summaries), "summaries": summaries}


__all__ = [
    "autopilot_scan_task",
    "launch_ab_test_task",
    "outreach_auto_followups_task",
    "prune_idempotency_keys_task",
    "run_agent_task",
    "send_outreach_email_task",
]
