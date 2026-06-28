"""Traffic analytics + optimization (Phase 6).

Aggregates the workspace's REAL traffic results — operator-logged/imported
`traffic_metrics` rows plus Phase 4 solo-ad orders — into per-source and
per-campaign rollups with derived economics (CPC/CPL/ROAS/EPC/conversion), a
per-source traffic quality score, profitability, and a paid/organic/paid-email
split. Feeds the dashboard and the Traffic Optimizer agent. No estimates or
placeholder numbers: every figure traces to a row the operator entered or
imported.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.exceptions import AdGenieError
from app.models.audit_log import AuditActorType
from app.models.solo_ad import SoloAdOrder
from app.models.traffic_campaign import TrafficCampaign
from app.models.traffic_metric import TrafficMetric
from app.services import audit_service
from app.traffic import catalog as cat

# Soft targets used only to scale the 0-100 quality score (not hard rules).
TARGET_LEAD_RATE = 0.25   # leads / clicks
TARGET_CONVERSION = 0.08  # sales / leads
TARGET_ROAS = 3.0


# ---------------------------------------------------------------------------
# Metric logging
# ---------------------------------------------------------------------------


def log_metric(
    db: Session, *, workspace_id: UUID, actor_user_id: UUID, data: dict,
    request: Request | None = None,
) -> TrafficMetric:
    if not data.get("source_slug"):
        raise AdGenieError("source_slug is required.", code="missing_source_slug")
    metric = TrafficMetric(
        workspace_id=workspace_id,
        created_by=actor_user_id,
        traffic_campaign_id=data.get("traffic_campaign_id"),
        source_slug=data["source_slug"],
        medium=data.get("medium"),
        date=data.get("date"),
        visitors=int(data.get("visitors") or 0),
        sessions=int(data.get("sessions") or 0),
        clicks=int(data.get("clicks") or 0),
        unique_clicks=int(data.get("unique_clicks") or 0),
        leads=int(data.get("leads") or 0),
        sales=int(data.get("sales") or 0),
        revenue_cents=int(data.get("revenue_cents") or 0),
        cost_cents=int(data.get("cost_cents") or 0),
        currency=data.get("currency"),
        bounce_rate=data.get("bounce_rate"),
        avg_session_duration_sec=data.get("avg_session_duration_sec"),
        email_opens=int(data.get("email_opens") or 0),
        email_clicks=int(data.get("email_clicks") or 0),
        unsubscribes=int(data.get("unsubscribes") or 0),
        spam_complaints=int(data.get("spam_complaints") or 0),
        refunds=int(data.get("refunds") or 0),
    )
    db.add(metric)
    db.flush()
    audit_service.log_event(
        db, workspace_id=workspace_id, actor_type=AuditActorType.USER, actor_id=actor_user_id,
        action="traffic_metric.logged", resource_type="traffic_metric", resource_id=metric.id,
        metadata={"source_slug": metric.source_slug}, request=request,
    )
    db.commit()
    db.refresh(metric)
    return metric


def list_metrics(db: Session, *, workspace_id: UUID, limit: int = 500) -> list[TrafficMetric]:
    return (
        db.query(TrafficMetric)
        .filter(TrafficMetric.workspace_id == workspace_id)
        .order_by(desc(TrafficMetric.date.nullslast()), desc(TrafficMetric.created_at))
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _blank() -> dict:
    return {
        "clicks": 0, "leads": 0, "sales": 0, "cost_cents": 0, "revenue_cents": 0,
        "refunds": 0, "visitors": 0, "sessions": 0, "spam_complaints": 0,
        "bounce_weight": 0.0, "bounce_sessions": 0,
    }


def _add(b: dict, *, clicks=0, leads=0, sales=0, cost=0, revenue=0, refunds=0,
         visitors=0, sessions=0, spam=0, bounce_rate=None) -> None:
    b["clicks"] += clicks; b["leads"] += leads; b["sales"] += sales
    b["cost_cents"] += cost; b["revenue_cents"] += revenue; b["refunds"] += refunds
    b["visitors"] += visitors; b["sessions"] += sessions; b["spam_complaints"] += spam
    if bounce_rate is not None and sessions:
        b["bounce_weight"] += bounce_rate * sessions
        b["bounce_sessions"] += sessions


def _finalize(b: dict) -> dict:
    clicks, leads, sales = b["clicks"], b["leads"], b["sales"]
    cost, revenue = b["cost_cents"], b["revenue_cents"]
    out = dict(b)
    out["profit_cents"] = revenue - cost
    out["cpc_cents"] = round(cost / clicks) if clicks else None
    out["cpl_cents"] = round(cost / leads) if leads else None
    out["cps_cents"] = round(cost / sales) if sales else None
    out["epc_cents"] = round(revenue / clicks) if clicks else None
    out["roas"] = round(revenue / cost, 4) if cost else None
    out["lead_rate"] = round(leads / clicks, 4) if clicks else None
    out["conversion_rate"] = round(sales / leads, 4) if leads else None
    out["refund_rate"] = round(b["refunds"] / sales, 4) if sales else None
    out["bounce_rate"] = round(b["bounce_weight"] / b["bounce_sessions"], 4) if b["bounce_sessions"] else None
    score, verdict = _quality(out)
    out["quality_score"] = score
    out["quality_verdict"] = verdict
    # Drop internal accumulators.
    for k in ("bounce_weight", "bounce_sessions"):
        out.pop(k, None)
    return out


def _quality(m: dict) -> tuple[int | None, str | None]:
    """Source-level traffic quality 0-100 from real factors. None if there isn't
    enough signal (no clicks)."""
    if not m["clicks"]:
        return None, None
    parts: list[tuple[float, float]] = []  # (subscore 0-100, weight)

    if m["lead_rate"] is not None:
        parts.append((min(100.0, m["lead_rate"] / TARGET_LEAD_RATE * 100), 0.30))
    if m["conversion_rate"] is not None:
        parts.append((min(100.0, m["conversion_rate"] / TARGET_CONVERSION * 100), 0.25))
    if m["roas"] is not None:
        parts.append((min(100.0, m["roas"] / TARGET_ROAS * 100), 0.35))
    # Health: start at 100, subtract for refunds / spam / bounce.
    health = 100.0
    if m["refund_rate"]:
        health -= min(60.0, m["refund_rate"] * 300)
    if m["sessions"] and m["spam_complaints"]:
        health -= min(40.0, (m["spam_complaints"] / m["sessions"]) * 100 * 40)
    if m["bounce_rate"] is not None and m["bounce_rate"] > 0.7:
        health -= (m["bounce_rate"] - 0.7) * 100
    parts.append((max(0.0, health), 0.10))

    total_w = sum(w for _, w in parts)
    score = round(sum(s * w for s, w in parts) / total_w) if total_w else None
    if score is None:
        return None, None
    verdict = (
        "Excellent" if score >= 85 else "Strong" if score >= 70 else
        "Promising" if score >= 55 else "Weak" if score >= 40 else
        "Risky" if score >= 25 else "Poor"
    )
    return score, verdict


def compute_overview(db: Session, *, workspace_id: UUID) -> dict:
    by_source: dict[str, dict] = {}
    by_campaign: dict[str, dict] = {}
    by_type: dict[str, dict] = {}
    campaign_meta: dict[str, dict] = {}

    def src_bucket(slug: str) -> dict:
        return by_source.setdefault(slug, _blank())

    def camp_bucket(cid: str) -> dict:
        return by_campaign.setdefault(cid, _blank())

    def type_bucket(t: str) -> dict:
        return by_type.setdefault(t, _blank())

    # Campaign names for labeling.
    for c in db.query(TrafficCampaign).filter(TrafficCampaign.workspace_id == workspace_id).all():
        campaign_meta[str(c.id)] = {"name": c.name, "source_slug": c.source_slug}

    def source_type(slug: str) -> str:
        s = cat.SOURCE_BY_SLUG.get(slug)
        return s.source_type if s else "other"

    # 1) traffic_metrics rows.
    for m in db.query(TrafficMetric).filter(TrafficMetric.workspace_id == workspace_id).all():
        kw = dict(
            clicks=m.clicks, leads=m.leads, sales=m.sales, cost=m.cost_cents,
            revenue=m.revenue_cents, refunds=m.refunds, visitors=m.visitors,
            sessions=m.sessions, spam=m.spam_complaints, bounce_rate=m.bounce_rate,
        )
        _add(src_bucket(m.source_slug), **kw)
        _add(type_bucket(source_type(m.source_slug)), **kw)
        if m.traffic_campaign_id:
            _add(camp_bucket(str(m.traffic_campaign_id)), **kw)

    # 2) Solo-ad orders fold in as paid-email "solo_ads" results.
    for o in db.query(SoloAdOrder).filter(SoloAdOrder.workspace_id == workspace_id).all():
        kw = dict(
            clicks=o.clicks_delivered or 0, leads=o.optins or 0, sales=o.sales or 0,
            cost=o.cost_cents or 0, revenue=o.revenue_cents or 0, refunds=o.refunds or 0,
        )
        _add(src_bucket("solo_ads"), **kw)
        _add(type_bucket("paid_email"), **kw)
        if o.traffic_campaign_id:
            _add(camp_bucket(str(o.traffic_campaign_id)), **kw)
            campaign_meta.setdefault(str(o.traffic_campaign_id), {"name": "Solo ad campaign", "source_slug": "solo_ads"})

    sources = []
    for slug, b in by_source.items():
        fin = _finalize(b)
        s = cat.SOURCE_BY_SLUG.get(slug)
        fin.update({"source_slug": slug, "source_name": s.name if s else slug, "source_type": source_type(slug)})
        sources.append(fin)
    sources.sort(key=lambda x: (x["profit_cents"], x["revenue_cents"]), reverse=True)

    campaigns = []
    for cid, b in by_campaign.items():
        fin = _finalize(b)
        meta = campaign_meta.get(cid, {})
        fin.update({"campaign_id": cid, "name": meta.get("name", "Campaign"), "source_slug": meta.get("source_slug")})
        campaigns.append(fin)
    campaigns.sort(key=lambda x: (x["profit_cents"], x["revenue_cents"]), reverse=True)

    totals = _finalize_totals(by_source.values())
    type_totals = {t: _finalize(b) for t, b in by_type.items()}

    return {
        "has_data": bool(sources),
        "currency": "USD",
        "totals": totals,
        "sources": sources,
        "campaigns": campaigns,
        "by_type": type_totals,
    }


def _finalize_totals(buckets) -> dict:
    agg = _blank()
    for b in buckets:
        for k in ("clicks", "leads", "sales", "cost_cents", "revenue_cents", "refunds", "visitors", "sessions", "spam_complaints"):
            agg[k] += b[k]
    fin = _finalize(agg)
    fin.pop("quality_score", None)
    fin.pop("quality_verdict", None)
    return fin


# ---------------------------------------------------------------------------
# Next best actions (deterministic) — consumed by the Traffic Optimizer agent
# ---------------------------------------------------------------------------


def next_best_actions(overview: dict) -> list[dict]:
    actions: list[dict] = []
    sources = overview.get("sources", [])

    for s in sources:
        name = s["source_name"]
        roas = s.get("roas")
        profit = s.get("profit_cents") or 0
        cost = s.get("cost_cents") or 0

        if cost > 0 and roas is not None and roas >= 2 and profit > 0:
            actions.append(_action("scale", "high", name,
                f"Scale {name}", f"{name} is profitable at {roas:.1f}x ROAS (+{_usd(profit)}). Increase budget gradually and keep watching CPL."))
        elif cost > 0 and profit < 0:
            actions.append(_action("fix_or_pause", "high", name,
                f"Fix or pause {name}", f"{name} is unprofitable ({_usd(profit)} at {('%.1fx' % roas) if roas is not None else 'n/a'} ROAS). Pause it or fix the offer/landing before spending more."))
        elif cost > 0 and (s.get("sales") or 0) == 0 and (s.get("leads") or 0) >= 10:
            actions.append(_action("improve_offer", "medium", name,
                f"Improve conversion for {name}", f"{name} is generating leads but no sales — tighten the offer, follow-up or pricing."))

        if s.get("refund_rate") and s["refund_rate"] > 0.2:
            actions.append(_action("quality", "medium", name,
                f"Investigate refunds on {name}", f"Refund rate is {s['refund_rate']*100:.0f}% — check buyer quality and expectations."))

    if sources:
        best = sources[0]
        if (best.get("profit_cents") or 0) > 0:
            actions.append(_action("double_down", "low", best["source_name"],
                f"Double down on {best['source_name']}", f"It's your most profitable source (+{_usd(best['profit_cents'])}). Put more of your next budget here."))

    # De-duplicate by (type, source), keep highest priority first.
    order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: order.get(a["priority"], 3))
    seen = set()
    deduped = []
    for a in actions:
        key = (a["type"], a["source"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    return deduped


def _action(type_: str, priority: str, source: str, title: str, detail: str) -> dict:
    return {"type": type_, "priority": priority, "source": source, "title": title, "detail": detail}


def _usd(cents: int) -> str:
    return f"${cents/100:,.0f}"


# ---------------------------------------------------------------------------
# Run the optimizer agent
# ---------------------------------------------------------------------------


def run_optimizer(db: Session, *, workspace_id: UUID, actor_user_id: UUID) -> dict:
    from app.agents.runtime import run_agent  # deferred to avoid import cycle

    run = run_agent(
        db, workspace_id=workspace_id, agent_type="traffic_optimizer",
        triggered_by_user_id=actor_user_id, input_payload={},
    )
    if run.status.value != "succeeded":
        raise AdGenieError(run.error_message or "Traffic optimizer failed.", code="traffic_optimize_failed")
    return run.output_payload or {}
