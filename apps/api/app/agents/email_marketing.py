"""Email-marketing audit agent.

Reads the workspace's synced email campaigns (Omnisend today) and answers the
operator's standing questions as one structured report:

  1. Audit + score /100
  2. Segments with untapped potential
  3. A Black Friday campaign (segment + subject lines + template draft)
  4. Why open rates moved this month
  5. Best send day (see the honest caveat below)
  6. Subject-line patterns over the last 6 months
  7. Deliverability / spam risk

All metrics are computed deterministically from real `email_campaigns` rows.
The LLM only writes the qualitative narrative + the Black Friday creative, and
the agent degrades to a deterministic report if no LLM is configured.

Data honesty: Omnisend's API exposes no recipient country and no hour-of-day, so
Q5 is answered as best *day-of-week, whole-audience* — never fabricated as a
UK-specific hour — and Q7 is reputation-signal-based (complaint/bounce rates),
not inbox-placement/seed testing or SPF/DKIM/DMARC auth checks.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.agents.base import BaseAgent
from app.agents.types import (
    AgentContext,
    AgentResult,
    RecommendationRecord,
    SkillOutputRecord,
    TaskRecord,
)
from app.models.agent_task import AgentTaskStatus
from app.models.email_campaign import EmailCampaign
from app.models.recommendation import RiskLevel

# Industry-ish benchmarks (whole-audience). Tunable; used for scoring + verdicts.
BENCH_OPEN = 0.25
BENCH_CLICK = 0.03
MAX_BOUNCE = 0.02
MAX_COMPLAINT = 0.001  # 0.1% — the classic spam-complaint red line
MAX_UNSUB = 0.005
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
URGENCY_WORDS = (
    "now", "today", "tonight", "hurry", "last chance", "ends", "ending", "final",
    "limited", "only", "sale", "% off", "off", "free", "save", "deal", "exclusive",
    "expires", "don't miss", "hours left", "ends soon",
)


class EmailMarketingAgent(BaseAgent):
    type = "email_marketing"
    title = "Email marketing audit"
    description = (
        "Audits your synced email campaigns (Omnisend), scores them, and answers "
        "segment, send-time, subject-line, open-rate and deliverability questions "
        "as one report — plus a Black Friday campaign draft."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        campaigns = (
            ctx.db.query(EmailCampaign)
            .filter(EmailCampaign.workspace_id == ctx.workspace_id)
            .all()
        )
        sent_campaigns = [c for c in campaigns if (c.sent_count or 0) > 0]
        total_sent = sum(c.sent_count or 0 for c in sent_campaigns)

        if not sent_campaigns or total_sent == 0:
            return self._no_data(result, started, has_rows=bool(campaigns))

        stats = self._aggregate(sent_campaigns)
        report = {
            "generated_at": started.isoformat(),
            "scope": {
                "provider": "omnisend",
                "campaigns_analyzed": len(sent_campaigns),
                "total_sent": total_sent,
            },
            "data_caveats": [
                "Omnisend's API exposes no recipient country and no hour-of-day; "
                "Q5 is answered as best send DAY for the whole audience, not a UK hour.",
                "Q7 is based on complaint + bounce rates (reputation signals), not "
                "inbox-placement/seed testing or SPF/DKIM/DMARC checks.",
            ],
            "section_1_audit": self._section_audit(stats),
            "section_2_segments": self._section_segments(stats),
            "section_4_open_rate_trend": self._section_open_trend(sent_campaigns),
            "section_5_best_send_day": self._section_send_day(sent_campaigns),
            "section_6_subject_patterns": self._section_subject_patterns(sent_campaigns),
            "section_7_deliverability": self._section_deliverability(stats),
        }

        # LLM enrichment: executive summary, segment expansion, Black Friday draft.
        enrich = self._llm_enrich(ctx, report, stats)
        report["executive_summary"] = enrich.get("executive_summary") or self._fallback_summary(stats)
        report["section_3_black_friday"] = enrich.get("black_friday") or self._fallback_black_friday(stats, report)
        if enrich.get("segments"):
            report["section_2_segments"]["ai_suggestions"] = enrich["segments"]

        self._emit_recommendations(result, stats, report)

        result.tasks.append(
            TaskRecord(
                skill_name="email.audit",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={"campaigns_analyzed": len(sent_campaigns)},
                output_payload={"score": report["section_1_audit"]["score"]},
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="email.audit",
                output_type="email_marketing_report",
                payload=report,
                task_index=1,
            )
        )
        result.output_payload = report
        return result

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(self, campaigns: list[EmailCampaign]) -> dict:
        sent = sum(c.sent_count or 0 for c in campaigns)
        opened = sum(c.opened_count or 0 for c in campaigns)
        clicked = sum(c.clicked_count or 0 for c in campaigns)
        bounced = sum(c.bounced_count or 0 for c in campaigns)
        complained = sum(c.complained_count or 0 for c in campaigns)
        unsubscribed = sum(c.unsubscribed_count or 0 for c in campaigns)

        def rate(part: int) -> float:
            return part / sent if sent else 0.0

        return {
            "campaigns": len(campaigns),
            "total_sent": sent,
            "open_rate": rate(opened),
            "click_rate": rate(clicked),
            "bounce_rate": rate(bounced),
            "complaint_rate": rate(complained),
            "unsubscribe_rate": rate(unsubscribed),
            "opened": opened,
            "clicked": clicked,
        }

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _section_audit(self, s: dict) -> dict:
        open_score = min(100.0, (s["open_rate"] / BENCH_OPEN) * 100) if BENCH_OPEN else 0
        click_score = min(100.0, (s["click_rate"] / BENCH_CLICK) * 100) if BENCH_CLICK else 0
        bounce_score = max(0.0, 100 - (s["bounce_rate"] / MAX_BOUNCE) * 100)
        complaint_score = max(0.0, 100 - (s["complaint_rate"] / MAX_COMPLAINT) * 100)
        unsub_score = max(0.0, 100 - (s["unsubscribe_rate"] / MAX_UNSUB) * 100)
        composite = (
            0.30 * open_score
            + 0.20 * click_score
            + 0.20 * bounce_score
            + 0.20 * complaint_score
            + 0.10 * unsub_score
        )
        score = round(composite)
        grade = (
            "Excellent" if score >= 85 else
            "Healthy" if score >= 70 else
            "Needs work" if score >= 50 else
            "At risk"
        )
        return {
            "score": score,
            "grade": grade,
            "subscores": {
                "engagement_open": round(open_score),
                "engagement_click": round(click_score),
                "deliverability_bounce": round(bounce_score),
                "deliverability_complaint": round(complaint_score),
                "list_health_unsub": round(unsub_score),
            },
            "weighted_rates": {
                "open_rate": round(s["open_rate"], 4),
                "click_rate": round(s["click_rate"], 4),
                "bounce_rate": round(s["bounce_rate"], 4),
                "complaint_rate": round(s["complaint_rate"], 4),
                "unsubscribe_rate": round(s["unsubscribe_rate"], 4),
            },
            "benchmarks": {
                "good_open_rate": BENCH_OPEN,
                "good_click_rate": BENCH_CLICK,
                "max_bounce_rate": MAX_BOUNCE,
                "max_complaint_rate": MAX_COMPLAINT,
            },
        }

    def _section_segments(self, s: dict) -> dict:
        non_opener_share = max(0.0, 1 - s["open_rate"])
        non_opener_count = round(s["total_sent"] * non_opener_share)
        deterministic = [
            {
                "segment": "Lapsed / never-opened",
                "why": (
                    f"~{round(non_opener_share*100)}% of your last sends didn't open "
                    f"(~{non_opener_count} recipients across analyzed campaigns). A "
                    "re-engagement/win-back flow recovers revenue before they go cold."
                ),
            },
            {
                "segment": "Engaged clickers (VIP)",
                "why": (
                    "Contacts who clicked recently convert best — a higher-frequency, "
                    "offer-led stream to them lifts revenue with low unsubscribe risk."
                ),
            },
            {
                "segment": "Opened-not-clicked",
                "why": (
                    "They read but didn't act — interest without a strong enough offer/CTA. "
                    "A different angle or incentive often converts this tier."
                ),
            },
        ]
        return {
            "note": (
                "Heuristic from campaign-level engagement. True per-contact RFM/behavioral "
                "scoring needs contact-level event data (not in Omnisend's campaign-stats API)."
            ),
            "recommended_segments": deterministic,
        }

    def _section_open_trend(self, campaigns: list[EmailCampaign]) -> dict:
        by_month: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # month -> [opened, sent]
        for c in campaigns:
            if not c.sent_at:
                continue
            key = c.sent_at.strftime("%Y-%m")
            by_month[key][0] += c.opened_count or 0
            by_month[key][1] += c.sent_count or 0
        series = [
            {"month": m, "open_rate": round(o / s, 4) if s else None, "sent": s}
            for m, (o, s) in sorted(by_month.items())
        ]
        out: dict = {"monthly": series}
        valid = [p for p in series if p["open_rate"] is not None]
        if len(valid) >= 2:
            cur, prev = valid[-1], valid[-2]
            delta = cur["open_rate"] - prev["open_rate"]
            rel = (delta / prev["open_rate"]) if prev["open_rate"] else 0.0
            out["latest_month"] = cur["month"]
            out["delta_vs_prev"] = round(delta, 4)
            out["relative_change"] = round(rel, 4)
            out["direction"] = "down" if delta < 0 else "up" if delta > 0 else "flat"
        else:
            out["note"] = "Not enough months of sent campaigns yet to trend open rate."
        return out

    def _section_send_day(self, campaigns: list[EmailCampaign]) -> dict:
        by_day: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        for c in campaigns:
            if not c.sent_at:
                continue
            d = c.sent_at.weekday()
            by_day[d][0] += c.opened_count or 0
            by_day[d][1] += c.sent_count or 0
        rows = [
            {"day": WEEKDAYS[d], "open_rate": round(o / s, 4) if s else None, "sent": s}
            for d, (o, s) in sorted(by_day.items())
        ]
        ranked = sorted(
            [r for r in rows if r["open_rate"] is not None],
            key=lambda r: r["open_rate"],
            reverse=True,
        )
        return {
            "caveat": (
                "Omnisend's API has no recipient country and no hour-of-day. This is the "
                "best send DAY for your whole list — not a UK-specific hour. For true "
                "country + hour optimization, capture per-open events (webhooks) or use a "
                "send-time-optimization tool."
            ),
            "by_day_of_week": rows,
            "best_day": ranked[0]["day"] if ranked else None,
        }

    def _section_subject_patterns(self, campaigns: list[EmailCampaign]) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(days=183)
        recent = [
            c for c in campaigns
            if c.subject and c.sent_at and c.sent_at >= cutoff and (c.sent_count or 0) > 0
        ]
        if not recent:
            return {"note": "No campaigns with subjects in the last 6 months to analyze."}

        features = {
            "has_emoji": _has_emoji,
            "personalized": _is_personalized,
            "has_number": lambda s: any(ch.isdigit() for ch in s),
            "is_question": lambda s: s.strip().endswith("?"),
            "urgency": _has_urgency,
            "short_<=30_chars": lambda s: len(s) <= 30,
        }
        out_feats = []
        for label, fn in features.items():
            with_f = [c for c in recent if fn(c.subject)]
            without_f = [c for c in recent if not fn(c.subject)]
            wr = _weighted_open(with_f)
            wo = _weighted_open(without_f)
            if wr is None or wo is None:
                continue
            out_feats.append({
                "pattern": label,
                "campaigns_with": len(with_f),
                "open_rate_with": round(wr, 4),
                "open_rate_without": round(wo, 4),
                "lift": round(wr - wo, 4),
            })
        out_feats.sort(key=lambda x: x["lift"], reverse=True)

        top = sorted(
            recent, key=lambda c: (c.open_rate or 0), reverse=True
        )[:5]
        return {
            "window_days": 183,
            "patterns": out_feats,
            "top_subjects": [
                {"subject": c.subject, "open_rate": round(c.open_rate or 0, 4), "sent": c.sent_count}
                for c in top
            ],
        }

    def _section_deliverability(self, s: dict) -> dict:
        flags = []
        if s["complaint_rate"] > MAX_COMPLAINT:
            flags.append(
                f"Spam-complaint rate {s['complaint_rate']*100:.3f}% exceeds the 0.1% "
                "red line — mailbox providers will start routing you to spam."
            )
        if s["bounce_rate"] > MAX_BOUNCE:
            flags.append(
                f"Bounce rate {s['bounce_rate']*100:.2f}% is above 2% — list hygiene/"
                "validation problem that hurts sender reputation."
            )
        if s["unsubscribe_rate"] > MAX_UNSUB:
            flags.append(
                f"Unsubscribe rate {s['unsubscribe_rate']*100:.2f}% is above 0.5% — "
                "frequency or relevance is pushing people off the list."
            )
        verdict = "at_risk" if flags else "healthy"
        return {
            "verdict": verdict,
            "flags": flags,
            "complaint_rate": round(s["complaint_rate"], 5),
            "bounce_rate": round(s["bounce_rate"], 5),
            "unsubscribe_rate": round(s["unsubscribe_rate"], 5),
            "limits": {
                "complaint_red_line": MAX_COMPLAINT,
                "bounce_ceiling": MAX_BOUNCE,
                "unsub_ceiling": MAX_UNSUB,
            },
            "not_covered": (
                "This is a reputation read from complaint/bounce rates. It does NOT test "
                "actual inbox placement (seed/GlockApps-style) or verify SPF/DKIM/DMARC. "
                "Run a seed test + check your domain auth records to confirm inboxing."
            ),
        }

    # ------------------------------------------------------------------
    # LLM enrichment (qualitative sections) — deterministic fallback on failure
    # ------------------------------------------------------------------

    def _llm_enrich(self, ctx: AgentContext, report: dict, stats: dict) -> dict:
        from app.llm.client import LlmMessage, get_llm_client_for_workspace

        compact = {
            "score": report["section_1_audit"]["score"],
            "open_rate": round(stats["open_rate"], 4),
            "click_rate": round(stats["click_rate"], 4),
            "complaint_rate": round(stats["complaint_rate"], 5),
            "best_day": report["section_5_best_send_day"].get("best_day"),
            "open_trend": report["section_4_open_rate_trend"].get("direction"),
            "top_subjects": [t["subject"] for t in report["section_6_subject_patterns"].get("top_subjects", [])][:5],
            "winning_patterns": [
                p["pattern"] for p in report["section_6_subject_patterns"].get("patterns", []) if p.get("lift", 0) > 0
            ][:4],
        }
        system = (
            "You are an email-marketing strategist. You are given REAL aggregate metrics "
            "from a brand's Omnisend campaigns. Return STRICT JSON only — no prose, no code "
            "fences. Keys: executive_summary (string, 3-5 sentences grounded in the numbers), "
            "segments (array of {segment, why} — 2 to 3 untapped audience ideas), black_friday "
            "(object: {segment, angle, subject_lines (array of 5 strings, reuse the brand's "
            "winning subject patterns), template_draft (string: a short ready-to-edit email "
            "body in plain text with a clear CTA)}). Do not invent metrics you weren't given."
        )
        user = "Metrics JSON:\n" + json.dumps(compact)
        try:
            client = get_llm_client_for_workspace(ctx.db, ctx.workspace_id)
            completion = client.complete_metered(
                db=ctx.db,
                workspace_id=ctx.workspace_id,
                messages=[LlmMessage(role="system", content=system), LlmMessage(role="user", content=user)],
                max_tokens=1400,
                temperature=0.5,
                purpose="email_marketing_report",
            )
            return _parse_json(completion.text)
        except Exception as exc:  # noqa: BLE001 — any LLM/budget failure → deterministic report
            from app.core.logging import get_logger

            get_logger(__name__).info("email_marketing.llm_fallback", error=str(exc))
            return {}

    def _fallback_summary(self, s: dict) -> str:
        return (
            f"Across {s['campaigns']} sent campaigns ({s['total_sent']:,} emails), your "
            f"weighted open rate is {s['open_rate']*100:.1f}% and click rate "
            f"{s['click_rate']*100:.1f}%. Complaint rate is {s['complaint_rate']*100:.3f}% "
            f"and bounce rate {s['bounce_rate']*100:.2f}%. See each section below for the "
            "specific levers; connect an LLM key for a written strategic summary."
        )

    def _fallback_black_friday(self, s: dict, report: dict) -> dict:
        best_day = report["section_5_best_send_day"].get("best_day") or "Thursday"
        return {
            "segment": "Engaged openers (last 90 days) + lapsed win-back as a second wave",
            "angle": "Early-access for engaged subscribers, then a broader last-chance push.",
            "subject_lines": [
                "Your early Black Friday access is open 🛍️",
                "24 hours early: our biggest deal of the year",
                "Black Friday starts now — don't miss it",
                "{{ firstName }}, your VIP Black Friday code inside",
                "Last chance: Black Friday ends at midnight",
            ],
            "template_draft": (
                "Hi {{ firstName }},\n\n"
                "Black Friday is here — and because you're one of our most engaged "
                "subscribers, you get first access.\n\n"
                "[Offer headline — e.g. 30% off everything]\n"
                "Use code BF-VIP at checkout.\n\n"
                "[Shop the sale →]\n\n"
                f"Tip: send the first wave on {best_day}, your best-performing day.\n\n"
                "— The team"
            ),
            "note": "Deterministic draft (no LLM configured). Edit before sending.",
        }

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _emit_recommendations(self, result: AgentResult, s: dict, report: dict) -> None:
        deliver = report["section_7_deliverability"]
        if deliver["verdict"] == "at_risk":
            result.recommendations.append(
                RecommendationRecord(
                    title="Email deliverability is at risk",
                    summary="; ".join(deliver["flags"]),
                    recommendation_type="email.deliverability_risk",
                    risk_level=RiskLevel.HIGH,
                    expected_impact="Protect inbox placement and sender reputation.",
                    suggested_action=(
                        "Suppress non-openers/hard-bounces, slow send frequency, and run a "
                        "seed/inbox-placement test plus an SPF/DKIM/DMARC check."
                    ),
                    platform="email",
                    metadata={"complaint_rate": deliver["complaint_rate"], "bounce_rate": deliver["bounce_rate"]},
                )
            )

        trend = report["section_4_open_rate_trend"]
        if trend.get("direction") == "down" and (trend.get("relative_change") or 0) <= -0.15:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Open rate dropped {abs(trend['relative_change'])*100:.0f}% vs last month",
                    summary=(
                        f"{trend.get('latest_month')} open rate fell to "
                        f"{[m for m in trend['monthly'] if m['month']==trend.get('latest_month')][0]['open_rate']}."
                    ),
                    recommendation_type="email.open_rate_decline",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Recover lost reach and revenue from your existing list.",
                    suggested_action=(
                        "Check for a bounce/complaint spike, list fatigue (send volume up), "
                        "and weaker subject lines vs your winning patterns."
                    ),
                    platform="email",
                    metadata={"relative_change": trend.get("relative_change")},
                )
            )

        best_day = report["section_5_best_send_day"].get("best_day")
        if best_day:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Your best send day is {best_day}",
                    summary="Highest weighted open rate across your sent campaigns by day of week.",
                    recommendation_type="email.best_send_day",
                    risk_level=RiskLevel.LOW,
                    expected_impact="Higher opens by scheduling broadcasts on your strongest day.",
                    suggested_action=f"Default new broadcasts to {best_day}; A/B test a second day.",
                    platform="email",
                    metadata={"best_day": best_day},
                )
            )

        if s["open_rate"] < 0.15:
            result.recommendations.append(
                RecommendationRecord(
                    title="Open rate is below a healthy floor",
                    summary=f"Weighted open rate {s['open_rate']*100:.1f}% is under ~15%.",
                    recommendation_type="email.low_open_rate",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="More of every send actually gets read.",
                    suggested_action=(
                        "Clean inactive contacts, warm sender reputation, and lean into the "
                        "subject-line patterns that lifted opens (see section 6)."
                    ),
                    platform="email",
                    metadata={"open_rate": round(s["open_rate"], 4)},
                )
            )

    # ------------------------------------------------------------------
    # Empty state
    # ------------------------------------------------------------------

    def _no_data(self, result: AgentResult, started: datetime, *, has_rows: bool) -> AgentResult:
        msg = (
            "Email campaigns are synced but none have send/open data yet."
            if has_rows
            else "No Omnisend email campaigns are synced for this workspace yet."
        )
        result.tasks.append(
            TaskRecord(
                skill_name="email.audit",
                status=AgentTaskStatus.SKIPPED,
                input_payload={},
                error_message=msg,
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.recommendations.append(
            RecommendationRecord(
                title="Connect Omnisend and sync email campaigns",
                summary=(
                    "The Email Marketing agent analyzes your real Omnisend campaigns. "
                    "Connect Omnisend, then run an email-campaign sync so there's data to audit."
                ),
                recommendation_type="email.no_data",
                risk_level=RiskLevel.MEDIUM,
                expected_impact="Unlocks the email audit, send-time, subject-line and deliverability analysis.",
                suggested_action="Settings → Autoresponders → connect Omnisend, then sync email campaigns.",
                platform="email",
            )
        )
        result.output_payload = {"skipped": True, "reason": "no_email_campaign_data"}
        return result


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _has_emoji(s: str) -> bool:
    return any(ord(ch) >= 0x1F000 or 0x2600 <= ord(ch) <= 0x27BF for ch in s)


def _is_personalized(s: str) -> bool:
    low = s.lower()
    return "{{" in s or "*|" in s or "%recipient" in low or "[firstname]" in low


def _has_urgency(s: str) -> bool:
    low = s.lower()
    return any(w in low for w in URGENCY_WORDS)


def _weighted_open(campaigns: list[EmailCampaign]) -> float | None:
    sent = sum(c.sent_count or 0 for c in campaigns)
    if sent <= 0:
        return None
    opened = sum(c.opened_count or 0 for c in campaigns)
    return opened / sent


def _parse_json(text: str) -> dict:
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
    if not body.startswith("{") and "{" in body:
        body = body[body.index("{"):]
    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}
