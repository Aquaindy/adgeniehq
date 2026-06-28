"""Pydantic schemas for the Omnisend journey connection (Phase 5)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class JourneyStepPublic(BaseModel):
    label: str
    delay: str


class JourneyTypePublic(BaseModel):
    slug: str
    name: str
    description: str
    default_channel: str
    trigger: str
    recommended_for: list[str]
    default_steps: list[JourneyStepPublic]


class GenerateJourneyRequest(BaseModel):
    journey_type: str
    channel: str | None = None  # email | email_sms
    offer_name: str | None = None
    offer_url: str | None = None
    audience: str | None = None
    flow_name: str | None = None
    tag: str | None = None
    segment_name: str | None = None
    campaign_name: str | None = None


class CampaignMappingRequest(BaseModel):
    traffic_campaign_id: UUID
    vendor_name: str | None = None
    journey_type: str | None = None


class ContactInput(BaseModel):
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None


class SyncLeadSourceRequest(BaseModel):
    tag: str
    source: str | None = None
    contacts: list[ContactInput]
