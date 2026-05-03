from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SeoProjectPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    site_url: str | None
    search_console_site_url: str | None
    last_crawled_at: datetime | None
    last_search_console_synced_at: datetime | None
    crawl_summary: dict | None
    created_at: datetime


class KeywordPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query: str
    impressions: int
    clicks: int
    ctr: float
    position: float
    opportunity_score: int
    top_page: str | None
    period_start: date | None
    period_end: date | None
    last_synced_at: datetime


class SearchConsoleSyncResponse(BaseModel):
    site_url: str
    period_start: date
    period_end: date
    keywords_upserted: int
