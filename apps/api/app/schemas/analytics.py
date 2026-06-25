from pydantic import BaseModel


class KpiBlock(BaseModel):
    impressions: int
    clicks: int
    spend_cents: int
    conversions: int
    conversion_value_cents: int
    ctr: float
    cpc_cents: int
    cpm_cents: int
    cpa_cents: int
    roas: float
    conversion_rate: float


class RawDailyPoint(BaseModel):
    date: str
    impressions: int
    clicks: int
    spend_cents: int
    conversions: int
    conversion_value_cents: int


class KpiDailyPoint(KpiBlock):
    date: str


class TopCampaign(KpiBlock):
    campaign_id: str
    name: str


class CampaignSeriesResponse(BaseModel):
    campaign_id: str
    days: int
    points: list[RawDailyPoint]
    totals: KpiBlock
    currency: str


class WorkspaceAnalyticsResponse(BaseModel):
    days: int
    has_data: bool
    totals: KpiBlock
    by_provider: dict[str, KpiBlock]
    top_campaigns: list[TopCampaign]
    daily: list[KpiDailyPoint]
    currency: str


class ProviderSyncMetricResult(BaseModel):
    provider: str
    status: str
    upserted: int | None = None
    error: str | None = None


class MetricsSyncResponse(BaseModel):
    upserted: int
    providers: list[ProviderSyncMetricResult]
    window: dict[str, str]
