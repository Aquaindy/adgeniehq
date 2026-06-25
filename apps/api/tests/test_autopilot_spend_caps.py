"""Autopilot spend-cap enforcement + scan-task coverage (launch blockers 5 & 6).

These guard the autonomous-spend engine:
  * per-change caps are derived STRUCTURALLY (target budget vs the campaign's
    current budget), not from self-declared metadata, and fail CLOSED when the
    baseline is unknown;
  * the absolute `max_daily_spend_total_cents` ceiling is enforced against the
    cumulative auto-approved increases for the day (across a single scan too);
  * `autopilot_scan_task` — the production entry point — only touches AUTOPILOT
    workspaces that have a real human owner, and is tenant-isolated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun, AgentRunStatus
from app.models.audit_log import AuditActorType, AuditLog
from app.models.autopilot_config import AutopilotConfig, AutopilotMode
from app.models.campaign import Campaign, CampaignStatus
from app.models.recommendation import (
    Recommendation,
    RecommendationStatus,
    RiskLevel,
)
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import autopilot_service


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _seed_ws(
    db: Session,
    *,
    email: str,
    mode: AutopilotMode = AutopilotMode.AUTOPILOT,
    allowed: list[str] | None = None,
    owner_role: Role = Role.OWNER,
    **cfg_overrides,
) -> tuple[User, Workspace, AutopilotConfig]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="WS", slug=f"ws-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id, user_id=user.id, role=owner_role, status=MemberStatus.ACTIVE
        )
    )
    cfg_kwargs = dict(
        workspace_id=ws.id,
        mode=mode,
        risk_ceiling=RiskLevel.HIGH,  # so risk-ceiling never masks a spend-cap test
        allowed_action_types=allowed or [],
        max_daily_spend_increase_cents=100_000,
        max_daily_spend_total_cents=1_000_000,
        max_pct_increase_per_change=1000,
        min_conversion_threshold=None,
    )
    cfg_kwargs.update(cfg_overrides)
    cfg = AutopilotConfig(**cfg_kwargs)
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return user, ws, cfg


def _campaign(db: Session, *, ws: Workspace, budget: int) -> Campaign:
    c = Campaign(
        workspace_id=ws.id,
        provider="meta_ads",
        external_id="100",
        external_account_id="act_42",
        name="C",
        status=CampaignStatus.ACTIVE,
        daily_budget_cents=budget,
        currency="USD",
        objective="Lead generation",
        last_synced_at=datetime.now(timezone.utc),
        raw_payload={},
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _seed_rec(
    db: Session,
    *,
    ws: Workspace,
    user: User,
    rec_type: str,
    risk: RiskLevel,
    metadata: dict,
) -> Recommendation:
    run = AgentRun(
        workspace_id=ws.id,
        triggered_by_user_id=user.id,
        agent_type="test",
        status=AgentRunStatus.SUCCEEDED,
        input_payload={},
        model_used="deterministic",
    )
    db.add(run)
    db.flush()
    rec = Recommendation(
        workspace_id=ws.id,
        agent_run_id=run.id,
        title="t",
        summary="—",
        recommendation_type=rec_type,
        risk_level=risk,
        expected_impact="—",
        suggested_action="—",
        status=RecommendationStatus.OPEN,
        metadata_json=metadata,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


# ---------------------------------------------------------------------------
# Blocker 5 — structural per-change cap + fail-closed
# ---------------------------------------------------------------------------


def test_update_budget_increase_is_derived_and_capped(db_session: Session) -> None:
    """A campaign.update_budget rec with NO self-declared budget_increase_cents
    is still capped, because the increase is derived from target vs current."""
    user, ws, cfg = _seed_ws(
        db_session,
        email="a@x.com",
        allowed=["campaign.update_budget"],
        max_daily_spend_increase_cents=2_000,
    )
    campaign = _campaign(db_session, ws=ws, budget=10_000)
    rec = _seed_rec(
        db_session,
        ws=ws,
        user=user,
        rec_type="campaign.update_budget",
        risk=RiskLevel.HIGH,
        metadata={
            "campaign_id": str(campaign.id),
            "payload": {"daily_budget_cents": 20_000},  # +$100 = 10_000c > 2_000c cap
        },
    )
    verdict = autopilot_service.evaluate_recommendation(db_session, rec=rec, config=cfg)
    assert verdict.allow is False
    assert verdict.reason == "spend_increase_above_cap"
    assert verdict.increase_cents == 10_000


def test_update_budget_within_cap_is_allowed(db_session: Session) -> None:
    user, ws, cfg = _seed_ws(
        db_session,
        email="a2@x.com",
        allowed=["campaign.update_budget"],
        max_daily_spend_increase_cents=10_000,
    )
    campaign = _campaign(db_session, ws=ws, budget=10_000)
    rec = _seed_rec(
        db_session,
        ws=ws,
        user=user,
        rec_type="campaign.update_budget",
        risk=RiskLevel.HIGH,
        metadata={
            "campaign_id": str(campaign.id),
            "payload": {"daily_budget_cents": 12_000},  # +2_000c, within cap
        },
    )
    verdict = autopilot_service.evaluate_recommendation(db_session, rec=rec, config=cfg)
    assert verdict.allow is True
    assert verdict.increase_cents == 2_000


def test_update_budget_fails_closed_when_baseline_unknown(db_session: Session) -> None:
    """If the campaign (baseline) can't be resolved, the increase can't be
    bounded — the action must fail closed, never auto-approve."""
    user, ws, cfg = _seed_ws(
        db_session, email="b@x.com", allowed=["campaign.update_budget"]
    )
    rec = _seed_rec(
        db_session,
        ws=ws,
        user=user,
        rec_type="campaign.update_budget",
        risk=RiskLevel.HIGH,
        metadata={
            "campaign_id": str(uuid4()),  # points at no campaign
            "payload": {"daily_budget_cents": 20_000},
        },
    )
    verdict = autopilot_service.evaluate_recommendation(db_session, rec=rec, config=cfg)
    assert verdict.allow is False
    assert verdict.reason == "spend_baseline_unknown"


def test_update_budget_decrease_is_not_a_raise(db_session: Session) -> None:
    user, ws, cfg = _seed_ws(
        db_session, email="b2@x.com", allowed=["campaign.update_budget"]
    )
    campaign = _campaign(db_session, ws=ws, budget=10_000)
    rec = _seed_rec(
        db_session,
        ws=ws,
        user=user,
        rec_type="campaign.update_budget",
        risk=RiskLevel.LOW,
        metadata={
            "campaign_id": str(campaign.id),
            "payload": {"daily_budget_cents": 4_000},  # a decrease
        },
    )
    verdict = autopilot_service.evaluate_recommendation(db_session, rec=rec, config=cfg)
    assert verdict.allow is True
    assert verdict.increase_cents == 0


# ---------------------------------------------------------------------------
# Blocker 5 — absolute daily-total ceiling
# ---------------------------------------------------------------------------


def test_daily_total_ceiling_blocks_when_today_sum_exceeds(db_session: Session) -> None:
    user, ws, cfg = _seed_ws(
        db_session,
        email="c@x.com",
        allowed=["paid_ads.budget_unset"],
        max_daily_spend_total_cents=50_000,
    )
    # 45_000c already auto-approved today (recorded in the audit trail).
    db_session.add(
        AuditLog(
            workspace_id=ws.id,
            actor_type=AuditActorType.SYSTEM,
            action="autopilot.approved",
            resource_type="recommendation",
            metadata_json={"budget_increase_cents": 45_000},
        )
    )
    db_session.commit()
    rec = _seed_rec(
        db_session,
        ws=ws,
        user=user,
        rec_type="paid_ads.budget_unset",
        risk=RiskLevel.LOW,
        metadata={"budget_increase_cents": 10_000},  # 45k + 10k = 55k > 50k
    )
    verdict = autopilot_service.evaluate_recommendation(db_session, rec=rec, config=cfg)
    assert verdict.allow is False
    assert verdict.reason.startswith("daily_total_above_cap")


def test_scan_stops_approving_when_daily_total_would_exceed(db_session: Session) -> None:
    """Two in-cap increases that cumulatively exceed the daily ceiling: the
    first is approved, the second is declined — the cumulative guard works
    across a single scan via the committed audit trail."""
    user, ws, cfg = _seed_ws(
        db_session,
        email="d@x.com",
        allowed=["paid_ads.budget_unset"],
        max_daily_spend_total_cents=15_000,
    )
    _seed_rec(
        db_session,
        ws=ws,
        user=user,
        rec_type="paid_ads.budget_unset",
        risk=RiskLevel.LOW,
        metadata={"budget_increase_cents": 10_000},
    )
    _seed_rec(
        db_session,
        ws=ws,
        user=user,
        rec_type="paid_ads.budget_unset",
        risk=RiskLevel.LOW,
        metadata={"budget_increase_cents": 10_000},
    )
    summary = autopilot_service.auto_approve_pending(
        db_session, workspace_id=ws.id, system_actor_id=user.id
    )
    assert summary["approved"] == 1
    assert any(
        d["reason"].startswith("daily_total_above_cap") for d in summary["declined"]
    )


# ---------------------------------------------------------------------------
# Blocker 6 — autopilot_scan_task end-to-end isolation
# ---------------------------------------------------------------------------


def test_scan_task_only_touches_autopilot_workspaces_with_owner(
    db_session: Session,
) -> None:
    # A: AUTOPILOT + owner + allowlisted passing rec -> approved
    ua, wsa, _ = _seed_ws(
        db_session,
        email="a3@x.com",
        mode=AutopilotMode.AUTOPILOT,
        allowed=["paid_ads.budget_unset"],
    )
    reca = _seed_rec(
        db_session, ws=wsa, user=ua, rec_type="paid_ads.budget_unset",
        risk=RiskLevel.LOW, metadata={"budget_increase_cents": 1_000},
    )
    # B: OFF + owner + rec -> untouched (not scanned at all)
    ub, wsb, _ = _seed_ws(
        db_session,
        email="b3@x.com",
        mode=AutopilotMode.OFF,
        allowed=["paid_ads.budget_unset"],
    )
    recb = _seed_rec(
        db_session, ws=wsb, user=ub, rec_type="paid_ads.budget_unset",
        risk=RiskLevel.LOW, metadata={"budget_increase_cents": 1_000},
    )
    # C: AUTOPILOT but NO owner (admin only) -> skipped, refuses to act
    uc, wsc, _ = _seed_ws(
        db_session,
        email="c3@x.com",
        mode=AutopilotMode.AUTOPILOT,
        allowed=["paid_ads.budget_unset"],
        owner_role=Role.ADMIN,
    )
    recc = _seed_rec(
        db_session, ws=wsc, user=uc, rec_type="paid_ads.budget_unset",
        risk=RiskLevel.LOW, metadata={"budget_increase_cents": 1_000},
    )

    from app.workers.tasks import autopilot_scan_task

    result = autopilot_scan_task.run()

    for rec in (reca, recb, recc):
        db_session.refresh(rec)
    assert reca.status == RecommendationStatus.APPROVED, "AUTOPILOT+owner should run"
    assert recb.status == RecommendationStatus.OPEN, "OFF workspace must be untouched"
    assert recc.status == RecommendationStatus.OPEN, "ownerless workspace must be skipped"
    # Only workspace A actually ran the approval loop.
    assert result["workspaces_scanned"] == 1
