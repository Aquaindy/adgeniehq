"""Outbound write executor for approved recommendations.

A recommendation describes the change in plain language; its `metadata_json`
carries the structured action the orchestrator wants applied:

    {
      "provider": "google_ads",
      "external_id": "1234567890",
      "external_account_id": "987",
      "action": "campaign.update_budget",
      "payload": {"daily_budget_cents": 5000}
    }

This service resolves the connected account, decrypts the token, dispatches to
the right provider write method, persists the result + prior_state, and emits
audit log entries. Reverts read prior_state and apply the inverse change."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.integrations.base import (
    BaseProvider,
    ProviderError,
    ProviderNotConfiguredError,
)
from app.integrations.registry import get_provider
from app.models.approval import Approval, ApprovalStatus
from app.models.audit_log import AuditActorType
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.recommendation_execution import (
    ExecutionStatus,
    RecommendationExecution,
)
from app.models.usage_event import UsageEventType
from app.services import audit_service, billing_service, integration_service

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExecutionError(AdVantaError):
    status_code = 502
    code = "execution_failed"


class InvalidActionError(AdVantaError):
    status_code = 400
    code = "invalid_action"


class AccountNotReadyError(AdVantaError):
    status_code = 409
    code = "account_not_ready"


class DuplicateExecutionError(AdVantaError):
    """Raised when an execute would clobber an in-flight or already-applied
    execution. The existing execution id is exposed so the caller can show
    the user the prior result instead of dispatching a duplicate write."""

    status_code = 409
    code = "duplicate_execution"

    def __init__(self, message: str, *, existing_execution_id: UUID) -> None:
        super().__init__(message)
        self.existing_execution_id = existing_execution_id


# Action types we know how to dispatch.
SUPPORTED_ACTIONS = {
    "campaign.pause",
    "campaign.resume",
    "campaign.update_budget",
    "campaign.update_audience",
    "campaign.create",
}

# Reverse map for revert-by-action — used when status flips, the inverse is
# obvious. For mutating ops (budget/audience) we replay the prior_state.
INVERSE_STATUS_ACTION = {
    "campaign.pause": "campaign.resume",
    "campaign.resume": "campaign.pause",
}


# ---------------------------------------------------------------------------
# Action plan extraction
# ---------------------------------------------------------------------------


def _extract_action_plan(rec: Recommendation) -> dict:
    meta = rec.metadata_json or {}
    provider = meta.get("provider") or rec.platform
    action = meta.get("action")
    if not provider:
        raise InvalidActionError(
            "Recommendation has no provider in metadata or platform — cannot execute."
        )
    if not action:
        raise InvalidActionError(
            "Recommendation metadata is missing an `action` key — cannot execute."
        )
    if action not in SUPPORTED_ACTIONS:
        raise InvalidActionError(
            f"Unsupported execution action `{action}`. Supported: {sorted(SUPPORTED_ACTIONS)}."
        )
    return {
        "provider": provider,
        "action": action,
        "external_id": meta.get("external_id"),
        "external_account_id": meta.get("external_account_id"),
        "payload": meta.get("payload") or {},
    }


# ---------------------------------------------------------------------------
# Connection + provider resolution
# ---------------------------------------------------------------------------


def _resolve_connection(
    db: Session, *, workspace_id: UUID, provider_id: str
) -> tuple[type[BaseProvider], str]:
    provider_cls = get_provider(provider_id)
    if not provider_cls.is_configured():
        raise ProviderNotConfiguredError(
            f"{provider_cls.display_name} integration is not configured on this server."
        )
    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == provider_id,
        )
        .first()
    )
    if (
        account is None
        or account.status != ConnectionStatus.CONNECTED
        or account.token is None
    ):
        raise AccountNotReadyError(
            f"{provider_id} is not connected for this workspace; connect it before executing."
        )

    # Refuse writes when the connected account doesn't carry the required
    # write scopes — e.g. a read-only OAuth grant snuck through. This prevents
    # the Budget Guardian or Autopilot from blasting an unauthorized provider
    # call that would 403 deep in the integration. The check is opportunistic:
    # account.scopes may be None for older grants — if so we trust the legacy
    # default (all `scopes` granted).
    required_write_scopes = list(provider_cls.write_scopes or [])
    granted = account.scopes or []
    if required_write_scopes and granted:
        missing = [s for s in required_write_scopes if s not in granted]
        if missing:
            raise AccountNotReadyError(
                f"{provider_id} is missing write scopes: "
                + ", ".join(missing)
                + " — reconnect with full permissions."
            )

    # Auto-refresh on the way out so a long-lived workspace doesn't hit
    # provider 401s the first time the access token rolls over.
    access_token = integration_service.get_fresh_access_token(db, account=account)
    return provider_cls, access_token


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _dispatch(
    *,
    provider_cls: type[BaseProvider],
    access_token: str,
    action: str,
    external_account_id: str | None,
    external_id: str | None,
    payload: dict,
) -> dict:
    if action in {"campaign.pause", "campaign.resume", "campaign.update_budget", "campaign.update_audience"}:
        if not external_id or not external_account_id:
            raise InvalidActionError(
                f"Action `{action}` requires external_id and external_account_id."
            )

    if action == "campaign.pause":
        return provider_cls.pause_campaign(
            access_token=access_token,
            external_account_id=external_account_id,  # type: ignore[arg-type]
            external_id=external_id,  # type: ignore[arg-type]
        )
    if action == "campaign.resume":
        return provider_cls.resume_campaign(
            access_token=access_token,
            external_account_id=external_account_id,  # type: ignore[arg-type]
            external_id=external_id,  # type: ignore[arg-type]
        )
    if action == "campaign.update_budget":
        daily = payload.get("daily_budget_cents")
        if not isinstance(daily, int) or daily <= 0:
            raise InvalidActionError(
                "campaign.update_budget needs payload.daily_budget_cents (positive int)."
            )
        return provider_cls.update_campaign_budget(
            access_token=access_token,
            external_account_id=external_account_id,  # type: ignore[arg-type]
            external_id=external_id,  # type: ignore[arg-type]
            daily_budget_cents=daily,
        )
    if action == "campaign.update_audience":
        targeting = payload.get("targeting")
        if not isinstance(targeting, dict) or not targeting:
            raise InvalidActionError(
                "campaign.update_audience needs payload.targeting (dict)."
            )
        return provider_cls.update_campaign_audience(
            access_token=access_token,
            external_account_id=external_account_id,  # type: ignore[arg-type]
            external_id=external_id,  # type: ignore[arg-type]
            targeting=targeting,
        )
    if action == "campaign.create":
        if not external_account_id:
            raise InvalidActionError(
                "campaign.create needs external_account_id (target ad account)."
            )
        return provider_cls.create_campaign(
            access_token=access_token,
            external_account_id=external_account_id,
            payload=payload,
        )
    raise InvalidActionError(f"Unsupported action `{action}`.")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def _build_execution_row(
    *,
    rec: Recommendation,
    plan: dict,
    is_revert: bool,
    reverts_execution_id: UUID | None,
    actor_user_id: UUID | None,
    idempotency_key: str | None = None,
) -> RecommendationExecution:
    return RecommendationExecution(
        workspace_id=rec.workspace_id,
        recommendation_id=rec.id,
        approval_id=rec.approval.id if rec.approval else None,
        provider=plan["provider"],
        action_type=plan["action"],
        status=ExecutionStatus.RUNNING,
        target_external_id=plan.get("external_id"),
        target_external_account_id=plan.get("external_account_id"),
        payload=plan.get("payload") or {},
        is_revert=is_revert,
        reverts_execution_id=reverts_execution_id,
        executed_by=actor_user_id,
        executed_at=datetime.now(timezone.utc),
        idempotency_key=idempotency_key,
    )


def _check_idempotency(
    db: Session,
    *,
    rec: Recommendation,
    idempotency_key: str | None,
) -> RecommendationExecution | None:
    """Return an existing execution that should be replayed instead of
    dispatching, or raise DuplicateExecutionError if a non-revertible prior
    execution would be clobbered.

    Two paths:
      * Caller supplied an Idempotency-Key — return the matching row verbatim
        if it exists (any status, including FAILED).
      * No key supplied — refuse to start a new execution if there's a RUNNING
        or SUCCEEDED-and-not-reverted prior. FAILED + REVERTED prior states
        are fair game for retry."""

    if idempotency_key is not None:
        existing = (
            db.query(RecommendationExecution)
            .filter(
                RecommendationExecution.workspace_id == rec.workspace_id,
                RecommendationExecution.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing is not None:
            return existing

    blocking = (
        db.query(RecommendationExecution)
        .filter(
            RecommendationExecution.recommendation_id == rec.id,
            RecommendationExecution.is_revert.is_(False),
            RecommendationExecution.status.in_(
                (ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED)
            ),
        )
        .order_by(RecommendationExecution.created_at.desc())
        .first()
    )
    if blocking is not None:
        raise DuplicateExecutionError(
            f"An execution for this recommendation is already "
            f"{blocking.status.value}. Revert or fail it before retrying.",
            existing_execution_id=blocking.id,
        )
    return None


def execute_recommendation(
    db: Session,
    *,
    rec: Recommendation,
    actor_user_id: UUID | None,
    request: Request | None = None,
    idempotency_key: str | None = None,
) -> RecommendationExecution:
    """Run the action described in `rec.metadata_json`. Caller must have already
    verified approval status.

    `idempotency_key` is recorded on the execution row and checked first: a
    second call with the same key returns the original execution unchanged,
    so a network retry never doubles a write. Even without an explicit key,
    we refuse to dispatch if a non-reverted prior execution is RUNNING or
    SUCCEEDED — see `_check_idempotency`."""

    plan = _extract_action_plan(rec)

    replay = _check_idempotency(db, rec=rec, idempotency_key=idempotency_key)
    if replay is not None:
        return replay

    # Build the execution row up front. The plan-limit + provider-resolution
    # gates run inside the same try/except as the dispatch so a capped or
    # disconnected workspace surfaces as a FAILED execution row (with a
    # clear error_message) rather than a bare 402/409 that's invisible to
    # the audit log.
    execution = _build_execution_row(
        rec=rec,
        plan=plan,
        is_revert=False,
        reverts_execution_id=None,
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(execution)
    db.flush()

    try:
        # A workspace at its outbound-writes/30d cap can't accidentally blow
        # through ad budgets via repeated approve cycles.
        billing_service.assert_within_outbound_write_limit(
            db, workspace_id=rec.workspace_id
        )
        provider_cls, access_token = _resolve_connection(
            db, workspace_id=rec.workspace_id, provider_id=plan["provider"]
        )
        result = _dispatch(
            provider_cls=provider_cls,
            access_token=access_token,
            action=plan["action"],
            external_account_id=plan.get("external_account_id"),
            external_id=plan.get("external_id"),
            payload=plan.get("payload") or {},
        )
    except (
        ProviderError,
        ProviderNotConfiguredError,
        InvalidActionError,
        AccountNotReadyError,
        billing_service.PlanLimitExceededError,
        integration_service.TokenRefreshFailedError,
    ) as exc:
        execution.status = ExecutionStatus.FAILED
        execution.error_message = str(exc)
        audit_service.log_event(
            db,
            workspace_id=rec.workspace_id,
            actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
            actor_id=actor_user_id,
            action="recommendation.execution_failed",
            resource_type="recommendation_execution",
            resource_id=execution.id,
            metadata={
                "recommendation_id": str(rec.id),
                "provider": plan["provider"],
                "action": plan["action"],
                "error": str(exc),
            },
            request=request,
        )
        db.commit()
        db.refresh(execution)
        raise ExecutionError(str(exc)) from exc

    execution.status = ExecutionStatus.SUCCEEDED
    execution.prior_state = result.get("prior_state")
    execution.result = _strip_secrets(result)

    rec.status = RecommendationStatus.EXECUTED
    if rec.approval is not None:
        rec.approval.status = ApprovalStatus.EXECUTED
        rec.approval.execution_result = {
            "execution_id": str(execution.id),
            "result": execution.result,
        }

    audit_service.log_event(
        db,
        workspace_id=rec.workspace_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        actor_id=actor_user_id,
        action="recommendation.executed",
        resource_type="recommendation_execution",
        resource_id=execution.id,
        metadata={
            "recommendation_id": str(rec.id),
            "provider": plan["provider"],
            "action": plan["action"],
            "external_id": plan.get("external_id"),
        },
        request=request,
    )

    billing_service.record_usage_event(
        db,
        workspace_id=rec.workspace_id,
        event_type=UsageEventType.OUTBOUND_WRITE,
        metadata={
            "provider": plan["provider"],
            "action": plan["action"],
            "execution_id": str(execution.id),
        },
    )

    db.commit()
    db.refresh(execution)
    return execution


def revert_execution(
    db: Session,
    *,
    execution: RecommendationExecution,
    actor_user_id: UUID | None,
    request: Request | None = None,
) -> RecommendationExecution:
    """Apply the inverse of a previously-succeeded execution."""

    if execution.status != ExecutionStatus.SUCCEEDED:
        raise InvalidActionError(
            f"Cannot revert an execution in status `{execution.status.value}`."
        )
    if execution.is_revert:
        raise InvalidActionError("Refusing to revert a revert.")

    rec = (
        db.query(Recommendation)
        .filter(Recommendation.id == execution.recommendation_id)
        .first()
    )
    if rec is None:
        raise InvalidActionError("Recommendation no longer exists.")

    revert_plan = _build_revert_plan(execution)
    provider_cls, access_token = _resolve_connection(
        db, workspace_id=rec.workspace_id, provider_id=execution.provider
    )

    revert_row = _build_execution_row(
        rec=rec,
        plan=revert_plan,
        is_revert=True,
        reverts_execution_id=execution.id,
        actor_user_id=actor_user_id,
    )
    db.add(revert_row)
    db.flush()

    try:
        result = _dispatch(
            provider_cls=provider_cls,
            access_token=access_token,
            action=revert_plan["action"],
            external_account_id=revert_plan.get("external_account_id"),
            external_id=revert_plan.get("external_id"),
            payload=revert_plan.get("payload") or {},
        )
    except (ProviderError, ProviderNotConfiguredError, InvalidActionError) as exc:
        revert_row.status = ExecutionStatus.FAILED
        revert_row.error_message = str(exc)
        audit_service.log_event(
            db,
            workspace_id=rec.workspace_id,
            actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
            actor_id=actor_user_id,
            action="recommendation.revert_failed",
            resource_type="recommendation_execution",
            resource_id=revert_row.id,
            metadata={
                "reverts_execution_id": str(execution.id),
                "error": str(exc),
            },
            request=request,
        )
        db.commit()
        db.refresh(revert_row)
        raise ExecutionError(str(exc)) from exc

    revert_row.status = ExecutionStatus.SUCCEEDED
    revert_row.result = _strip_secrets(result)

    execution.status = ExecutionStatus.REVERTED

    audit_service.log_event(
        db,
        workspace_id=rec.workspace_id,
        actor_type=AuditActorType.USER if actor_user_id else AuditActorType.SYSTEM,
        actor_id=actor_user_id,
        action="recommendation.reverted",
        resource_type="recommendation_execution",
        resource_id=revert_row.id,
        metadata={
            "reverts_execution_id": str(execution.id),
            "provider": execution.provider,
            "action": revert_plan["action"],
        },
        request=request,
    )

    db.commit()
    db.refresh(revert_row)
    return revert_row


def _build_revert_plan(execution: RecommendationExecution) -> dict:
    action = execution.action_type
    prior = execution.prior_state or {}
    if action in INVERSE_STATUS_ACTION:
        return {
            "provider": execution.provider,
            "action": INVERSE_STATUS_ACTION[action],
            "external_id": execution.target_external_id,
            "external_account_id": execution.target_external_account_id,
            "payload": {},
        }
    if action == "campaign.update_budget":
        prior_daily = prior.get("daily_budget_cents")
        if not prior_daily:
            raise InvalidActionError(
                "Cannot revert budget update — prior_state is missing daily_budget_cents."
            )
        return {
            "provider": execution.provider,
            "action": "campaign.update_budget",
            "external_id": execution.target_external_id,
            "external_account_id": execution.target_external_account_id,
            "payload": {"daily_budget_cents": int(prior_daily)},
        }
    if action == "campaign.update_audience":
        # Provider-specific revert.
        if execution.provider == "google_ads":
            # Build inverse ops: each criterion we created becomes a remove.
            # Removed criteria can't be restored without a pre-mutation snapshot,
            # which we don't capture — surface that gap loudly.
            created = prior.get("created_resource_names") or []
            removed = prior.get("removed_resource_names") or []
            if removed and not created:
                raise InvalidActionError(
                    "Cannot revert a Google Ads audience update that only removed "
                    "criteria — restoring removed criteria requires a snapshot we "
                    "did not capture."
                )
            if not created:
                raise InvalidActionError(
                    "Google Ads audience update has no revertible state."
                )
            inverse_ops = [{"remove": rn} for rn in created]
            return {
                "provider": execution.provider,
                "action": "campaign.update_audience",
                "external_id": execution.target_external_id,
                "external_account_id": execution.target_external_account_id,
                "payload": {"targeting": {"operations": inverse_ops}},
            }
        # Meta + LinkedIn capture full prior targeting we can replay verbatim.
        targeting = prior.get("targetingCriteria") or prior
        return {
            "provider": execution.provider,
            "action": "campaign.update_audience",
            "external_id": execution.target_external_id,
            "external_account_id": execution.target_external_account_id,
            "payload": {"targeting": targeting},
        }
    if action == "campaign.create":
        # Best-effort: pause the newly-created campaign instead of deleting.
        return {
            "provider": execution.provider,
            "action": "campaign.pause",
            "external_id": (execution.result or {}).get("external_id"),
            "external_account_id": execution.target_external_account_id,
            "payload": {},
        }
    raise InvalidActionError(f"Action `{action}` is not revertible.")


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_executions_for_recommendation(
    db: Session, *, workspace_id: UUID, recommendation_id: UUID
) -> list[RecommendationExecution]:
    return (
        db.query(RecommendationExecution)
        .filter(
            RecommendationExecution.workspace_id == workspace_id,
            RecommendationExecution.recommendation_id == recommendation_id,
        )
        .order_by(RecommendationExecution.created_at.asc())
        .all()
    )


def get_execution(
    db: Session, *, workspace_id: UUID, execution_id: UUID
) -> RecommendationExecution:
    row = (
        db.query(RecommendationExecution)
        .filter(
            RecommendationExecution.id == execution_id,
            RecommendationExecution.workspace_id == workspace_id,
        )
        .first()
    )
    if row is None:
        raise InvalidActionError("Execution not found in this workspace.")
    return row


def _strip_secrets(payload: Any) -> Any:
    """Defensive scrubber so we never persist raw access tokens/cookies into the db."""

    if isinstance(payload, dict):
        return {
            k: "[redacted]" if k.lower() in {"access_token", "refresh_token", "authorization"}
            else _strip_secrets(v)
            for k, v in payload.items()
        }
    if isinstance(payload, list):
        return [_strip_secrets(v) for v in payload]
    return payload
