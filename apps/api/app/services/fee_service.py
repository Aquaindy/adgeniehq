"""Platform fee engine — provider-agnostic.

Computes and records the fees AdVanta charges customers for ad activity:
  * a one-time **listing fee** per campaign launched through AdVanta,
  * a recurring **run fee** = flat + percentage-of-spend, accrued per month.

This module knows nothing about Stripe/Paddle/PayPal. It only resolves rates
from the admin-configured schedule and writes owed amounts to the `fee_accruals`
ledger. A separate collection layer bills the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.campaign import Campaign, CampaignStatus
from app.models.fee_accrual import FeeAccrual, FeeAccrualStatus, FeeType
from app.models.fee_rule import FeeRule

# Average days per month for spend → monthly-fee estimates.
_DAYS_PER_MONTH = 30


class FeeRuleNotFoundError(AdVantaError):
    status_code = 404
    code = "fee_rule_not_found"


# ---------------------------------------------------------------------------
# Default rates — used when no rule matches, so quotes/accruals always work
# out of the box. The admin overrides these by creating rules.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rates:
    listing_fee_cents: int
    run_flat_fee_cents: int
    run_pct_basis_points: int
    source: str  # "rule" | "default"
    rule_id: UUID | None


DEFAULT_RATES = Rates(
    listing_fee_cents=2500,  # $25 one-time per campaign
    run_flat_fee_cents=0,
    run_pct_basis_points=1000,  # 10% of spend
    source="default",
    rule_id=None,
)


# ---------------------------------------------------------------------------
# Campaign-type normalization — map a platform objective to a coarse bucket the
# fee schedule is keyed on.
# ---------------------------------------------------------------------------

_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("sales", ("sale", "conversion", "purchase", "catalog", "ecommerce", "checkout", "revenue")),
    ("leads", ("lead", "signup", "sign-up", "form", "acquisition", "subscriber")),
    ("app", ("app_install", "app install", "mobile_app", "app promotion")),
    ("traffic", ("traffic", "link_click", "clicks", "visit")),
    ("engagement", ("engage", "post_engagement", "page_likes", "messages", "video_view", "view")),
    ("awareness", ("aware", "reach", "brand", "impression")),
]


def normalize_campaign_type(objective: str | None) -> str:
    if not objective:
        return "other"
    text = objective.strip().lower()
    for label, keywords in _TYPE_KEYWORDS:
        if any(k in text for k in keywords):
            return label
    return "other"


CAMPAIGN_TYPES = ["leads", "sales", "traffic", "awareness", "engagement", "app", "other"]


# ---------------------------------------------------------------------------
# Rule resolution
# ---------------------------------------------------------------------------


def _specificity(rule: FeeRule, provider: str, campaign_type: str) -> int:
    """Higher = more specific match. -1 means it doesn't apply."""
    if rule.provider is not None and rule.provider != provider:
        return -1
    if rule.campaign_type is not None and rule.campaign_type != campaign_type:
        return -1
    return (1 if rule.provider is not None else 0) + (
        1 if rule.campaign_type is not None else 0
    )


def resolve_rule(
    db: Session, *, provider: str | None, campaign_type: str
) -> FeeRule | None:
    provider = provider or ""
    candidates = db.query(FeeRule).filter(FeeRule.is_active.is_(True)).all()
    best: FeeRule | None = None
    best_score = -1
    for rule in candidates:
        score = _specificity(rule, provider, campaign_type)
        if score > best_score:
            best, best_score = rule, score
    return best


def effective_rates(
    db: Session, *, provider: str | None, campaign_type: str
) -> Rates:
    rule = resolve_rule(db, provider=provider, campaign_type=campaign_type)
    if rule is None:
        return DEFAULT_RATES
    return Rates(
        listing_fee_cents=rule.listing_fee_cents,
        run_flat_fee_cents=rule.run_flat_fee_cents,
        run_pct_basis_points=rule.run_pct_basis_points,
        source="rule",
        rule_id=rule.id,
    )


# ---------------------------------------------------------------------------
# Quoting (preview — no DB writes)
# ---------------------------------------------------------------------------


