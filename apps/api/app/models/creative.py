from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Enum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class CreativeType(StrEnum):
    SEARCH_AD = "search_ad"          # Headlines + descriptions (Google Ads)
    RESPONSIVE_DISPLAY = "responsive_display"
    SINGLE_IMAGE = "single_image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    UGC = "ugc"
    OTHER = "other"


class CreativeSource(StrEnum):
    PLATFORM_SYNCED = "platform_synced"  # Pulled from a connected ad platform
    AI_GENERATED = "ai_generated"        # Built by Creative Strategy Agent
    USER_UPLOADED = "user_uploaded"


class Creative(Base, TimestampMixin):
    __tablename__ = "creatives"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[CreativeType] = mapped_column(
        Enum(
            CreativeType,
            name="creative_type",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=CreativeType.OTHER,
    )
    source: Mapped[CreativeSource] = mapped_column(
        Enum(
            CreativeSource,
            name="creative_source",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=CreativeSource.AI_GENERATED,
    )
    title: Mapped[str | None] = mapped_column(String(512))
    primary_text: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    cta: Mapped[str | None] = mapped_column(String(120))
    image_url: Mapped[str | None] = mapped_column(String(2048))
    video_url: Mapped[str | None] = mapped_column(String(2048))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)

    ads: Mapped[list["Ad"]] = relationship(  # noqa: F821
        "Ad", back_populates="creative"
    )
