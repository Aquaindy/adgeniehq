"""Monthly run-fee accrual: real-spend-based rollup + all-workspaces job."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.campaign import Campaign, CampaignStatus
from app.models.fee_accrual import FeeAccrual, FeeAccrualStatus, FeeType
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.security.passwords import hash_password
from app.security.permissions import MemberStatus, Role
from app.services import fee_service, metrics_service


def _seed(db: Session, *, email: str) -> tuple[User, Workspace]:
    user = User(email=email, hashed_password=hash_password("correct-horse-9"), is_active=True)
    db.add(user)
    db.flush()
    ws = Workspace(name="T", slug=f"t-{email.split('@')[0]}")
    db.add(ws)
    db.flush()
    db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=Role.OWNER, status=MemberStatus.ACTIVE))
    db.commit()
    return user, ws


def _campaign(db: Session, *, ws: Workspace, budget: int = 4000) -> Campaign:
    c = Campaign(
        workspace_id=ws.id, provider="meta_ads", external_id="100", external_account_id="act_42",
        name="C", status=CampaignStatus.ACTIVE, objective="Lead generation",
        daily_budget_cents=budget, currency="USD", last_synced_at=datetime.now(timezone.utc), raw_payload={},
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _period_now() -> str:
    n = datetime.now(timezone.utc)
    return f"{n.year:04d}-{n.month:02d}"


def test_db_index_blocks_duplicate_run_accrual(db_session: Session) -> None:
    """The partial unique index is the no-double-bill guarantee: a duplicate
    (campaign, fee_type, period) accrual is rejected at the database level even
    if the app-level dedup is bypassed."""
    _, ws = _seed(db_session, email="dup@example.com")
    c = _campaign(db_session, ws=ws)

    def _row() -> FeeAccrual:
        return FeeAccrual(
            workspace_id=ws.id, campaign_id=c.id, fee_type=FeeType.RUN_FLAT,
            period="2026-06", amount_cents=500, status=FeeAccrualStatus.ACCRUED,
        )

    db_session.add(_row())
    db_session.commit()
    db_session.add(_row())
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_db_index_blocks_duplicate_listing_accrual(db_session: Session) -> None:
    _, ws = _seed(db_session, email="dup2@example.com")
    c = _campaign(db_session, ws=ws)

    def _row() -> FeeAccrual:
        return FeeAccrual(
            workspace_id=ws.id, campaign_id=c.id, fee_type=FeeType.LISTING,
            period=None, amount_cents=2500, status=FeeAccrualStatus.ACCRUED,
        )

    db_session.add(_row())
    db_session.commit()
    db_session.add(_row())
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_run_fee_uses_real_spend_from_metrics(db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    c = _campaign(db_session, ws=ws)
    today = datetime.now(timezone.utc).date()
    metrics_service.upsert_daily(
        db_session, campaign=c, on_date=today, impressions=10000, clicks=500,
        spend_cents=100000, conversions=20,
    )
    db_session.commit()

    out = fee_service.accrue_run_fees_for_workspace(
        db_session, workspace_id=ws.id, period=_period_now()
    )
    pct = [a for a in out if a.fee_type == FeeType.RUN_PCT]
    assert len(pct) == 1
    # Default rate = 10% of spend; basis = the real metric spend (not the estimate).
    assert pct[0].amount_cents == 10000  # 10% of 100000
    assert pct[0].basis_spend_cents == 100000


def test_run_fee_falls_back_to_estimate_without_metrics(db_session: Session) -> None:
    _, ws = _seed(db_session, email="o@example.com")
    _campaign(db_session, ws=ws, budget=4000)  # no metrics
    out = fee_service.accrue_run_fees_for_workspace(
        db_session, workspace_id=ws.id, period=_period_now()
    )
    pct = [a for a in out if a.fee_type == FeeType.RUN_PCT]
    # Estimate = daily_budget × 30 = 120000; 10% = 12000.
    assert pct[0].basis_spend_cents == 120000
    assert pct[0].amount_cents == 12000


def test_accrue_all_workspaces_is_idempotent(db_session: Session) -> None:
    _, ws1 = _seed(db_session, email="a@example.com")
    _, ws2 = _seed(db_session, email="b@example.com")
    _campaign(db_session, ws=ws1)
    _campaign(db_session, ws=ws2)
    period = _period_now()

    first = fee_service.accrue_run_fees_all_workspaces(db_session, period=period)
    assert first["workspaces"] == 2
    assert first["accruals_created"] == 2  # one RUN_PCT each (flat rate is 0)

    second = fee_service.accrue_run_fees_all_workspaces(db_session, period=period)
    assert second["accruals_created"] == 0  # nothing new on re-run


def test_monthly_task_defaults_to_previous_period(db_session: Session) -> None:
    from app.workers.tasks import monthly_run_fee_accrual_task

    _, ws = _seed(db_session, email="o@example.com")
    _campaign(db_session, ws=ws)
    # No explicit period → task computes the previous month and accrues for it.
    result = monthly_run_fee_accrual_task.run()
    n = datetime.now(timezone.utc)
    py, pm = (n.year, n.month - 1) if n.month > 1 else (n.year - 1, 12)
    assert result["period"] == f"{py:04d}-{pm:02d}"

    rows = (
        db_session.query(FeeAccrual)
        .filter(FeeAccrual.workspace_id == ws.id, FeeAccrual.period == result["period"])
        .all()
    )
    assert len(rows) >= 1