@dataclass
class FeeQuote:
    provider: str | None
    campaign_type: str
    listing_fee_cents: int
    run_flat_fee_cents: int
    run_pct_basis_points: int
    est_monthly_spend_cents: int
    est_monthly_run_fee_cents: int
    est_first_month_total_cents: int
    source: str
    rule_id: UUID | None


def quote_fees(
    db: Session,
    *,
    provider: str | None,
    campaign_type: str,
    daily_budget_cents: int | None,
) -> FeeQuote:
    rates = effective_rates(db, provider=provider, campaign_type=campaign_type)
    est_monthly_spend = (daily_budget_cents or 0) * _DAYS_PER_MONTH
    run_pct_fee = est_monthly_spend * rates.run_pct_basis_points // 10_000
    est_monthly_run_fee = rates.run_flat_fee_cents + run_pct_fee
    return FeeQuote(
        provider=provider,
        campaign_type=campaign_type,
        listing_fee_cents=rates.listing_fee_cents,
        run_flat_fee_cents=rates.run_flat_fee_cents,
        run_pct_basis_points=rates.run_pct_basis_points,
        est_monthly_spend_cents=est_monthly_spend,
        est_monthly_run_fee_cents=est_monthly_run_fee,
        est_first_month_total_cents=rates.listing_fee_cents + est_monthly_run_fee,
        source=rates.source,
        rule_id=rates.rule_id,
    )


def quote_for_campaign(db: Session, *, campaign: Campaign) -> FeeQuote:
    return quote_fees(
        db,
        provider=campaign.provider,
        campaign_type=normalize_campaign_type(campaign.objective),
        daily_budget_cents=campaign.daily_budget_cents,
    )


# ---------------------------------------------------------------------------
# Accrual (ledger writes)
# ---------------------------------------------------------------------------


def _current_period() -> str:
    now = datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def accrue_listing_fee(
    db: Session, *, campaign: Campaign, actor_user_id: UUID | None
) -> FeeAccrual | None:
    """Idempotent: one listing fee per campaign, ever. Returns the accrual
    (existing or new), or None if the resolved listing fee is 0."""
    existing = (
        db.query(FeeAccrual)
        .filter(
            FeeAccrual.campaign_id == campaign.id,
            FeeAccrual.fee_type == FeeType.LISTING,
            FeeAccrual.status != FeeAccrualStatus.VOID,
        )
        .first()
    )
    if existing is not None:
        return existing

    campaign_type = normalize_campaign_type(campaign.objective)
    rates = effective_rates(db, provider=campaign.provider, campaign_type=campaign_type)
    if rates.listing_fee_cents <= 0:
        return None

    accrual = FeeAccrual(
        workspace_id=campaign.workspace_id,
        campaign_id=campaign.id,
        fee_type=FeeType.LISTING,
        provider=campaign.provider,
        campaign_type=campaign_type,
        period=None,
        amount_cents=rates.listing_fee_cents,
        status=FeeAccrualStatus.ACCRUED,
        rule_id=rates.rule_id,
        created_by=actor_user_id,
        metadata_json={"campaign_name": campaign.name},
    )
    try:
        # Savepoint: a concurrent double-launch loses the race on the partial
        # unique index; return the winning row rather than 500-ing.
        with db.begin_nested():
            db.add(accrual)
            db.flush()
    except IntegrityError:
        return (
            db.query(FeeAccrual)
            .filter(
                FeeAccrual.campaign_id == campaign.id,
                FeeAccrual.fee_type == FeeType.LISTING,
                FeeAccrual.status != FeeAccrualStatus.VOID,
            )
            .first()
        )
    return accrual


