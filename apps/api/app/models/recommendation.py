from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    ARCHIVED = "archived"


class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_run_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, name="recommendation_risk_level"),
        nullable=False,
        default=RiskLevel.LOW,
    )
    expected_impact: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus, name="recommendation_status"),
        nullable=False,
        default=RecommendationStatus.OPEN,
    )

    platform: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)

    agent_run = relationship("AgentRun", back_populates="recommendations")
    approval = relationship(
        "Approval",
        back_populates="recommendation",
        cascade="all, delete-orphan",
        uselist=False,
    )
    executions = relationship(
        "RecommendationExecution",
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="RecommendationExecution.created_at",
        foreign_keys="RecommendationExecution.recommendation_id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Recommendation id={self.id} type={self.recommendation_type} risk={self.risk_level}>"
