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
5. Per-change spend cap: the increase a spend-raising action would cause —
   derived structurally from the target budget vs the campaign's CURRENT
   budget, not from self-declared metadata — must stay within
   max_daily_spend_increase_cents AND max_pct_increase_per_change. If the
   baseline can't be determined the action FAILS CLOSED.
6. Daily-total ceiling: today's cumulative auto-approved increases (from the
   audit trail) plus this one must stay within max_daily_spend_total_cents, so
   many in-cap increases can't blow past the absolute daily limit.
7. Min conversion threshold: only campaigns with conversions >= threshold
   may be increased; new-spend actions are exempt.
8. Every auto-approval is audit-logged with actor_type=SYSTEM and the increase.

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
from app.models.audit_log import AuditActorType, AuditLog
from app.models.autopilot_config import AutopilotConfig, AutopilotMode
from app.models.campaign import Campaign
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
    explains the first failing rule. `increase_cents` is the spend increase the
    action would cause (0 for non-raising actions) so the scan loop can both
    record it in the audit trail and enforce the cumulative daily ceiling."""

    allow: bool
    reason: str
    matched_rules: list[str]
    increase_cents: int = 0


# ---------------------------------------------------------------------------
# Spend derivation — structural, not metadata-dependent.
#
# The per-change and daily-total caps must apply to ANY spend-raising action,
# not only ones that happen to self-declare `budget_increase_cents`. For a
# `campaign.update_budget` rec we derive the real increase from the target
# budget in the payload versus the campaign's current budget. When the baseline
# can't be determined we FAIL CLOSED (treat as raising-but-unbounded) so a stale
# or missing budget can never let an uncapped increase through.
# ---------------------------------------------------------------------------


def _load_campaign_budget(
    db: Session, metadata: dict[str, Any], workspace_id: UUID
) -> int | None:
    cid = metadata.get("campaign_id")
    if not cid:
        return None
    try:
        campaign_uuid = UUID(str(cid))
    except (ValueError, TypeError):
        return None
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_uuid, Campaign.workspace_id == workspace_id)
        .first()
    )
    return campaign.daily_budget_cents if campaign else None


def _derive_increase(
    db: Session, *, rec: Recommendation
) -> tuple[bool, int | None, float | None]:
    """Return (is_spend_raising, increase_cents, pct_increase).

    `increase_cents is None` while `is_spend_raising is True` means the increase
    can't be bounded (unknown baseline) and the caller must fail closed."""
    metadata = rec.metadata_json or {}

    # 1. Explicit increase declared by the producer (autonomous scale detector).
    explicit = metadata.get("budget_increase_cents")
    if isinstance(explicit, int) and explicit > 0:
        pct = metadata.get("pct_increase")
        return True, explicit, (float(pct) if isinstance(pct, (int, float)) else None)

    # 2. Budget update — derive the increase from payload target vs current.
    if rec.recommendation_type == "campaign.update_budget":
        target = (metadata.get("payload") or {}).get("daily_budget_cents")
        if not isinstance(target, int) or target <= 0:
            return True, None, None  # raising, unknown target -> fail closed
        current = _load_campaign_budget(db, metadata, rec.workspace_id)
        if current is None:
            return True, None, None  # raising, unknown baseline -> fail closed
        if target <= current:
            return False, 0, 0.0  # a decrease / no raise
        inc = target - current
        pct = (inc / current * 100) if current else None
        return True, inc, pct

    # 3. Anything else is not a quantifiable budget raise (pause/resume etc.);
    #    those remain gated by the risk-ceiling + allowlist rules.
    return False, 0, 0.0


def _todays_autopilot_increase_cents(db: Session, *, workspace_id: UUID) -> int:
    """Sum of budget increases already auto-approved by autopilot for this
    workspace since 00:00 UTC today, read from the (committed) audit trail."""
    day_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.workspace_id == workspace_id,
            AuditLog.action == "autopilot.approved",
            AuditLog.created_at >= day_start,
        )
        .all()
    )
    total = 0
    for row in rows:
        value = (row.metadata_json or {}).get("budget_increase_cents")
        if isinstance(value, int) and value > 0:
            total += value
    return total


def evaluate_recommendation(
    db: Session,
    *,
    rec: Recommendation,
    config: AutopilotConfig | None = None,
    pending_increase_cents: int = 0,
) -> AutopilotVerdict:
    """Read-only check (no writes) of every autopilot guardrail. Used by both
    the scan loop and the API surface (`POST /autopilot/preview`) so the verdict
    is consistent. `pending_increase_cents` lets a caller account for increases
    it has approved but not yet committed when enforcing the daily ceiling."""

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
    is_raise, increase, pct = _derive_increase(db, rec=rec)
    if is_raise:
        # Fail closed: a spend-raising action whose increase we can't bound
        # (unknown/stale baseline) is never auto-approved.
        if increase is None:
            return AutopilotVerdict(False, "spend_baseline_unknown", matched)

        if increase > (config.max_daily_spend_increase_cents or 0):
            return AutopilotVerdict(False, "spend_increase_above_cap", matched, increase_cents=increase)
        matched.append("spend_increase_within_cap")

        if pct is not None and pct > (config.max_pct_increase_per_change or 0):
            return AutopilotVerdict(
                False,
                f"pct_increase_above_cap:{pct:.1f}>{config.max_pct_increase_per_change}",
                matched,
                increase_cents=increase,
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
                    increase_cents=increase,
                )
            matched.append("conversions_above_threshold")

        # Absolute daily ceiling: today's already-auto-approved increases
        # (committed audit trail) PLUS any approved earlier in this same scan
        # (`pending_increase_cents`) PLUS this one must stay within the cap the
        # owner was required to set. This is what stops many in-cap increases
        # from cumulatively blowing past the daily total.
        if config.max_daily_spend_total_cents is not None:
            already = _todays_autopilot_increase_cents(db, workspace_id=rec.workspace_id)
            projected = already + pending_increase_cents + increase
            if projected > config.max_daily_spend_total_cents:
                return AutopilotVerdict(
                    False,
                    f"daily_total_above_cap:{projected}>{config.max_daily_spend_total_cents}",
                    matched,
                    increase_cents=increase,
                )
            matched.append("daily_total_within_cap")

    return AutopilotVerdict(True, "allow", matched, increase_cents=(increase or 0))


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
        # In-flight kill switch: re-read the config each iteration so an owner
        # flipping mode OFF or arming stop-loss mid-scan halts further
        # auto-approvals immediately rather than at the next scan. (Each prior
        # approval commits, so the refreshed row reflects a concurrent change.)
        db.refresh(config)
        if config.mode != AutopilotMode.AUTOPILOT:
            declined.append({"id": str(rec.id), "reason": "halted:not_autopilot"})
            break
        if config.stop_loss_active:
            declined.append({"id": str(rec.id), "reason": "halted:stop_loss_active"})
            break

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
                # SYSTEM `autopilot.approved`. The recorded
                # `budget_increase_cents` is what the daily-total ceiling reads
                # back on the next iteration.
                actor_type=AuditActorType.SYSTEM,
                audit_action="autopilot.approved",
                audit_metadata_extra={
                    "matched_rules": verdict.matched_rules,
                    "budget_increase_cents": verdict.increase_cents,
                },
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
