"""Landing-page conversion audit agent.

Fetches the page HTML, runs M4's mobile-viewport check + the M9 conversion
skills, and (when reachable) the real PageSpeed Insights API. Composes three
scores (conversion / mobile UX / page speed), persists them on the
`LandingPage`, and emits per-finding recommendations through M5's approval
flow."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from bs4 import BeautifulSoup

from app.agents.base import BaseAgent
from app.agents.types import (
    AgentContext,
    AgentResult,
    RecommendationRecord,
    SkillOutputRecord,
    TaskRecord,
)
from app.models.agent_task import AgentTaskStatus
from app.models.landing_page import LandingPage, LandingPageSource
from app.models.recommendation import RiskLevel
from app.skills.conversion import (
    check_above_fold,
    check_copy_clarity,
    check_cta_analysis,
    check_form_friction,
    check_trust_signals,
    fetch_page_speed,
)
from app.skills.conversion.page_speed import PageSpeedError
from app.skills.website import check_viewport, fetch_html
from app.skills.website.fetch import WebsiteFetchError


SEVERITY_TO_RISK = {
    "high": RiskLevel.HIGH,
    "medium": RiskLevel.MEDIUM,
    "low": RiskLevel.LOW,
}

SKILL_SUGGESTED_ACTIONS = {
    "conversion.cta_analysis": (
        "Replace vague button copy with action-led language ('Get started', "
        "'Book a demo', 'Start free trial'). Keep one primary CTA above the fold."
    ),
    "conversion.above_fold": (
        "Rewrite the hero H1 to a 5–12 word benefit-led headline and add a 1–2 "
        "sentence supporting paragraph with a quantified outcome where possible."
    ),
    "conversion.trust_signals": (
        "Add a customer logo cloud, a quote, and a star rating above the fold."
    ),
    "conversion.form_friction": (
        "Remove or defer non-essential fields. Multi-step forms often outperform a "
        "single tall form."
    ),
    "conversion.copy_clarity": (
        "Trim sentence length to 12–20 words and replace jargon with plain alternatives."
    ),
    "conversion.viewport": (
        "Add `<meta name='viewport' content='width=device-width, initial-scale=1'>` "
        "so the page scales correctly on phones."
    ),
}

SKILL_IMPACT = {
    "conversion.cta_analysis": "Higher click-through on the primary action.",
    "conversion.above_fold": "Visitors understand the value prop in <5 seconds.",
    "conversion.trust_signals": "Reduces hesitation, especially for first-time visitors.",
    "conversion.form_friction": "Each removed field typically lifts form completion 5–15%.",
    "conversion.copy_clarity": "Higher scroll depth and engagement.",
    "conversion.viewport": "Mobile sessions stop bouncing on a desktop-scaled layout.",
}


def _resolve_landing_page(
    ctx: AgentContext,
) -> tuple[LandingPage | None, str | None, str | None]:
    """Returns (landing_page, url, error_reason)."""
    payload = ctx.input_payload or {}

    lp_id_raw = payload.get("landing_page_id")
    if lp_id_raw:
        try:
            lp_id = UUID(str(lp_id_raw))
        except ValueError:
            return None, None, "invalid_landing_page_id"
        lp = (
            ctx.db.query(LandingPage)
            .filter(LandingPage.id == lp_id, LandingPage.workspace_id == ctx.workspace_id)
            .first()
        )
        if lp is None:
            return None, None, "landing_page_not_found"
        return lp, lp.url, None

    url = payload.get("url")
    if url:
        # Find or create a landing page row for this URL.
        lp = (
            ctx.db.query(LandingPage)
            .filter(
                LandingPage.workspace_id == ctx.workspace_id,
                LandingPage.url == url,
            )
            .first()
        )
        if lp is None:
            lp = LandingPage(
                workspace_id=ctx.workspace_id,
                url=url,
                source=LandingPageSource.MANUAL,
            )
            ctx.db.add(lp)
            ctx.db.flush()
        return lp, url, None

    # Fall back to the first landing page stored in the workspace, then to onboarding URLs.
    lp = (
        ctx.db.query(LandingPage)
        .filter(LandingPage.workspace_id == ctx.workspace_id)
        .order_by(LandingPage.is_primary.desc(), LandingPage.created_at.asc())
        .first()
    )
    if lp is not None:
        return lp, lp.url, None

    return None, None, "no_landing_page"


class LandingPageAuditAgent(BaseAgent):
    type = "landing_page_audit"
    title = "Landing-page conversion audit"
    description = (
        "Fetches the page, scores hero copy / CTA / trust / form friction / "
        "page speed, and emits prioritized conversion recommendations."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        landing_page, url, reason = _resolve_landing_page(ctx)

        if not url:
            return self._no_target(result, started, reason or "no_landing_page")

        # ---------------- Task 1: fetch the page ----------------
        fetch_started = datetime.now(timezone.utc)
        try:
            page = fetch_html(url)
        except WebsiteFetchError as exc:
            result.tasks.append(
                TaskRecord(
                    skill_name="website.fetch",
                    status=AgentTaskStatus.FAILED,
                    input_payload={"url": url},
                    error_message=str(exc),
                    started_at=fetch_started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            result.recommendations.append(
                RecommendationRecord(
                    title="Landing page is unreachable",
                    summary=f"AdVanta could not fetch {url}.",
                    recommendation_type="website.unreachable",
                    risk_level=RiskLevel.HIGH,
                    expected_impact=(
                        "All landing-page audits and copy improvements are blocked until "
                        "the URL responds with HTML."
                    ),
                    suggested_action=(
                        "Confirm the URL, that the page is online, and that it accepts "
                        "automated user agents."
                    ),
                    platform="website",
                    metadata={"url": url, "error": str(exc)},
                )
            )
            result.output_payload = {"skipped": True, "reason": "fetch_failed", "url": url}
            return result

        result.tasks.append(
            TaskRecord(
                skill_name="website.fetch",
                status=AgentTaskStatus.SUCCEEDED,
                input_payload={"url": url},
                output_payload={
                    "final_url": page.final_url,
                    "status_code": page.status_code,
                    "content_type": page.content_type,
                    "html_length": len(page.html),
                },
                started_at=fetch_started,
                completed_at=datetime.now(timezone.utc),
            )
        )

        soup = BeautifulSoup(page.html, "html.parser")

        # ---------------- Conversion + mobile skills ----------------
        skill_runs: list[tuple[str, dict[str, Any]]] = []
        skill_runs.append(("conversion.above_fold", check_above_fold(soup)))
        skill_runs.append(("conversion.cta_analysis", check_cta_analysis(soup)))
        skill_runs.append(("conversion.trust_signals", check_trust_signals(soup)))
        skill_runs.append(("conversion.form_friction", check_form_friction(soup)))
        skill_runs.append(("conversion.copy_clarity", check_copy_clarity(soup)))
        viewport_finding = check_viewport(soup)
        skill_runs.append(("conversion.viewport", viewport_finding))

        for idx, (skill_name, finding) in enumerate(skill_runs, start=2):
            now = datetime.now(timezone.utc)
            result.tasks.append(
                TaskRecord(
                    skill_name=skill_name,
                    status=AgentTaskStatus.SUCCEEDED,
                    input_payload={"url": page.final_url},
                    output_payload=finding,
                    started_at=now,
                    completed_at=now,
                )
            )
            result.skill_outputs.append(
                SkillOutputRecord(
                    skill_name=skill_name,
                    output_type="conversion_finding",
                    payload=finding,
                    task_index=idx,
                )
            )

            severity = finding.get("severity")
            if severity in SEVERITY_TO_RISK:
                result.recommendations.append(
                    RecommendationRecord(
                        title=f"{skill_name.split('.')[-1].replace('_', ' ').title()}: {finding.get('message', '')[:80]}",
                        summary=finding.get("message", ""),
                        recommendation_type=f"{skill_name}.{severity}",
                        risk_level=SEVERITY_TO_RISK[severity],
                        expected_impact=SKILL_IMPACT.get(skill_name, "Better conversion rate."),
                        suggested_action=SKILL_SUGGESTED_ACTIONS.get(
                            skill_name, "Address the issue described in the finding."
                        ),
                        platform="website",
                        metadata={"url": page.final_url, "finding": finding},
                    )
                )

        # ---------------- Task: PageSpeed Insights ----------------
        ps_index = len(skill_runs) + 2
        ps_started = datetime.now(timezone.utc)
        page_speed_score: int | None = None
        page_speed_payload: dict[str, Any] = {}
        try:
            psi = fetch_page_speed(url=page.final_url, strategy="mobile")
            page_speed_payload = {
                "url": psi.url,
                "strategy": psi.strategy,
                "performance": psi.performance,
                "accessibility": psi.accessibility,
                "best_practices": psi.best_practices,
                "seo": psi.seo,
            }
            if psi.performance is not None:
                page_speed_score = int(round(psi.performance * 100))
            result.tasks.append(
                TaskRecord(
                    skill_name="conversion.page_speed",
                    status=AgentTaskStatus.SUCCEEDED,
                    input_payload={"url": page.final_url, "strategy": "mobile"},
                    output_payload=page_speed_payload,
                    started_at=ps_started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            result.skill_outputs.append(
                SkillOutputRecord(
                    skill_name="conversion.page_speed",
                    output_type="page_speed",
                    payload=page_speed_payload,
                    task_index=ps_index,
                )
            )
            if page_speed_score is not None and page_speed_score < 50:
                result.recommendations.append(
                    RecommendationRecord(
                        title=f"Mobile page speed is poor ({page_speed_score}/100)",
                        summary=(
                            f"PageSpeed Insights' mobile performance score is {page_speed_score}. "
                            "Slow pages bleed conversion and ad ROAS."
                        ),
                        recommendation_type="conversion.page_speed.high",
                        risk_level=RiskLevel.HIGH,
                        expected_impact=(
                            "Faster mobile loads typically lift conversion 5–10% per second saved."
                        ),
                        suggested_action=(
                            "Run the Lighthouse report and tackle the highest-cost opportunities "
                            "(image weight, render-blocking JS, third-party scripts)."
                        ),
                        platform="website",
                        metadata={"url": page.final_url, "psi": page_speed_payload},
                    )
                )
            elif page_speed_score is not None and page_speed_score < 75:
                result.recommendations.append(
                    RecommendationRecord(
                        title=f"Mobile page speed needs work ({page_speed_score}/100)",
                        summary=(
                            f"PageSpeed Insights' mobile performance score is {page_speed_score}. "
                            "Push above 90 for best results."
                        ),
                        recommendation_type="conversion.page_speed.medium",
                        risk_level=RiskLevel.MEDIUM,
                        expected_impact="Lower bounce rate on mobile sessions.",
                        suggested_action=(
                            "Compress hero images, defer non-critical JS, and audit third-party tags."
                        ),
                        platform="website",
                        metadata={"url": page.final_url, "psi": page_speed_payload},
                    )
                )
        except PageSpeedError as exc:
            result.tasks.append(
                TaskRecord(
                    skill_name="conversion.page_speed",
                    status=AgentTaskStatus.FAILED,
                    input_payload={"url": page.final_url, "strategy": "mobile"},
                    error_message=str(exc),
                    started_at=ps_started,
                    completed_at=datetime.now(timezone.utc),
                )
            )

        # ---------------- Composite scoring ----------------
        scores: dict[str, dict[str, Any]] = {}
        for skill_name, finding in skill_runs:
            scores[skill_name] = {
                "score": finding.get("score"),
                "severity": finding.get("severity"),
            }

        conversion_score = self._compose_conversion_score(scores)
        mobile_ux_score = 100 if viewport_finding.get("severity") == "ok" else (
            50 if viewport_finding.get("severity") in ("medium", "low") else 0
        )

        completed_at = datetime.now(timezone.utc)
        summary_payload = {
            "url": page.final_url,
            "ran_at": completed_at.isoformat(),
            "scores": {
                "conversion": conversion_score,
                "mobile_ux": mobile_ux_score,
                "page_speed": page_speed_score,
            },
            "skills": scores,
            "page_speed": page_speed_payload,
        }

        if landing_page is not None:
            landing_page.last_audited_at = completed_at
            landing_page.last_audit_summary = summary_payload

        result.output_payload = summary_payload
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compose_conversion_score(self, scores: dict[str, dict[str, Any]]) -> int:
        weights = {
            "conversion.cta_analysis": 0.30,
            "conversion.above_fold": 0.25,
            "conversion.trust_signals": 0.15,
            "conversion.form_friction": 0.15,
            "conversion.copy_clarity": 0.15,
        }
        total_weight = 0.0
        weighted = 0.0
        for skill, weight in weights.items():
            entry = scores.get(skill) or {}
            score = entry.get("score")
            if score is None:
                continue
            weighted += score * weight
            total_weight += weight
        if total_weight == 0:
            return 0
        return int(round(weighted / total_weight))

    def _no_target(
        self, result: AgentResult, started: datetime, reason: str
    ) -> AgentResult:
        message = {
            "no_landing_page": (
                "No landing pages added yet. Add one in the Website Intelligence dashboard."
            ),
            "landing_page_not_found": "Landing page not found in this workspace.",
            "invalid_landing_page_id": "Invalid landing_page_id supplied.",
        }.get(reason, "No landing page target supplied.")

        result.tasks.append(
            TaskRecord(
                skill_name="landing_page.resolve",
                status=AgentTaskStatus.SKIPPED,
                input_payload={},
                error_message=message,
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.recommendations.append(
            RecommendationRecord(
                title="Add a landing page to audit",
                summary=message,
                recommendation_type="website.no_landing_page",
                risk_level=RiskLevel.MEDIUM,
                expected_impact=(
                    "Unlocks conversion scoring, copy critiques, and PageSpeed insights."
                ),
                suggested_action="Open Website Intelligence and add a URL.",
                platform="website",
            )
        )
        result.output_payload = {"skipped": True, "reason": reason}
        return result
