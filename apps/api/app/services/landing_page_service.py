from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.landing_page import LandingPage, LandingPageSource
from app.models.onboarding_profile import OnboardingProfile


class LandingPageNotFoundError(AdVantaError):
    status_code = 404
    code = "landing_page_not_found"


class DuplicateLandingPageError(AdVantaError):
    status_code = 409
    code = "duplicate_landing_page"


def list_landing_pages(db: Session, *, workspace_id: UUID) -> list[LandingPage]:
    return (
        db.query(LandingPage)
        .filter(LandingPage.workspace_id == workspace_id)
        .order_by(
            LandingPage.is_primary.desc(),
            LandingPage.created_at.asc(),
        )
        .all()
    )


def get_landing_page(
    db: Session, *, workspace_id: UUID, landing_page_id: UUID
) -> LandingPage:
    lp = (
        db.query(LandingPage)
        .filter(
            LandingPage.id == landing_page_id,
            LandingPage.workspace_id == workspace_id,
        )
        .first()
    )
    if lp is None:
        raise LandingPageNotFoundError("Landing page not found in this workspace.")
    return lp


def create_landing_page(
    db: Session,
    *,
    workspace_id: UUID,
    url: str,
    label: str | None = None,
    source: LandingPageSource = LandingPageSource.MANUAL,
    is_primary: bool = False,
) -> LandingPage:
    # Plan-limit gate (M11). Imported lazily to avoid a circular import with
    # billing_service, which depends on a different layer.
    from app.services import billing_service

    clean_url = url.strip()

    # Duplicate-URL check first so re-submitting the same URL surfaces 409
    # rather than a misleading 402 plan-limit error.
    existing = (
        db.query(LandingPage)
        .filter(
            LandingPage.workspace_id == workspace_id,
            LandingPage.url == clean_url,
        )
        .first()
    )
    if existing is not None:
        raise DuplicateLandingPageError(
            "This URL is already tracked for the workspace."
        )

    current = (
        db.query(LandingPage)
        .filter(LandingPage.workspace_id == workspace_id)
        .count()
    )
    billing_service.assert_within_landing_page_limit(
        db, workspace_id=workspace_id, current_count=current
    )

    lp = LandingPage(
        workspace_id=workspace_id,
        url=clean_url,
        label=(label or "").strip() or None,
        source=source,
        is_primary=is_primary,
    )
    db.add(lp)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise DuplicateLandingPageError(
            "This URL is already tracked for the workspace."
        )
    db.commit()
    db.refresh(lp)
    return lp


def delete_landing_page(
    db: Session, *, workspace_id: UUID, landing_page_id: UUID
) -> None:
    lp = get_landing_page(
        db, workspace_id=workspace_id, landing_page_id=landing_page_id
    )
    db.delete(lp)
    db.commit()


def import_from_onboarding(db: Session, *, workspace_id: UUID) -> int:
    """Import any landing_page_urls from the workspace's onboarding profile that
    aren't already tracked. Returns the number of new rows created."""
    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )
    if profile is None or not profile.landing_page_urls:
        return 0

    existing = {
        lp.url
        for lp in db.query(LandingPage)
        .filter(LandingPage.workspace_id == workspace_id)
        .all()
    }

    created = 0
    for url in profile.landing_page_urls:
        clean = (url or "").strip()
        if not clean or clean in existing:
            continue
        db.add(
            LandingPage(
                workspace_id=workspace_id,
                url=clean,
                source=LandingPageSource.ONBOARDING,
                is_primary=created == 0 and not existing,
            )
        )
        existing.add(clean)
        created += 1

    if created:
        db.commit()
    return created
