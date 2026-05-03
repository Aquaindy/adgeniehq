from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.ab_test import AbTestStatus, AbTestTarget, BanditStrategy


class AbTestVariantPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ab_test_id: UUID
    name: str
    position: int
    is_control: bool
    traffic_share: float
    payload: dict
    external_id: str | None
    launched_at: datetime | None
    metrics: dict | None
    created_at: datetime
    updated_at: datetime

    @field_validator("traffic_share", mode="before")
    @classmethod
    def _decimal_to_float(cls, v):
        if isinstance(v, Decimal):
            return float(v)
        return v


class VariantStatsPublic(BaseModel):
    variant_id: UUID
    name: str
    visits: int
    conversions: int
    conversion_rate: float
    ci_low: float
    ci_high: float


class TestStatisticsPublic(BaseModel):
    variants: list[VariantStatsPublic]
    p_value: float | None
    z_score: float | None
    relative_lift: float | None
    significant: bool
    confidence: float
    min_sample_per_variant: int
    underpowered: bool
    suggested_winner_variant_id: UUID | None


class AbTestPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    hypothesis: str | None
    target: AbTestTarget
    objective: str
    status: AbTestStatus
    provider: str | None
    external_account_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    winner_variant_id: UUID | None
    bandit_strategy: BanditStrategy = BanditStrategy.STATIC
    metadata: dict | None = Field(default=None, alias="metadata_json")
    created_at: datetime
    updated_at: datetime
    variants: list[AbTestVariantPublic] = []
    statistics: TestStatisticsPublic | None = None


class CreateVariantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    is_control: bool = False
    traffic_share: float = Field(ge=0.0, le=1.0, default=0.5)
    payload: dict = Field(default_factory=dict)


class CreateAbTestRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    hypothesis: str | None = Field(default=None, max_length=4000)
    target: AbTestTarget
    objective: str = Field(min_length=1, max_length=64)
    provider: str | None = Field(default=None, max_length=64)
    external_account_id: str | None = Field(default=None, max_length=128)
    metadata: dict | None = None
    bandit_strategy: BanditStrategy = BanditStrategy.STATIC
    variants: list[CreateVariantRequest] = Field(min_length=2)


class RecordMetricsRequest(BaseModel):
    metrics: dict = Field(min_length=1)


class DeclareWinnerRequest(BaseModel):
    variant_id: UUID
    # Override the underpowered guard. Use only when the user has out-of-band
    # confidence (manual data, qualitative wins). Default is False so a
    # nominal "Declare winner" click respects the sample-size minimum.
    force: bool = False