def accrue_run_fees_for_campaign(
    db: Session,
    *,
    campaign: Campaign,
    period: str | None = None,
    spend_cents: int | None = None,
    actor_user_id: UUID | None = None,
) -> list[FeeAccrual]:
    """Accrue this period's run fees (flat + % of spend) for one campaign.

    Idempotent per (campaign, period, fee_type). `spend_cents` defaults to a
    daily-budget × days estimate when real spend isn't supplied."""
    period = period or _current_period()
    campaign_type = normalize_campaign_type(campaign.objective)
    rates = effective_rates(db, provider=campaign.provider, campaign_type=campaign_type)
    spend = spend_cents if spend_cents is not None else (campaign.daily_budget_cents or 0) * _DAYS_PER_MONTH

    created: list[FeeAccrual] = []

    def _ensure(fee_type: FeeType, amount: int, basis: int | None) -> None:
        if amount <= 0:
            return
        dup = (
            db.query(FeeAccrual)
            .filter(
                FeeAccrual.campaign_id == campaign.id,
                FeeAccrual.fee_type == fee_type,
                FeeAccrual.period == period,
                FeeAccrual.status != FeeAccrualStatus.VOID,
            )
            .first()
        )
        if dup is not None:
            return
        accrual = FeeAccrual(
            workspace_id=campaign.workspace_id,
            campaign_id=campaign.id,
            fee_type=fee_type,
            provider=campaign.provider,
            campaign_type=campaign_type,
            period=period,
            amount_cents=amount,
            basis_spend_cents=basis,
            status=FeeAccrualStatus.ACCRUED,
            rule_id=rates.rule_id,
            created_by=actor_user_id,
        )
        try:
            # Savepoint so a lost race (the partial unique index rejects the
            # duplicate) is a clean no-op rather than poisoning the transaction.
            with db.begin_nested():
                db.add(accrual)
                db.flush()
        except IntegrityError:
            return
        created.append(accrual)

    _ensure(FeeType.RUN_FLAT, rates.run_flat_fee_cents, None)
    _ensure(FeeType.RUN_PCT, spend * rates.run_pct_basis_points // 10_000, spend)
    return created


def _period_spend_cents(db: Session, *, campaign: Campaign, period: str) -> int | None:
    """Real spend for a campaign over a "YYYY-MM" period from campaign_metrics.
    Returns None when there are no metrics for the period (so the caller falls
    back to the daily-budget estimate); returns the real sum otherwise (which
    may legitimately be 0)."""
    from calendar import monthrange
    from datetime import date

    from app.models.campaign_metric import CampaignMetric

    try:
        year, month = int(period[:4]), int(period[5:7])
        start = date(year, month, 1)
        end = date(year, month, monthrange(year, month)[1])
    except (ValueError, IndexError):
        return None
    rows = (
        db.query(CampaignMetric.spend_cents)
        .filter(
            CampaignMetric.campaign_id == campaign.id,
            CampaignMetric.date >= start,
            CampaignMetric.date <= end,
        )
        .all()
    )
    if not rows:
        return None
    return sum(r[0] for r in rows)


def accrue_run_fees_for_workspace(
    db: Session, *, workspace_id: UUID, period: str | None = None
) -> list[FeeAccrual]:
    """Period rollup over all active campaigns in a workspace. Uses real synced
    spend for the period when available, else the daily-budget estimate."""
    period = period or _current_period()
    campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.workspace_id == workspace_id,
            Campaign.status == CampaignStatus.ACTIVE,
        )
        .all()
    )
    out: list[FeeAccrual] = []
    for c in campaigns:
        spend = _period_spend_cents(db, campaign=c, period=period)
        out.extend(
            accrue_run_fees_for_campaign(
                db, campaign=c, period=period, spend_cents=spend
            )
        )
    db.commit()
    return out


def accrue_run_fees_all_workspaces(
    db: Session, *, period: str | None = None
) -> dict:
    """Accrue this period's run fees across every workspace that has active
    campaigns. Idempotent per (campaign, period, fee_type) — safe to re-run."""
    period = period or _current_period()
    workspace_ids = [
        row[0]
        for row in db.query(Campaign.workspace_id)
        .filter(Campaign.status == CampaignStatus.ACTIVE)
        .distinct()
        .all()
    ]
    created = 0
    for ws_id in workspace_ids:
        created += len(accrue_run_fees_for_workspace(db, workspace_id=ws_id, period=period))
    return {
        "period": period,
        "workspaces": len(workspace_ids),
        "accruals_created": created,
    }


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def workspace_fee_summary(
    db: Session, *, workspace_id: UUID, period: str | None = None
) -> dict:
    period = period or _current_period()
    rows = (
        db.query(FeeAccrual)
        .filter(
            FeeAccrual.workspace_id == workspace_id,
            FeeAccrual.status != FeeAccrualStatus.VOID,
        )
        .all()
    )
    # Listing fees are one-time (period is NULL) — count those that belong to
    # this period by created_at month; run fees match `period` exactly.
    by_type: dict[str, int] = {"listing": 0, "run_flat": 0, "run_pct": 0}
    total = 0
    for r in rows:
        in_period = r.period == period or (
            r.period is None and f"{r.created_at.year:04d}-{r.created_at.month:02d}" == period
        )
        if not in_period:
            continue
        by_type[r.fee_type.value] = by_type.get(r.fee_type.value, 0) + r.amount_cents
        total += r.amount_cents
    return {
        "period": period,
        "total_cents": total,
        "by_type": by_type,
        "currency": "USD",
    }


