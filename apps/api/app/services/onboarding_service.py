from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.onboarding_profile import OnboardingProfile
from app.schemas.onboarding import OnboardingProfileUpdate


def get_or_create_profile(db: Session, *, workspace_id: UUID) -> OnboardingProfile:
    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )
    if profile is None:
        profile = OnboardingProfile(workspace_id=workspace_id, step_completed=0)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def get_profile(db: Session, *, workspace_id: UUID) -> OnboardingProfile | None:
    return (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )


def update_profile(
    db: Session, *, profile: OnboardingProfile, payload: OnboardingProfileUpdate
) -> OnboardingProfile:
    data = payload.model_dump(exclude_unset=True, exclude_none=False, mode="json")

    mark_completed = data.pop("mark_completed", None)

    for field, value in data.items():
        setattr(profile, field, value)

    if mark_completed:
        profile.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(profile)
    return profile
