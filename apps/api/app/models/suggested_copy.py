from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SuggestedCopyType(StrEnum):
    """The kind of copy artifact a Growth DNA section maps to."""

    KEYWORDS = "keywords"          # Keyword plan (paid search + SEO)
    AD_COPY = "ad_copy"            # Headlines + descriptions per platform
    LANDING_PAGE = "landing_page"  # Hero + benefits + CTA copy
    EMAIL = "email"               # Lifecycle / nurture email
    SOCIAL_POST = "social_post"    # Pillar-driven organic social post
    BLOG_OUTLINE = "blog_outline"  # SEO/content article outline
    META_TAGS = "meta_tags"        # SEO title tag + meta description
    # Vertical short-form video (Reels / Shorts / TikTok) for an organic social
    # pillar. Body is a shot-by-shot script, not copy to paste.
    SHORT_VIDEO_SCRIPT = "short_video_script"


class SuggestedCopy(Base, TimestampMixin):
    """A ready-to-use content artifact the Growth Content Studio agent generates
    from one section/segment of a workspace's Growth DNA Profile.

    Surfaced on the Creatives page under "Suggested Copies" and downloadable as
    a .txt or .docx file. Every row is stamped with the product/service name
    (the Growth DNA "profile" the run targeted) so the operator always knows
    which business the copy belongs to.
    """

    __tablename__ = "suggested_copies"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable + SET NULL so a copy survives if the source Growth DNA is
    # regenerated or removed — the artifact stays usable on its own.
    growth_dna_profile_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("growth_dna_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # The product/service this copy was generated for (the Growth DNA "profile"
    # name). Stamped on every row so the run is always traceable to a target.
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)

    copy_type: Mapped[SuggestedCopyType] = mapped_column(
        Enum(
            SuggestedCopyType,
            name="suggested_copy_type",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )
    # Which Growth DNA section/segment the suggestion came from, e.g.
    # "Paid Search", "Email: Welcome flow", "Content pillar: Education & POV".
    section: Mapped[str] = mapped_column(String(255), nullable=False)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # "llm" | "deterministic" — provenance, so the UI can be honest about it.
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic")
    model_used: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)

    # Organic-social artifacts stash their platform slug + hashtags in
    # `metadata_json`. Surfaced as read-only attributes so the public schema
    # can pick them up via `from_attributes` without a column each.
    @property
    def platform(self) -> str | None:
        return (self.metadata_json or {}).get("platform")

    @property
    def hashtags(self) -> list[str] | None:
        return (self.metadata_json or {}).get("hashtags")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SuggestedCopy {self.copy_type} section={self.section!r}>"
