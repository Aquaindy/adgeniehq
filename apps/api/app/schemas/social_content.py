from pydantic import BaseModel, Field, field_validator

from app.schemas.content_drafts import ContentDraftPublic
from app.social.catalog import PLATFORMS, SocialPlatform


class SocialPlatformPublic(BaseModel):
    """Reference data for one platform. Static — safe for the client to cache."""

    slug: str
    label: str
    format: str  # "post" | "video_script"
    draft_type: str
    body_length_min: int
    body_length_max: int
    hard_char_limit: int | None
    hashtag_min: int
    hashtag_max: int
    aspect_ratio: str | None
    duration_min_seconds: int | None
    duration_max_seconds: int | None
    guidance: str

    @classmethod
    def from_platform(cls, p: SocialPlatform) -> "SocialPlatformPublic":
        low, high = p.body_length
        hlow, hhigh = p.hashtag_range
        duration = p.duration_seconds
        return cls(
            slug=p.slug,
            label=p.label,
            format=p.format.value,
            draft_type=p.draft_type.value,
            body_length_min=low,
            body_length_max=high,
            hard_char_limit=p.hard_char_limit,
            hashtag_min=hlow,
            hashtag_max=hhigh,
            aspect_ratio=p.aspect_ratio,
            duration_min_seconds=duration[0] if duration else None,
            duration_max_seconds=duration[1] if duration else None,
            guidance=p.guidance,
        )


class GenerateSocialPackRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=512)
    # Platform slugs from GET /social/platforms. Bounded so one request can't
    # fan out into an unbounded number of metered LLM calls.
    platforms: list[str] = Field(min_length=1, max_length=9)
    keywords: list[str] = Field(default_factory=list)
    audience: str | None = Field(default=None, max_length=512)
    target_url: str | None = Field(default=None, max_length=1024)
    notes: str | None = Field(default=None, max_length=2000)
    call_to_action: str | None = Field(default=None, max_length=280)

    @field_validator("platforms")
    @classmethod
    def _known_and_deduped(cls, value: list[str]) -> list[str]:
        """Reject unknown slugs here (a 422 the caller can act on) rather than
        letting the agent fail downstream as a 500.

        Dedupe as part of validation, not later: the service charges one credit
        per entry, so `["x", "x"]` must not bill twice for the one draft the
        agent would produce."""

        seen: list[str] = []
        unknown: list[str] = []
        for raw in value:
            slug = (raw or "").strip().lower()
            if not slug:
                continue
            if slug not in PLATFORMS:
                unknown.append(slug)
            elif slug not in seen:
                seen.append(slug)
        if unknown:
            raise ValueError(
                f"Unknown platform(s): {', '.join(sorted(set(unknown)))}. "
                f"Known: {', '.join(PLATFORMS)}"
            )
        if not seen:
            raise ValueError("Select at least one platform.")
        return seen


class SocialPackResponse(BaseModel):
    topic: str
    drafts: list[ContentDraftPublic]
