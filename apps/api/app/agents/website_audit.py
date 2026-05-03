from datetime import datetime, timezone

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
from app.models.recommendation import RiskLevel
from app.models.onboarding_profile import OnboardingProfile
from app.skills.website import (
    check_headings,
    check_meta_description,
    check_robots,
    check_title,
    check_viewport,
    fetch_html,
)
from app.skills.website.fetch import WebsiteFetchError

SKILL_REGISTRY = (
    ("website.title", check_title),
    ("website.meta_description", check_meta_description),
    ("website.headings", check_headings),
    ("website.viewport", check_viewport),
    ("website.robots", check_robots),
)


def _severity_to_risk(severity: str) -> RiskLevel:
    if severity == "high":
        return RiskLevel.HIGH
    if severity == "medium":
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _resolve_url(ctx: AgentContext) -> str | None:
    explicit = ctx.input_payload.get("url") if ctx.input_payload else None
    if explicit:
        return explicit
    profile = (
        ctx.db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == ctx.workspace_id)
        .first()
    )
    return profile.website_url if profile and profile.website_url else None


class WebsiteAuditAgent(BaseAgent):
    type = "website_audit"
    title = "Website conversion audit"
    description = (
        "Crawls your primary website URL and surfaces above-the-fold and basic on-page issues "
        "that hurt SEO, GEO, and conversion."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()

        url = _resolve_url(ctx)
        if not url:
            result.output_payload = {"skipped": True, "reason": "no_website_url"}
            result.tasks.append(
                TaskRecord(
                    skill_name="website.fetch",
                    status=AgentTaskStatus.SKIPPED,
                    input_payload={},
                    error_message="No website URL configured in onboarding.",
                )
            )
            return result

        # Task 0: fetch
        fetch_started = datetime.now(timezone.utc)
        try:
            page = fetch_html(url)
        except WebsiteFetchError as exc:
            result.output_payload = {"skipped": True, "reason": "fetch_failed", "url": url}
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
                    title="Website is unreachable",
                    summary=f"AdVanta could not fetch {url}.",
                    recommendation_type="website_unreachable",
                    risk_level=RiskLevel.HIGH,
                    expected_impact=(
                        "All website-based agents (audit, copy improvements, conversion scoring) "
                        "are blocked until the URL responds with HTML."
                    ),
                    suggested_action=(
                        "Confirm the website URL in onboarding, or check that the site is online "
                        "and not blocking automated user agents."
                    ),
                    metadata={"url": url, "error": str(exc)},
                )
            )
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
        findings: dict[str, dict] = {}

        for idx, (skill_name, fn) in enumerate(SKILL_REGISTRY, start=1):
            started = datetime.now(timezone.utc)
            try:
                finding = fn(soup)
                status = AgentTaskStatus.SUCCEEDED
                error = None
            except Exception as exc:  # pragma: no cover — defensive
                finding = {"severity": "error", "message": str(exc)}
                status = AgentTaskStatus.FAILED
                error = str(exc)

            findings[skill_name] = finding
            completed = datetime.now(timezone.utc)

            result.tasks.append(
                TaskRecord(
                    skill_name=skill_name,
                    status=status,
                    input_payload={"url": page.final_url},
                    output_payload=finding,
                    error_message=error,
                    started_at=started,
                    completed_at=completed,
                )
            )

            result.skill_outputs.append(
                SkillOutputRecord(
                    skill_name=skill_name,
                    output_type="website_finding",
                    payload=finding,
                    task_index=idx,
                )
            )

            severity = finding.get("severity")
            if severity in ("high", "medium", "low"):
                result.recommendations.append(
                    RecommendationRecord(
                        title=f"{skill_name.split('.')[-1].replace('_', ' ').title()}: {finding['message'][:80]}",
                        summary=finding["message"],
                        recommendation_type=f"{skill_name}.{severity}",
                        risk_level=_severity_to_risk(severity),
                        expected_impact=_impact_for(skill_name),
                        suggested_action=_action_for(skill_name, finding),
                        platform="website",
                        metadata={"url": page.final_url, "finding": finding},
                    )
                )

        # High-level summary payload
        severity_counts = {"high": 0, "medium": 0, "low": 0, "ok": 0}
        for finding in findings.values():
            sev = finding.get("severity", "ok")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        result.output_payload = {
            "url": page.final_url,
            "status_code": page.status_code,
            "html_length": len(page.html),
            "severity_counts": severity_counts,
            "findings": findings,
        }
        return result


def _impact_for(skill_name: str) -> str:
    return {
        "website.title": (
            "A weak <title> reduces click-through from organic search and AI-search results."
        ),
        "website.meta_description": (
            "A clear meta description improves search-result CTR and AI-search citations."
        ),
        "website.headings": (
            "A clear above-the-fold H1 sets the value prop and increases scroll + conversion."
        ),
        "website.viewport": (
            "Without a mobile viewport, mobile users see a desktop-scaled page and bounce."
        ),
        "website.robots": (
            "Restrictive robots directives keep your page out of search and AI-search results."
        ),
    }.get(skill_name, "Improving this finding strengthens overall site quality signals.")


def _action_for(skill_name: str, finding: dict) -> str:
    severity = finding.get("severity", "ok")
    if severity == "ok":
        return "No change needed."
    return {
        "website.title": "Edit the <title> tag to a 30–60 character benefit-led headline.",
        "website.meta_description": (
            "Add or rewrite the meta description as a 120–160 character pitch + offer + CTA."
        ),
        "website.headings": "Use exactly one <h1> with a benefit-driven hero headline.",
        "website.viewport": (
            "Add `<meta name='viewport' content='width=device-width, initial-scale=1'>`."
        ),
        "website.robots": (
            "Remove `noindex` (or `nofollow`) directives once the page is ready to be indexed."
        ),
    }.get(skill_name, "Address the issue described in the finding.")
