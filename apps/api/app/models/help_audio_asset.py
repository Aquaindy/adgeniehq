from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Enum, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class HelpAudioStatus(StrEnum):
    """Lifecycle of a generated narration file."""

    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class HelpAudioAsset(Base, TimestampMixin):
    """Cache of ElevenLabs-narrated Help articles.

    Help content is global (platform-level), so audio is generated ONCE and
    shared across all workspaces. The cache key is (topic_id, content_hash,
    voice_id): if the article text changes, `content_hash` changes and a fresh
    file is generated, leaving the old one addressable by its own hash. One row
    per distinct (topic, content version, voice)."""

    __tablename__ = "help_audio_assets"
    __table_args__ = (
        UniqueConstraint(
            "topic_id", "content_hash", "voice_id", name="uq_help_audio_topic_hash_voice"
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    topic_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Hash of the narration text — changes when the article is edited.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Public URL of the stored MP3 (object storage). Null until READY.
    url: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[HelpAudioStatus] = mapped_column(
        Enum(HelpAudioStatus, name="help_audio_status"),
        nullable=False,
        default=HelpAudioStatus.GENERATING,
    )
    error: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HelpAudioAsset topic={self.topic_id} status={self.status}>"
