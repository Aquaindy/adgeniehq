from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Keyword(Base, TimestampMixin):
    """One keyword opportunity per (seo_project, query). Refreshed on each Search
    Console sync — we keep the latest snapshot, not a time-series for M8."""

    __tablename__ = "keywords"
    __table_args__ = (
        UniqueConstraint(
            "seo_project_id", "query", name="uq_keywords_project_query"
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    seo_project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("seo_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    query: Mapped[str] = mapped_column(Text, nullable=False)

    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    opportunity_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    top_page: Mapped[str | None] = mapped_column(String(2048))

    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    seo_project = relationship("SeoProject", back_populates="keywords")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Keyword query={self.query!r} pos={self.position} clicks={self.clicks}>"
