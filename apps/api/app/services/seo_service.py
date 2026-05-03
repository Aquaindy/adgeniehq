"""SEO project management + Search Console keyword sync."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.integrations.google_search_console import (
    GoogleSearchConsoleProvider,
    GSCKeywordRow,
    GSCSearchAnalyticsResult,
)
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.keyword import Keyword
from app.models.onboarding_profile import OnboardingProfile
from app.models.seo_project import SeoProject
from app.services import integration_service

log = get_logger(__name__)


class GSCNotConnectedError(AdVantaError):
    status_code = 409
    code = "search_console_not_connected"


class NoSiteUrlError(AdVantaError):
    status_code = 422
    code = "no_site_url"


# ---------------------------------------------------------------------------
# SEO project
# ---------------------------------------------------------------------------


def get_or_create_project(db: Session, *, workspace_id: UUID) -> SeoProject:
    project = (
        db.query(SeoProject)
        .filter(SeoProject.workspace_id == workspace_id)
        .first()
    )
    if project is None:
        onboarding = (
            db.query(OnboardingProfile)
            .filter(OnboardingProfile.workspace_id == workspace_id)
            .first()
        )
        site_url = onboarding.website_url if onboarding else None
        project = SeoProject(workspace_id=workspace_id, site_url=site_url)
        db.add(project)
        db.commit()
        db.refresh(project)
    elif project.site_url is None:
        # Sync the URL from onboarding if it's been added since project creation.
        onboarding = (
            db.query(OnboardingProfile)
            .filter(OnboardingProfile.workspace_id == workspace_id)
            .first()
        )
        if onboarding and onboarding.website_url:
            project.site_url = onboarding.website_url
            db.commit()
            db.refresh(project)
    return project


def list_keywords(
    db: Session, *, workspace_id: UUID, limit: int = 100
) -> list[Keyword]:
    project = get_or_create_project(db, workspace_id=workspace_id)
    return (
        db.query(Keyword)
        .filter(Keyword.seo_project_id == project.id)
        .order_by(Keyword.opportunity_score.desc(), Keyword.impressions.desc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Opportunity scoring
# ---------------------------------------------------------------------------


def opportunity_score(*, position: float, impressions: int, ctr: float) -> int:
    """Heuristic 0–100 score: rewards high impressions on ranks 5–20 with low CTR.

    The intuition: a keyword on rank 8 with 1000 impressions and 1% CTR is a very
    high-leverage target — small ranking gains drive a disproportionate CTR jump.
    """
    if impressions <= 0:
        return 0
    # Position boost: peaks around 5–20, drops off above and below
    if position <= 3:
        position_factor = 0.15  # already ranking near the top
    elif position <= 20:
        position_factor = 1.0 - abs(position - 10) / 12.0  # peaks at 10
    elif position <= 40:
        position_factor = 0.4
    else:
        position_factor = 0.2

    # Impressions log-scaled (1k impressions = 1.0, 10k = 1.3-ish)
    import math

    impressions_factor = min(1.5, math.log10(max(1, impressions)) / 3.0)

    # Underperforming CTR boosts opportunity (high impressions + low CTR = big lever)
    ctr_factor = 1.0 if ctr < 0.02 else (0.6 if ctr < 0.05 else 0.3)

    raw = position_factor * impressions_factor * ctr_factor * 100
    return int(max(0, min(100, raw)))


# ---------------------------------------------------------------------------
# Search Console sync
# ---------------------------------------------------------------------------


def _site_origin(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme or 'https'}://{parsed.netloc}"


def _pick_search_console_site(
    available_sites: list[dict], *, project_site_url: str | None
) -> str | None:
    if not available_sites:
        return None

    if project_site_url:
        origin = _site_origin(project_site_url)
        domain = urlparse(project_site_url).netloc

        # Prefer exact siteUrl match
        for entry in available_sites:
            if entry.get("siteUrl") == project_site_url:
                return entry.get("siteUrl")

        # Match by origin (e.g. "https://example.com/")
        if origin:
            for entry in available_sites:
                site = entry.get("siteUrl") or ""
                if site.rstrip("/") == origin.rstrip("/"):
                    return site

        # Match by sc-domain prefix
        if domain:
            for entry in available_sites:
                site = entry.get("siteUrl") or ""
                if site == f"sc-domain:{domain}":
                    return site

    # Fall back: first verified site
    for entry in available_sites:
        if entry.get("permissionLevel") and entry.get("siteUrl"):
            return entry["siteUrl"]
    return None


def sync_search_console(
    db: Session, *, workspace_id: UUID
) -> tuple[SeoProject, GSCSearchAnalyticsResult]:
    project = get_or_create_project(db, workspace_id=workspace_id)

    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == "google_search_console",
            ConnectedAccount.status == ConnectionStatus.CONNECTED,
        )
        .first()
    )
    if account is None or account.token is None:
        raise GSCNotConnectedError(
            "Connect Google Search Console first to sync keyword data."
        )

    access_token = integration_service.get_fresh_access_token(db, account=account)
    sites = GoogleSearchConsoleProvider.list_sites(access_token=access_token)

    target_site = _pick_search_console_site(sites, project_site_url=project.site_url)
    if not target_site:
        raise NoSiteUrlError(
            "Search Console does not list any verified sites for this account."
        )

    project.search_console_site_url = target_site

    result = GoogleSearchConsoleProvider.fetch_search_analytics(
        access_token=access_token, site_url=target_site
    )

    _upsert_keywords(db, project=project, result=result)

    project.last_search_console_synced_at = datetime.now(timezone.utc)
    account.last_sync_at = project.last_search_console_synced_at
    account.last_error = None
    db.commit()
    db.refresh(project)
    return project, result


def _upsert_keywords(
    db: Session, *, project: SeoProject, result: GSCSearchAnalyticsResult
) -> int:
    now = datetime.now(timezone.utc)
    count = 0
    for row in result.rows:
        existing = (
            db.query(Keyword)
            .filter(Keyword.seo_project_id == project.id, Keyword.query == row.query)
            .first()
        )
        score = opportunity_score(
            position=row.position, impressions=row.impressions, ctr=row.ctr
        )
        if existing is None:
            existing = Keyword(
                seo_project_id=project.id,
                query=row.query,
                last_synced_at=now,
            )
            db.add(existing)

        existing.clicks = row.clicks
        existing.impressions = row.impressions
        existing.ctr = row.ctr
        existing.position = row.position
        existing.opportunity_score = score
        existing.top_page = row.top_page
        existing.period_start = result.period_start
        existing.period_end = result.period_end
        existing.last_synced_at = now
        count += 1
    db.flush()
    return count
