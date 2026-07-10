"""Social platform reference data.

Code-level reference data — deliberately NOT a per-tenant table, mirroring
`app/traffic/catalog.py` and the integration/agent registries. Adding a
platform is a one-entry code change with no migration, because a draft
references its platform by `slug` (a plain string column).

The numbers below are authoring *guidance*, not a contract with the
platforms:

  * `hard_char_limit` is the length the platform itself refuses to exceed.
    We enforce it as a trim ceiling so a draft is never longer than what the
    operator can actually paste into the composer.
  * `body_length` is the engagement sweet spot we ask the model to hit. It's
    a soft hint, well inside the hard limit.
  * `hashtag_range` is convention, not enforcement — platforms permit far
    more than is useful (Instagram allows 30; stuffing 30 reads as spam).

Platforms revise these limits without notice. They live here, in one place,
so a change is a single edit rather than a hunt through prompt strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.models.content_draft import ContentDraftType


class SocialFormat(StrEnum):
    """What kind of artifact the platform takes.

    `POST` → written copy the operator pastes into a composer.
    `VIDEO_SCRIPT` → a shot-by-shot script for a vertical short-form video.
    """

    POST = "post"
    VIDEO_SCRIPT = "video_script"


@dataclass(frozen=True)
class SocialPlatform:
    slug: str
    label: str
    format: SocialFormat
    # Which ContentDraftType a draft for this platform is stored as. Posts and
    # scripts are shaped differently enough to warrant separate types, while
    # the platform itself stays a string column.
    draft_type: ContentDraftType
    # Soft target for the body, in characters: (low, high).
    body_length: tuple[int, int]
    # Platform-enforced ceiling. None = effectively unbounded for our purposes.
    hard_char_limit: int | None
    # Conventional hashtag count: (low, high).
    hashtag_range: tuple[int, int]
    # Video-only fields.
    aspect_ratio: str | None = None
    duration_seconds: tuple[int, int] | None = None
    # Platform-specific voice/format guidance fed to the model.
    guidance: str = ""

    @property
    def is_video(self) -> bool:
        return self.format is SocialFormat.VIDEO_SCRIPT


_POSTS: tuple[SocialPlatform, ...] = (
    SocialPlatform(
        slug="linkedin",
        label="LinkedIn",
        format=SocialFormat.POST,
        draft_type=ContentDraftType.SOCIAL_POST,
        body_length=(900, 1500),
        hard_char_limit=3000,
        hashtag_range=(3, 5),
        guidance=(
            "Professional but human. Open with a concrete, specific claim or a "
            "short story — the first 2 lines are all that show before the "
            "'…see more' fold, so earn the click there. Short paragraphs, "
            "generous line breaks. No engagement-bait ('Agree? 👇'). Close with "
            "one clear question or CTA."
        ),
    ),
    SocialPlatform(
        slug="facebook",
        label="Facebook",
        format=SocialFormat.POST,
        draft_type=ContentDraftType.SOCIAL_POST,
        body_length=(300, 600),
        hard_char_limit=63206,
        hashtag_range=(0, 3),
        guidance=(
            "Conversational and plainspoken, like talking to a peer. Lead with "
            "the payoff, not the setup. Hashtags carry little weight here — use "
            "few or none. Ask something answerable to invite comments."
        ),
    ),
    SocialPlatform(
        slug="x",
        label="X (Twitter)",
        format=SocialFormat.POST,
        draft_type=ContentDraftType.SOCIAL_POST,
        body_length=(180, 270),
        hard_char_limit=280,
        hashtag_range=(0, 2),
        guidance=(
            "One sharp idea, compressed. No preamble — the first 5 words do the "
            "work. Hard 280-character ceiling including hashtags and any link, "
            "so every word must earn its place. At most 2 hashtags; zero is "
            "often better."
        ),
    ),
    SocialPlatform(
        slug="instagram",
        label="Instagram",
        format=SocialFormat.POST,
        draft_type=ContentDraftType.SOCIAL_POST,
        body_length=(125, 400),
        hard_char_limit=2200,
        hashtag_range=(8, 15),
        guidance=(
            "Caption for a visual post. The first line is the hook shown before "
            "'more' — front-load it. Warm, direct, first-person. Line breaks "
            "between thoughts. Mix broad and niche hashtags; avoid banned or "
            "generic one-word tags like #love."
        ),
    ),
    SocialPlatform(
        slug="pinterest",
        label="Pinterest",
        format=SocialFormat.POST,
        draft_type=ContentDraftType.SOCIAL_POST,
        body_length=(100, 300),
        hard_char_limit=500,
        hashtag_range=(2, 5),
        guidance=(
            "Pin description. Pinterest is a search engine — write for intent, "
            "using the literal words someone would type. Describe what the "
            "reader gets and why they'd save it for later. Keyword-rich but "
            "readable, never a keyword list."
        ),
    ),
    SocialPlatform(
        slug="threads",
        label="Threads",
        format=SocialFormat.POST,
        draft_type=ContentDraftType.SOCIAL_POST,
        body_length=(150, 400),
        hard_char_limit=500,
        hashtag_range=(0, 1),
        guidance=(
            "Casual, opinionated, conversational — closer to a text message "
            "than a press release. Threads surfaces one topic tag at most, so "
            "use zero or one."
        ),
    ),
)

_VIDEOS: tuple[SocialPlatform, ...] = (
    SocialPlatform(
        slug="tiktok",
        label="TikTok",
        format=SocialFormat.VIDEO_SCRIPT,
        draft_type=ContentDraftType.SHORT_VIDEO_SCRIPT,
        body_length=(400, 900),
        hard_char_limit=None,
        hashtag_range=(3, 6),
        aspect_ratio="9:16",
        duration_seconds=(21, 60),
        guidance=(
            "Native, unpolished, creator-to-camera. The first 2 seconds decide "
            "everything — open on the payoff or a pattern break, never on a "
            "logo or 'hey guys'. Spoken cadence, not written prose. Plan "
            "on-screen text for every beat, because most viewers watch muted."
        ),
    ),
    SocialPlatform(
        slug="instagram_reels",
        label="Instagram Reels",
        format=SocialFormat.VIDEO_SCRIPT,
        draft_type=ContentDraftType.SHORT_VIDEO_SCRIPT,
        body_length=(400, 900),
        hard_char_limit=None,
        hashtag_range=(5, 10),
        aspect_ratio="9:16",
        duration_seconds=(15, 60),
        guidance=(
            "Polished but personal. Hook in the first 2 seconds. Build for the "
            "loop — the last beat should make replaying feel natural. Keep the "
            "lower third clear of on-screen text so the caption UI doesn't "
            "cover it."
        ),
    ),
    SocialPlatform(
        slug="youtube_shorts",
        label="YouTube Shorts",
        format=SocialFormat.VIDEO_SCRIPT,
        draft_type=ContentDraftType.SHORT_VIDEO_SCRIPT,
        body_length=(400, 900),
        hard_char_limit=None,
        hashtag_range=(3, 5),
        aspect_ratio="9:16",
        duration_seconds=(20, 60),
        guidance=(
            "Search-and-suggestion driven, so state the topic in words people "
            "actually search. Deliver a complete idea — Shorts viewers reward "
            "resolution over cliffhangers. Title reads like a promise the "
            "script keeps."
        ),
    ),
)


PLATFORMS: dict[str, SocialPlatform] = {p.slug: p for p in (*_POSTS, *_VIDEOS)}


def list_platforms(format: SocialFormat | None = None) -> list[SocialPlatform]:
    """All platforms, optionally narrowed to one format. Order is curated
    (posts before video, most-used first), so the UI can render it as-is."""

    values = list(PLATFORMS.values())
    if format is None:
        return values
    return [p for p in values if p.format is format]


def get_platform(slug: str) -> SocialPlatform | None:
    return PLATFORMS.get((slug or "").strip().lower())
