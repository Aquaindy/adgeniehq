"""Omnisend journey connection service (Phase 5).

Three jobs:
  1. generate_journey  — run the AI Omnisend Journey Builder (a blueprint).
  2. map_campaign       — derive + store the segment/tag/flow naming convention
                          on a traffic campaign (real data on existing fields).
  3. sync_lead_source   — REALLY tag contacts in Omnisend with the campaign's
                          source/segment tag, via the existing autoresponder path.

Omnisend's API can't create automations/segments, so journeys are blueprints the
operator builds once; the bridge that actually works at runtime is the tag.
"""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.agents.runtime import run_agent
from app.core.exceptions import AdGenieError
from app.models.audit_log import AuditActorType
from app.omnisend import journeys as jcat
from app.services import audit_service, traffic_service
from app.traffic import catalog as tcat

PROVIDER = "omnisend"


def list_journey_types() -> list[dict]:
    return jcat.journey_types_payload()


def generate_journey(
    db: Session, *, workspace_id: UUID, actor_user_id: UUID, context: dict,
    request: Request | None = None,
) -> dict:
    """Run the Omnisend journey agent and return the blueprint payload."""
    run = run_agent(
        db,
        workspace_id=workspace_id,
        agent_type="omnisend_journey",
        triggered_by_user_id=actor_user_id,
        input_payload=context or {},
    )
    if run.status.value != "succeeded":
        raise AdGenieError(run.error_message or "Omnisend journey agent failed.", code="omnisend_journey_failed")
    return run.output_payload or {}


def map_campaign(
    db: Session, *, workspace_id: UUID, actor_user_id: UUID, traffic_campaign_id: UUID,
    vendor_name: str | None = None, journey_type: str | None = None,
    request: Request | None = None,
) -> dict:
    """Derive the Omnisend segment/tag/flow naming for a traffic campaign and
    store the segment + flow names on it. Returns the full mapping."""
    campaign = traffic_service.get_campaign(db, workspace_id=workspace_id, campaign_id=traffic_campaign_id)
    source = tcat.SOURCE_BY_SLUG.get(campaign.source_slug)
    source_name = source.name if source else campaign.source_slug

    # Convention: "Source - [Vendor -] Campaign" (e.g. "Solo Ads - VendorX - Lead Magnet Launch").
    parts = [source_name]
    if vendor_name:
        parts.append(vendor_name)
    parts.append(campaign.name)
    segment_name = " - ".join(p for p in parts if p)
    tag = _slug(segment_name)

    jtype = jcat.JOURNEY_BY_SLUG.get(journey_type or "") if journey_type else None
    if jtype is None:
        # Sensible default journey per source type.
        default = (
            "solo_ads_nurture" if campaign.source_slug == "solo_ads"
            else "lead_magnet" if (source and source.source_type in ("paid", "paid_email"))
            else "welcome"
        )
        jtype = jcat.JOURNEY_BY_SLUG[default]
    flow_name = f"{jtype.name} — {campaign.name}"

    campaign.omnisend_segment = segment_name[:255]
    campaign.omnisend_flow = flow_name[:255]

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="omnisend.campaign_mapped",
        resource_type="traffic_campaign",
        resource_id=campaign.id,
        metadata={"segment": segment_name, "tag": tag, "flow": flow_name},
        request=request,
    )
    db.commit()

    return {
        "traffic_campaign_id": str(campaign.id),
        "source": source_name,
        "segment_name": segment_name,
        "tag": tag,
        "flow_name": flow_name,
        "lead_source_field": campaign.source_slug,
        "recommended_journey_type": jtype.slug,
        "how_to": (
            f"In Omnisend, create a segment for contacts tagged '{tag}', then build the "
            f"'{jtype.name}' automation triggered by that tag. Use 'Tag opt-ins' to push your "
            "leads in with this tag so they enter the flow."
        ),
    }


def sync_lead_source(
    db: Session, *, workspace_id: UUID, actor_user_id: UUID, tag: str,
    contacts: list[dict], source: str | None = None, request: Request | None = None,
) -> dict:
    """Tag contacts in Omnisend with the campaign's source/segment tag (REAL API
    call via the autoresponder path). Returns the sync summary."""
    from app.services import autoresponder_service

    clean_tag = _slug(tag) if tag else ""
    if not clean_tag:
        raise AdGenieError("A tag is required to sync lead source.", code="missing_tag")
    if not contacts:
        raise AdGenieError("Provide at least one contact (email) to tag.", code="no_contacts")

    sync = autoresponder_service.push_contacts(
        db,
        workspace_id=workspace_id,
        user_id=actor_user_id,
        provider_id=PROVIDER,
        audience_id=clean_tag,
        audience_name=tag,
        contacts=contacts,
        source=source or "traffic_lead_source",
        request=request,
    )
    return {
        "tag": clean_tag,
        "requested": sync.requested_count,
        "succeeded": sync.succeeded_count,
        "failed": sync.failed_count,
        "status": sync.status.value if hasattr(sync.status, "value") else str(sync.status),
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