def admin_revenue_summary(db: Session, *, period: str | None = None) -> dict:
    rows = db.query(FeeAccrual).filter(FeeAccrual.status != FeeAccrualStatus.VOID).all()
    period = period or _current_period()
    period_total = 0
    all_time_total = 0
    by_status: dict[str, int] = {}
    for r in rows:
        all_time_total += r.amount_cents
        by_status[r.status.value] = by_status.get(r.status.value, 0) + r.amount_cents
        r_period = r.period or f"{r.created_at.year:04d}-{r.created_at.month:02d}"
        if r_period == period:
            period_total += r.amount_cents
    return {
        "period": period,
        "period_total_cents": period_total,
        "all_time_total_cents": all_time_total,
        "by_status_cents": by_status,
        "accrual_count": len(rows),
        "currency": "USD",
    }


# ---------------------------------------------------------------------------
# Admin fee-rule CRUD
# ---------------------------------------------------------------------------


def list_rules(db: Session) -> list[FeeRule]:
    return (
        db.query(FeeRule)
        .order_by(FeeRule.provider.is_(None), FeeRule.provider, FeeRule.campaign_type)
        .all()
    )


def get_rule(db: Session, *, rule_id: UUID) -> FeeRule:
    rule = db.query(FeeRule).filter(FeeRule.id == rule_id).first()
    if rule is None:
        raise FeeRuleNotFoundError("Fee rule not found.")
    return rule


def upsert_rule(
    db: Session,
    *,
    provider: str | None,
    campaign_type: str | None,
    label: str,
    listing_fee_cents: int,
    run_flat_fee_cents: int,
    run_pct_basis_points: int,
    is_active: bool = True,
    actor_user_id: UUID | None = None,
) -> FeeRule:
    """Create or update the rule for a (provider, campaign_type) pair."""
    provider = provider or None
    campaign_type = campaign_type or None
    existing = (
        db.query(FeeRule)
        .filter(
            FeeRule.provider.is_(provider) if provider is None else FeeRule.provider == provider,
            FeeRule.campaign_type.is_(campaign_type)
            if campaign_type is None
            else FeeRule.campaign_type == campaign_type,
        )
        .first()
    )
    if existing is not None:
        existing.label = label
        existing.listing_fee_cents = listing_fee_cents
        existing.run_flat_fee_cents = run_flat_fee_cents
        existing.run_pct_basis_points = run_pct_basis_points
        existing.is_active = is_active
        db.commit()
        db.refresh(existing)
        return existing

    rule = FeeRule(
        provider=provider,
        campaign_type=campaign_type,
        label=label,
        listing_fee_cents=listing_fee_cents,
        run_flat_fee_cents=run_flat_fee_cents,
        run_pct_basis_points=run_pct_basis_points,
        is_active=is_active,
        created_by=actor_user_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def update_rule(db: Session, *, rule_id: UUID, updates: dict) -> FeeRule:
    rule = get_rule(db, rule_id=rule_id)
    for field in (
        "label",
        "listing_fee_cents",
        "run_flat_fee_cents",
        "run_pct_basis_points",
        "is_active",
    ):
        if field in updates and updates[field] is not None:
            setattr(rule, field, updates[field])
    db.commit()
    db.refresh(rule)
    return rule


def delete_rule(db: Session, *, rule_id: UUID) -> None:
    rule = get_rule(db, rule_id=rule_id)
    db.delete(rule)
    db.commit()
