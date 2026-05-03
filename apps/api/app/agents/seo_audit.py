"""SEO & GEO audit agent.

Discovers a sitemap for the workspace's site, fetches a bounded number of
pages, runs M4's website skills + M8's SEO/GEO skills on each, and aggregates
the results into site-wide recommendations."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

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
from app.models.onboarding_profile import OnboardingProfile
from app.models.recommendation import RiskLevel
from app.models.seo_project import SeoProject
from app.skills.seo import (
    check_canonical,
    check_faq_schema,
    check_open_graph,
    check_structured_data,
    discover_sitemap,
)
from app.skills.website import (
    check_headings,
    check_meta_description,
    check_title,
    fetch_html,
)
from app.skills.website.fetch import WebsiteFetchError

CRAWL_PAGE_BUDGET = 5  # homepage + up to 4 sitemap pages


class SEOAuditAgent(BaseAgent):
    type = "seo_audit"
    title = "SEO & GEO audit"
    description = (
        "Discovers your sitemap, crawls a handful of pages, and emits SEO + "
        "Generative Engine Optimization recommendations."
    )

    def run(self, ctx: AgentContext) -> AgentResult:
        result = AgentResult()
        started = datetime.now(timezone.utc)

        site_url = self._resolve_site_url(ctx)
        if not site_url:
            return self._no_site(result, started)

        # Ensure we have an SeoProject row to attach the crawl summary to
        project = (
            ctx.db.query(SeoProject)
            .filter(SeoProject.workspace_id == ctx.workspace_id)
            .first()
        )
        if project is None:
            project = SeoProject(workspace_id=ctx.workspace_id, site_url=site_url)
            ctx.db.add(project)
            ctx.db.flush()
        else:
            project.site_url = site_url

        # ---- Skill 1: sitemap discovery ----
        sitemap_started = datetime.now(timezone.utc)
        sitemap = discover_sitemap(site_url, max_pages=200)
        sitemap_payload = {
            "base_url": sitemap.base_url,
            "discovered_via_robots": sitemap.discovered_via_robots,
            "sitemap_url_found": sitemap.sitemap_url_found,
            "page_url_count": len(sitemap.page_urls),
            "tried": sitemap.sitemap_urls_tried,
            "error": sitemap.error,
        }
        result.tasks.append(
            TaskRecord(
                skill_name="seo.sitemap",
                status=AgentTaskStatus.SUCCEEDED if sitemap.sitemap_url_found else AgentTaskStatus.SKIPPED,
                input_payload={"site_url": site_url},
                output_payload=sitemap_payload,
                error_message=sitemap.error if not sitemap.sitemap_url_found else None,
                started_at=sitemap_started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.skill_outputs.append(
            SkillOutputRecord(
                skill_name="seo.sitemap",
                output_type="sitemap_discovery",
                payload=sitemap_payload,
                task_index=1,
            )
        )
        if not sitemap.sitemap_url_found:
            result.recommendations.append(
                RecommendationRecord(
                    title="No sitemap.xml found",
                    summary=(
                        "AdVanta couldn't locate a sitemap via /robots.txt, "
                        "/sitemap.xml, or /sitemap_index.xml. Search engines and AI "
                        "crawlers rely on sitemaps to discover content."
                    ),
                    recommendation_type="seo.sitemap_missing",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact=(
                        "Faster indexing of new pages, better crawl coverage."
                    ),
                    suggested_action=(
                        "Generate sitemap.xml (most CMS platforms have a plugin) and "
                        "reference it from /robots.txt with `Sitemap: https://.../sitemap.xml`."
                    ),
                    platform="seo",
                    metadata={"site_url": site_url},
                )
            )

        # ---- Pick which pages to crawl ----
        crawl_targets = self._select_crawl_targets(site_url, sitemap.page_urls)

        # ---- Skill 2: per-page audit ----
        per_page_findings: list[dict] = []
        title_missing_count = 0
        meta_missing_count = 0
        h1_issue_count = 0
        canonical_missing_count = 0
        sd_missing_count = 0
        og_missing_count = 0
        faq_missing_count = 0

        for idx, url in enumerate(crawl_targets, start=2):  # task indices follow sitemap=1
            page_started = datetime.now(timezone.utc)
            page_record = {"url": url, "checks": {}}
            try:
                page = fetch_html(url)
            except WebsiteFetchError as exc:
                result.tasks.append(
                    TaskRecord(
                        skill_name="seo.page_audit",
                        status=AgentTaskStatus.FAILED,
                        input_payload={"url": url},
                        error_message=str(exc),
                        started_at=page_started,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                page_record["error"] = str(exc)
                per_page_findings.append(page_record)
                continue

            soup = BeautifulSoup(page.html, "html.parser")
            checks = {
                "title": check_title(soup),
                "meta_description": check_meta_description(soup),
                "headings": check_headings(soup),
                "canonical": check_canonical(soup, page_url=page.final_url),
                "structured_data": check_structured_data(soup),
                "open_graph": check_open_graph(soup),
                "faq_schema": check_faq_schema(soup),
            }
            page_record["checks"] = checks
            page_record["status_code"] = page.status_code
            page_record["final_url"] = page.final_url
            per_page_findings.append(page_record)

            if checks["title"]["severity"] == "high":
                title_missing_count += 1
            if checks["meta_description"]["severity"] == "high":
                meta_missing_count += 1
            if checks["headings"]["severity"] in ("high", "medium"):
                h1_issue_count += 1
            if not checks["canonical"]["present"]:
                canonical_missing_count += 1
            if checks["structured_data"]["block_count"] == 0:
                sd_missing_count += 1
            if checks["open_graph"]["present_count"] == 0:
                og_missing_count += 1
            if not checks["faq_schema"]["present"]:
                faq_missing_count += 1

            result.tasks.append(
                TaskRecord(
                    skill_name="seo.page_audit",
                    status=AgentTaskStatus.SUCCEEDED,
                    input_payload={"url": url},
                    output_payload=page_record,
                    started_at=page_started,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            result.skill_outputs.append(
                SkillOutputRecord(
                    skill_name="seo.page_audit",
                    output_type="page_audit",
                    payload=page_record,
                    task_index=idx,
                )
            )

        # ---- Site-wide aggregation + recommendations ----
        crawled = sum(1 for p in per_page_findings if "error" not in p)
        if crawled > 0:
            self._emit_aggregate_recs(
                result,
                crawled=crawled,
                site_url=site_url,
                title_missing=title_missing_count,
                meta_missing=meta_missing_count,
                h1_issues=h1_issue_count,
                canonical_missing=canonical_missing_count,
                sd_missing=sd_missing_count,
                og_missing=og_missing_count,
                faq_missing=faq_missing_count,
            )

        # ---- Persist crawl summary on the SEO project ----
        completed_at = datetime.now(timezone.utc)
        project.last_crawled_at = completed_at
        project.crawl_summary = {
            "site_url": site_url,
            "sitemap_url_found": sitemap.sitemap_url_found,
            "page_url_count": len(sitemap.page_urls),
            "pages_crawled": crawled,
            "title_missing_count": title_missing_count,
            "meta_missing_count": meta_missing_count,
            "h1_issue_count": h1_issue_count,
            "canonical_missing_count": canonical_missing_count,
            "structured_data_missing_count": sd_missing_count,
            "open_graph_missing_count": og_missing_count,
            "faq_schema_missing_count": faq_missing_count,
        }

        result.output_payload = {
            "site_url": site_url,
            "started_at": started.isoformat(),
            **project.crawl_summary,
        }
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_site_url(self, ctx: AgentContext) -> str | None:
        explicit = ctx.input_payload.get("site_url") if ctx.input_payload else None
        if explicit:
            return explicit
        profile = (
            ctx.db.query(OnboardingProfile)
            .filter(OnboardingProfile.workspace_id == ctx.workspace_id)
            .first()
        )
        return profile.website_url if profile and profile.website_url else None

    def _no_site(self, result: AgentResult, started: datetime) -> AgentResult:
        result.tasks.append(
            TaskRecord(
                skill_name="seo.sitemap",
                status=AgentTaskStatus.SKIPPED,
                input_payload={},
                error_message="No website URL configured in onboarding.",
                started_at=started,
                completed_at=datetime.now(timezone.utc),
            )
        )
        result.recommendations.append(
            RecommendationRecord(
                title="Add a website URL to onboarding",
                summary=(
                    "The SEO & GEO Agent needs a website URL to crawl. Add one in "
                    "onboarding so the audit can run."
                ),
                recommendation_type="seo.no_site",
                risk_level=RiskLevel.MEDIUM,
                expected_impact="Unlocks site audits, content gap analysis, and GEO recommendations.",
                suggested_action="Open onboarding and fill in the Website URL field.",
                platform="seo",
            )
        )
        result.output_payload = {"skipped": True, "reason": "no_website_url"}
        return result

    def _select_crawl_targets(
        self, site_url: str, sitemap_pages: list[str]
    ) -> list[str]:
        targets: list[str] = []
        # Always include the homepage if the site_url is itself a URL.
        targets.append(site_url)

        for url in sitemap_pages:
            # Stay on the same origin as the site_url.
            if urlparse(url).netloc == urlparse(site_url).netloc and url not in targets:
                targets.append(url)
            if len(targets) >= CRAWL_PAGE_BUDGET:
                break

        # Even if the sitemap was empty, we keep the homepage. Cap to the budget.
        return targets[:CRAWL_PAGE_BUDGET]

    def _emit_aggregate_recs(
        self,
        result: AgentResult,
        *,
        crawled: int,
        site_url: str,
        title_missing: int,
        meta_missing: int,
        h1_issues: int,
        canonical_missing: int,
        sd_missing: int,
        og_missing: int,
        faq_missing: int,
    ) -> None:
        if title_missing > 0:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"{title_missing} of {crawled} crawled page(s) missing a <title>",
                    summary=(
                        "Pages without a title tag get truncated, generic snippets in search "
                        "and zero AI-search consideration."
                    ),
                    recommendation_type="seo.title_missing_site_wide",
                    risk_level=RiskLevel.HIGH,
                    expected_impact="Higher organic CTR and clearer AI-search citations.",
                    suggested_action=(
                        "Audit your CMS template and ensure every page renders a 30–60 char title."
                    ),
                    platform="seo",
                    metadata={"crawled": crawled, "missing": title_missing},
                )
            )

        if meta_missing > 0:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"{meta_missing} of {crawled} crawled page(s) missing meta description",
                    summary=(
                        "Without a meta description, Google generates one from page text — "
                        "often poorly."
                    ),
                    recommendation_type="seo.meta_description_missing_site_wide",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Higher organic CTR.",
                    suggested_action=(
                        "Add a 120–160 char meta description with the page's offer + value prop."
                    ),
                    platform="seo",
                    metadata={"crawled": crawled, "missing": meta_missing},
                )
            )

        if canonical_missing > 0:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Canonical links missing on {canonical_missing} of {crawled} crawled page(s)",
                    summary=(
                        "Missing canonical links risk duplicate-content treatment, especially "
                        "for sites with query parameters."
                    ),
                    recommendation_type="seo.canonical_missing_site_wide",
                    risk_level=RiskLevel.LOW,
                    expected_impact="Cleaner indexing of preferred URLs.",
                    suggested_action=(
                        "Set `<link rel='canonical' href='…'>` to the canonical URL on every page."
                    ),
                    platform="seo",
                    metadata={"crawled": crawled, "missing": canonical_missing},
                )
            )

        if sd_missing >= max(1, crawled // 2):
            result.recommendations.append(
                RecommendationRecord(
                    title=f"No structured data on {sd_missing} of {crawled} crawled page(s)",
                    summary=(
                        "AI search engines (and Google's AI Overviews) lean on schema.org "
                        "JSON-LD to extract entities, products, articles, and reviews."
                    ),
                    recommendation_type="geo.structured_data_missing",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact=(
                        "Eligibility for rich results, AI Overview citations, and entity-aware "
                        "answers."
                    ),
                    suggested_action=(
                        "Add JSON-LD for Organization, WebSite, and per-page types (Article, "
                        "Product, FAQPage, etc.)."
                    ),
                    platform="geo",
                    metadata={"crawled": crawled, "missing": sd_missing},
                )
            )

        if faq_missing >= max(1, crawled - 1):
            result.recommendations.append(
                RecommendationRecord(
                    title="No FAQ schema detected on any crawled page",
                    summary=(
                        "FAQPage schema makes a page eligible for direct-answer placements "
                        "in Google and AI search engines."
                    ),
                    recommendation_type="geo.faq_schema_missing",
                    risk_level=RiskLevel.LOW,
                    expected_impact="Direct-answer eligibility on common product questions.",
                    suggested_action=(
                        "Add a small FAQ section to your highest-traffic page with FAQPage JSON-LD."
                    ),
                    platform="geo",
                    metadata={"crawled": crawled, "missing": faq_missing},
                )
            )

        if og_missing > 0:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"Open Graph tags missing on {og_missing} of {crawled} crawled page(s)",
                    summary=(
                        "Without OG tags, social shares and AI-search snippets fall back to "
                        "title/meta only — losing the image and structured preview."
                    ),
                    recommendation_type="geo.open_graph_missing",
                    risk_level=RiskLevel.LOW,
                    expected_impact="Better social CTR and richer AI-search citations.",
                    suggested_action=(
                        "Add og:title, og:description, og:url, og:image to every page template."
                    ),
                    platform="geo",
                    metadata={"crawled": crawled, "missing": og_missing},
                )
            )

        if h1_issues > 0:
            result.recommendations.append(
                RecommendationRecord(
                    title=f"H1 issues on {h1_issues} of {crawled} crawled page(s)",
                    summary=(
                        "Pages without a clear single <h1> hurt above-the-fold clarity for "
                        "users, search engines, and AI summarizers."
                    ),
                    recommendation_type="seo.h1_issue",
                    risk_level=RiskLevel.MEDIUM,
                    expected_impact="Clearer message, better engagement and conversion.",
                    suggested_action="Use exactly one benefit-driven H1 per page.",
                    platform="seo",
                    metadata={"crawled": crawled, "h1_issues": h1_issues},
                )
            )
