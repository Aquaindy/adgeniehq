"""Per-workspace Autopilot configuration.

Autopilot Mode is OFF by default. It must be explicitly enabled per workspace,
and every guardrail (spend cap, risk ceiling, allowed action types) must be
filled in. The service that consumes this config refuses to act if any
required guardrail is missing.
"""

from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.recommendation import RiskLevel


class AutopilotMode(StrEnum):
    OFF = "off"            # Manual approvals only.
    ADVISOR = "advisor"    # Recs surface only; no auto-approval.
    APPROVAL = "approval"  # Same as advisor, kept for legacy clarity.
    AUTOPILOT = "autopilot"  # Auto-approve under the configured guardrails.


class AutopilotConfig(Base, TimestampMixin):
    __tablename__ = "autopilot_configs"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_autopilot_configs_workspace"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mode: Mapped[AutopilotMode] = mapped_column(
        Enum(
            AutopilotMode,
            name="autopilot_mode",
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=AutopilotMode.OFF,
        # Defense in depth: the DB itself defaults a config row to OFF, so any
        # insert path that forgets to set mode can never land a live autopilot.
        server_default="off",
    )
    # Spend guardrails.
    max_daily_spend_increase_cents: Mapped[int | None] = mapped_column(BigInteger)
    max_daily_spend_total_cents: Mapped[int | None] = mapped_column(BigInteger)
    max_pct_increase_per_change: Mapped[int | None] = mapped_column(Integer)  # e.g. 20 = 20%
    min_conversion_threshold: Mapped[int | None] = mapped_column(Integer)

    # Action-type allowlist. Empty list means "no auto-execution allowed."
    # Stored as JSONB to keep this flexible without another join table.
    allowed_action_types: Mapped[list[str] | None] = mapped_column(JSONB)

    # Highest recommendation risk level that may be auto-approved. Reuses the
    # `recommendation_risk_level` PG enum from M5 (which stores Python member
    # names — LOW/MEDIUM/HIGH — so we don't pass values_callable here).
    risk_ceiling: Mapped[RiskLevel] = mapped_column(
        Enum(
            RiskLevel,
            name="recommendation_risk_level",
            create_type=False,
        ),
        nullable=False,
        default=RiskLevel.LOW,
    )

    # Stop-loss kill switch — flipped by the Budget Guardian when something
    # is detected in the workspace (overspend, repeated execution failures).
    stop_loss_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    stop_loss_reason: Mapped[str | None] = mapped_column(Text)
    last_disabled_reason: Mapped[str | None] = mapped_column(String(512))
