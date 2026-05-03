"""Autopilot service.

Centralizes the safety harness for *automated* execution of recommendations.
This module is the only place that may auto-approve a recommendation on the
workspace's behalf — it must run every guardrail before delegating to
`recommendation_service.approve_recommendation` with `auto_execute=True`.

Hard rules (mirrored from CLAUDE.md §14):
1. Mode must be AUTOPILOT — anything else returns `denied:not_autopilot`.
2. Stop-loss flag short-circuits everything.
3. Risk ceiling: rec.risk_level <= config.risk_ceiling.
4. Action allowlist: rec.recommendation_type in config.allowed_action_types.
5. Spend cap: any action with a `budget_increase_cents` metadata field must
   stay within max_daily_spend_increase_cents AND max_pct_increase_per_change.
6. Min conversion threshold: only campaigns with conversions >= threshold
   may be increased; new-spend actions are exempt.
7. Every auto-approval is audit-logged with actor_type=SYSTEM.

The Budget Guardian is responsible for *flipping the stop_loss_active flag*
when conditions deteriorate; this module trusts that flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.models.audit_log import AuditActorType
from app.models.autopilot_config import AutopilotConfig, AutopilotMode
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    RiskLevel,
)
from app.security.permissions import Role
from app.services import audit_service, recommendation_service

log = get_logger(__name__)


_RISK_RANK = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3}


class AutopilotConfigNotFoundError(AdVantaError):
    status_code = 404
    code = "autopilot_config_not_found"


# ---------------------------------------------------------------------------
# Config CRUD (used by the API + admin tooling)
# ---------------------------------------------------------------------------


def get_or_create_config(db: Session, *, workspace_id: UUID) -> AutopilotConfig:
    config = (
        db.query(AutopilotConfig)
        .filter(AutopilotConfig.workspace_id == workspace_id)
        .first()
    )
    if config is None:
        config = AutopilotConfig(
            id=uuid4(),
            workspace_id=workspace_id,
            mode=AutopilotMode.OFF,
            risk_ceiling=RiskLevel.LOW,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def update_config(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    patch: dict[str, Any],
) -> AutopilotConfig:
    """Apply a partial update. Audit-logs every transition into AUTOPILOT
    mode so we can prove informed opt-in."""
    config = get_or_create_config(db, workspace_id=workspace_id)
    previous_mode = config.mode

    if "mode" in patch:
        new_mode = AutopilotMode(patch["mode"])
        config.mode = new_mode
    if "max_daily_spend_increase_cents" in patch:
        config.max_daily_spend_increase_cents = patch["max_daily_spend_increase_cents"]
    if "max_daily_spend_total_cents" in patch:
        config.max_daily_spend_total_cents = patch["max_daily_spend_total_cents"]
    if "max_pct_increase_per_change" in patch:
        config.max_pct_increase_per_change = patch["max_pct_increase_per_change"]
    if "min_conversion_threshold" in patch:
        config.min_conversion_threshold = patch["min_conversion_threshold"]
    if "allowed_action_types" in patch:
        config.allowed_action_types = list(patch["allowed_action_types"] or [])
    if "risk_ceiling" in patch:
        config.risk_ceiling = RiskLevel(patch["risk_ceiling"])
    if "stop_loss_active" in patch:
        config.stop_loss_active = bool(patch["stop_loss_active"])
        if not config.stop_loss_active:
            config.stop_loss_reason = None
    if "stop_loss_reason" in patch:
        config.stop_loss_reason = patch["stop_loss_reason"]

    # Refuse to enter AUTOPILOT without all guardrails populated.
    if config.mode == AutopilotMode.AUTOPILOT:
        missing = _missing_guardrails(config)
        if missing:
            raise _ConfigInvalidError(
                "Cannot enable AUTOPILOT mode: missing guardrails: "
                + ", ".join(missing)
            )

    db.commit()
    db.refresh(config)

    if previous_mode != config.mode:
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER,
            actor_id=actor_user_id,
            action="autopilot.mode_changed",
            resource_type="autopilot_config",
            resource_id=config.id,
            metadata={
                "from": previous_mode.value,
                "to": config.mode.value,
            },
        )
        db.commit()
    return config


class _ConfigInvalidError(AdVantaError):
    status_code = 422
    code = "autopilot_config_invalid"


def _missing_guardrails(config: AutopilotConfig) -> list[str]:
    missing: list[str] = []
    if config.max_daily_spend_increase_cents is None:
        missing.append("max_daily_spend_increase_cents")
    if config.max_daily_spend_total_cents is None:
        missing.append("max_daily_spend_total_cents")
    if config.max_pct_increase_per_change is None:
        missing.append("max_pct_increase_per_change")
    if not config.allowed_action_types:
        missing.append("allowed_action_types")
    return missing


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------


@dataclass
class AutopilotVerdict:
    """Returned by `evaluate_recommendation`. `allow=True` means every
    guardrail passes and the rec is safe to auto-approve. Otherwise `reason`
    explains the first failing rule."""

    allow: bool
    reason: str
    matched_rules: list[str]


def evaluate_recommendation(
    db: Session, *, rec: Recommendation, config: AutopilotConfig | None = None
) -> AutopilotVerdict:
    """Pure check — no DB writes. Used by both the scan loop and the API
    surface (`POST /autopilot/preview`) so the verdict is consistent."""

    if config is None:
        config = (
            db.query(AutopilotConfig)
            .filter(AutopilotConfig.workspace_id == rec.workspace_id)
            .first()
        )

    matched: list[str] = []

    if config is None or config.mode != AutopilotMode.AUTOPILOT:
        return AutopilotVerdict(False, "not_autopilot", matched)
    matched.append("mode_autopilot")

    if config.stop_loss_active:
        return AutopilotVerdict(
            False,
            f"stop_loss_active:{config.stop_loss_reason or 'unspecified'}",
            matched,
        )
    matched.append("stop_loss_clear")

    missing = _missing_guardrails(config)
    if missing:
        return AutopilotVerdict(
            False, f"guardrails_missing:{','.join(missing)}", matched
        )
    matched.append("guardrails_complete")

    if rec.status != RecommendationStatus.OPEN:
        return AutopilotVerdict(False, f"rec_not_open:{rec.status.value}", matched)
    matched.append("rec_open")

    if _RISK_RANK[rec.risk_level] > _RISK_RANK[config.risk_ceiling]:
        return AutopilotVerdict(
            False,
            f"risk_above_ceiling:{rec.risk_level.value}>{config.risk_ceiling.value}",
            matched,
        )
    matched.append("risk_within_ceiling")

    allowed = config.allowed_action_types or []
    if rec.recommendation_type not in allowed:
        return AutopilotVerdict(
            False,
            f"action_not_allowed:{rec.recommendation_type}",
            matched,
        )
    matched.append("action_allowed")

    metadata = rec.metadata_json or {}
    increase = metadata.get("budget_increase_cents")
    if isinstance(increase, int) and increase > 0:
        if increase > (config.max_daily_spend_increase_cents or 0):
            return AutopilotVerdict(
                False,
                "spend_increase_above_cap",
                matched,
            )
        matched.append("spend_increase_within_cap")

        pct = metadata.get("pct_increase")
        if isinstance(pct, (int, float)) and pct > (
            config.max_pct_increase_per_change or 0
        ):
            return AutopilotVerdict(
                False,
                f"pct_increase_above_cap:{pct}>{config.max_pct_increase_per_change}",
                matched,
            )
        if pct is not None:
            matched.append("pct_increase_within_cap")

        conversions = metadata.get("recent_conversions")
        if config.min_conversion_threshold is not None and isinstance(
            conversions, int
        ):
            if conversions < config.min_conversion_threshold:
                return AutopilotVerdict(
                    False,
                    f"conversions_below_threshold:{conversions}<{config.min_conversion_threshold}",
                    matched,
                )
            matched.append("conversions_above_threshold")

    return AutopilotVerdict(True, "allow", matched)


# ---------------------------------------------------------------------------
# Scan loop — picks all auto-eligible pending recs and approves them.
# ---------------------------------------------------------------------------


def auto_approve_pending(
    db: Session, *, workspace_id: UUID, system_actor_id: UUID
) -> dict[str, Any]:
    """Iterate every OPEN recommendation in the workspace, evaluate it under
    autopilot rules, and auto-approve those that pass. Used by the periodic
    scan (Celery beat). Returns a summary."""

    config = get_or_create_config(db, workspace_id=workspace_id)
    if config.mode != AutopilotMode.AUTOPILOT:
        return {"workspace_id": str(workspace_id), "scanned": 0, "approved": 0, "skipped_reason": "not_autopilot"}

    open_recs = (
        db.query(Recommendation)
        .filter(
            Recommendation.workspace_id == workspace_id,
            Recommendation.status == RecommendationStatus.OPEN,
        )
        .all()
    )

    approved = 0
    declined: list[dict[str, str]] = []

    for rec in open_recs:
        verdict = evaluate_recommendation(db, rec=rec, config=config)
        if not verdict.allow:
            declined.append({"id": str(rec.id), "reason": verdict.reason})
            continue
        try:
            recommendation_service.approve_recommendation(
                db,
                workspace_id=workspace_id,
                recommendation_id=rec.id,
                actor_user_id=system_actor_id,
                actor_role=Role.OWNER,  # autopilot writes as workspace-owner
                # Audit attribution: SYSTEM actor + autopilot-specific action
                # name. This produces a single accurate audit row instead of
                # layering a USER `recommendation.approved` underneath a
                # SYSTEM `autopilot.approved`.
                actor_type=AuditActorType.SYSTEM,
                audit_action="autopilot.approved",
                audit_metadata_extra={"matched_rules": verdict.matched_rules},
            )
        except Exception as exc:  # noqa: BLE001 — log and continue
            log.warning(
                "autopilot.approve.failed",
                recommendation_id=str(rec.id),
                error=str(exc),
            )
            declined.append({"id": str(rec.id), "reason": f"approve_error:{exc}"})
            continue
        approved += 1
    db.commit()
    return {
        "workspace_id": str(workspace_id),
        "scanned": len(open_recs),
        "approved": approved,
        "declined": declined,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
