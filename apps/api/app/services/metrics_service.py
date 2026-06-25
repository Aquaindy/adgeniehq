"""Campaign analytics — daily metrics storage, KPI derivation, and insights sync.

Stores raw daily counters in `campaign_metrics` and derives KPIs (CTR, CPC, CPM,
CPA, ROAS, conversion rate) on read so nothing stale is persisted. The sync pulls
real numbers from each platform's insights API via `provider.fetch_insights`;
platforms not yet wired return [] (no fabricated data).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.integrations.base import ProviderError
from app.integrations.registry import get_provider
from app.models.campaign import Campaign
from app.models.campaign_metric import CampaignMetric
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.services import integration_service

log = get_logger(__name__)


class CampaignNotFoundError(AdVantaError):
    status_code = 404
    code = "campaign_not_found"


# ---------------------------------------------------------------------------
# KPI derivation
# ---------------------------------------------------------------------------


def derive_kpis(
    *,
    impressions: int,
    clicks: int,
    spend_cents: int,
    conversions: int,
    conversion_value_cents: int,
) -> dict:
    def div(a: float, b: float) -> float:
        return (a / b) if b else 0.0

    return {
        "ctr": round(div(clicks, impressions), 4),
        "cpc_cents": round(div(spend_cents, clicks)),
        "cpm_cents": round(div(spend_cents * 1000, impressions)),
        "cpa_cents": round(div(spend_cents, conversions)),
        "roas": round(div(conversion_value_cents, spend_cents), 2),
        "conversion_rate": round(div(conversions, clicks), 4),
    }


@dataclass
class _Totals:
    impressions: int = 0
    clicks: int = 0
    spend_cents: int = 0
    conversions: int = 0
    conversion_value_cents: int = 0

    def add(self, m: CampaignMetric) -> None:
        self.impressions += m.impressions
        self.clicks += m.clicks
        self.spend_cents += m.spend_cents
        self.conversions += m.conversions
        self.conversion_value_cents += m.conversion_value_cents

    def as_dict(self) -> dict:
        d = {
            "impressions": self.impressions,
            "clicks": self.clicks,
            "spend_cents": self.spend_cents,
            "conversions": self.conversions,
            "conversion_value_cents": self.conversion_value_cents,
        }
        d.update(derive_kpis(**d))
        return d


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


def upsert_daily(
    db: Session,
    *,
    campaign: Campaign,
    on_date: date_type,
    impressions: int,
    clicks: int,
    spend_cents: int,
    conversions: int,
    conversion_value_cents: int = 0,
) -> CampaignMetric:
    row = (
        db.query(CampaignMetric)
        .filter(
            CampaignMetric.campaign_id == campaign.id,
            CampaignMetric.date == on_date,
        )
        .first()
    )
    if row is None:
        row = CampaignMetric(
            workspace_id=campaign.workspace_id,
            campaign_id=campaign.id,
            provider=campaign.provider,
            date=on_date,
        )
        db.add(row)
    row.impressions = impressions
    row.clicks = clicks
    row.spend_cents = spend_cents
    row.conversions = conversions
    row.conversion_value_cents = conversion_value_cents
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Read: per-campaign series + workspace summary
# ---------------------------------------------------------------------------


def _window(days: int) -> tuple[date_type, date_type]:
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=max(1, days) - 1), today


def campaign_series(
    db: Session, *, workspace_id: UUID, campaign_id: UUID, days: int = 30
) -> dict:
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id)
        .first()
    )
    if campaign is None:
        raise CampaignNotFoundError("Campaign not found in this workspace.")
    start, end = _window(days)
    rows = (
        db.query(CampaignMetric)
        .filter(
            CampaignMetric.campaign_id == campaign_id,
            CampaignMetric.date >= start,
            CampaignMetric.date <= end,
        )
        .order_by(CampaignMetric.date)
        .all()
    )
    totals = _Totals()
    points = []
    for m in rows:
        totals.add(m)
        points.append(
            {
                "date": m.date.isoformat(),
                "impressions": m.impressions,
                "clicks": m.clicks,
                "spend_cents": m.spend_cents,
                "conversions": m.conversions,
                "conversion_value_cents": m.conversion_value_cents,
            }
        )
    return {
        "campaign_id": str(campaign_id),
        "days": days,
        "points": points,
        "totals": totals.as_dict(),
        "currency": campaign.currency or "USD",
    }


def workspace_summary(db: Session, *, workspace_id: UUID, days: int = 30) -> dict:
    start, end = _window(days)
    rows = (
        db.query(CampaignMetric)
        .filter(
            CampaignMetric.workspace_id == workspace_id,
            CampaignMetric.date >= start,
            CampaignMetric.date <= end,
        )
        .all()
    )

    totals = _Totals()
    by_provider: dict[str, _Totals] = {}
    by_campaign: dict[str, _Totals] = {}
    by_day: dict[str, _Totals] = {}
    for m in rows:
        totals.add(m)
        by_provider.setdefault(m.provider or "unknown", _Totals()).add(m)
        by_campaign.setdefault(str(m.campaign_id), _Totals()).add(m)
        by_day.setdefault(m.date.isoformat(), _Totals()).add(m)

    # Top campaigns by spend, with names.
    name_by_id = {
        str(c.id): c.name
        for c in db.query(Campaign).filter(Campaign.workspace_id == workspace_id).all()
    }
    top_campaigns = sorted(
        (
            {"campaign_id": cid, "name": name_by_id.get(cid, "—"), **t.as_dict()}
            for cid, t in by_campaign.items()
        ),
        key=lambda x: x["spend_cents"],
        reverse=True,
    )[:10]

    daily = [
        {"date": d, **by_day[d].as_dict()} for d in sorted(by_day.keys())
    ]

    return {
        "days": days,
        "has_data": len(rows) > 0,
        "totals": totals.as_dict(),
        "by_provider": {p: t.as_dict() for p, t in by_provider.items()},
        "top_campaigns": top_campaigns,
        "daily": daily,
        "currency": "USD",
    }


# ---------------------------------------------------------------------------
# Sync — pull real insights per connected platform
# ---------------------------------------------------------------------------


def sync_workspace_metrics(
    db: Session, *, workspace_id: UUID, days: int = 30
) -> dict:
    start, end = _window(days)
    date_from, date_to = start.isoformat(), end.isoformat()

    accounts = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.status == ConnectionStatus.CONNECTED,
        )
        .all()
    )

    results: list[dict] = []
    total_upserted = 0
    for account in accounts:
        try:
            provider_cls = get_provider(account.provider)
        except Exception:  # noqa: BLE001 — unknown provider id, skip
            continue
        if not provider_cls.is_configured() or account.token is None:
            continue

        campaigns = (
            db.query(Campaign)
            .filter(
                Campaign.workspace_id == workspace_id,
                Campaign.provider == account.provider,
            )
            .all()
        )
        if not campaigns:
            continue

        try:
            access_token = integration_service.get_fresh_access_token(db, account=account)
        except Exception as exc:  # noqa: BLE001
            results.append({"provider": account.provider, "status": "auth_failed", "error": str(exc)})
            continue

        provider_upserts = 0
        provider_error: str | None = None
        for campaign in campaigns:
            if not campaign.external_id or not campaign.external_account_id:
                continue
            try:
                rows = provider_cls.fetch_insights(
                    access_token=access_token,
                    external_account_id=campaign.external_account_id,
                    external_id=campaign.external_id,
                    date_from=date_from,
                    date_to=date_to,
                )
            except ProviderError as exc:
                provider_error = str(exc)
                continue
            for r in rows:
                on_date = _parse_date(r.get("date"))
                if on_date is None:
                    continue
                upsert_daily(
                    db,
                    campaign=campaign,
                    on_date=on_date,
                    impressions=int(r.get("impressions", 0) or 0),
                    clicks=int(r.get("clicks", 0) or 0),
                    spend_cents=int(r.get("spend_cents", 0) or 0),
                    conversions=int(r.get("conversions", 0) or 0),
                    conversion_value_cents=int(r.get("conversion_value_cents", 0) or 0),
                )
                provider_upserts += 1
        total_upserted += provider_upserts
        results.append(
            {
                "provider": account.provider,
                "status": "ok" if provider_error is None else "partial",
                "upserted": provider_upserts,
                "error": provider_error,
            }
        )

    db.commit()
    return {"upserted": total_upserted, "providers": results, "window": {"from": date_from, "to": date_to}}


def _parse_date(value: object) -> date_type | None:
    if not value:
        return None
    try:
        return date_type.fromisoformat(str(value)[:10])
    except ValueError:
        return None
