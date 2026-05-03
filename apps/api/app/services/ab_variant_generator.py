"""Generate A/B-test variant payloads from a control variant.

Used by the API endpoint `POST /workspaces/{ws}/ab-tests/{test_id}/generate-variants`.
The endpoint asks the LLM (or falls back to a deterministic skeleton) to
produce N additional variant payloads, then creates the AbTestVariant rows
inline so the operator can edit them in the UI.

Variant payload shapes:
- AbTestTarget.AD            → {headline, primary_text, description, cta}
- AbTestTarget.LANDING_PAGE  → {url, hero_headline, hero_subhead, cta}

LLM is grounded in the workspace's onboarding profile (offer + brand voice)
plus the control variant payload so generated copy matches positioning.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.llm.client import LlmError, LlmMessage, get_llm_client_for_workspace
from app.models.ab_test import (
    AbTest,
    AbTestStatus,
    AbTestTarget,
    AbTestVariant,
)
from app.models.audit_log import AuditActorType
from app.models.onboarding_profile import OnboardingProfile
from app.security.permissions import Role, require_role_at_least
from app.services import audit_service


class VariantGenerationError(AdVantaError):
    status_code = 422
    code = "ab_variant_generation_failed"


class TestNotEditableError(AdVantaError):
    status_code = 409
    code = "ab_test_not_editable"


def generate_variants_for_test(
    db: Session,
    *,
    workspace_id: UUID,
    test_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    count: int = 2,
) -> list[AbTestVariant]:
    """Look up the test, find its control variant, generate `count` new
    variants, persist them. Audit-logs the action."""

    require_role_at_least(actor_role, Role.MARKETER)
    if count < 1 or count > 4:
        raise VariantGenerationError("Generate between 1 and 4 new variants.")

    test = (
        db.query(AbTest)
        .filter(AbTest.id == test_id, AbTest.workspace_id == workspace_id)
        .first()
    )
    if test is None:
        raise VariantGenerationError("Test not found.")

    if test.status not in (AbTestStatus.DRAFT, AbTestStatus.READY):
        raise TestNotEditableError(
            f"Cannot add variants to a test in '{test.status.value}' state."
        )

    control = next((v for v in test.variants if v.is_control), None)
    if control is None and test.variants:
        control = test.variants[0]
    if control is None:
        raise VariantGenerationError(
            "The test has no variants yet — add a control before generating."
        )

    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )

    payloads, source = _generate_payloads(
        db,
        workspace_id=workspace_id,
        target=test.target,
        control_payload=control.payload or {},
        profile=profile,
        count=count,
    )

    next_position = max((v.position for v in test.variants), default=0) + 1
    created: list[AbTestVariant] = []
    for idx, payload in enumerate(payloads):
        variant = AbTestVariant(
            workspace_id=workspace_id,
            ab_test_id=test.id,
            name=payload.get("__name") or f"Variant {next_position + idx}",
            position=next_position + idx,
            is_control=False,
            # Provisional share — the loop below rebalances every variant
            # (existing + new) once the full set is known so the test passes
            # the sum-to-1.0 invariant on launch.
            traffic_share=Decimal("0"),
            payload={k: v for k, v in payload.items() if not k.startswith("__")},
            metrics={},
        )
        db.add(variant)
        db.flush()
        created.append(variant)

    # Rebalance: split traffic evenly across the FULL variant set so the test
    # remains launchable. Use Decimal arithmetic + 4-decimal rounding (matches
    # `_validate_variants` precision), then absorb any rounding remainder on
    # the final variant so the sum is exactly 1.0.
    db.refresh(test)
    all_variants = sorted(test.variants, key=lambda v: v.position)
    n = len(all_variants)
    base_share = (Decimal("1") / Decimal(n)).quantize(Decimal("0.0001"))
    running = Decimal("0")
    for i, v in enumerate(all_variants):
        if i == n - 1:
            # Last variant absorbs the rounding remainder.
            v.traffic_share = (Decimal("1") - running).quantize(Decimal("0.0001"))
        else:
            v.traffic_share = base_share
            running += base_share

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.AGENT,
        actor_id=actor_user_id,
        action="ab_test.variants_generated",
        resource_type="ab_test",
        resource_id=test.id,
        metadata={
            "count": len(created),
            "source": source,
            "target": test.target.value,
        },
    )
    db.commit()
    for v in created:
        db.refresh(v)
    return created


# -------------------------------------------------------------------------
# Payload generation (LLM-enriched + deterministic fallback)
# -------------------------------------------------------------------------


def _generate_payloads(
    db: Session,
    *,
    workspace_id: UUID,
    target: AbTestTarget,
    control_payload: dict[str, Any],
    profile: OnboardingProfile | None,
    count: int,
) -> tuple[list[dict[str, Any]], str]:
    llm = get_llm_client_for_workspace(db, workspace_id)
    if llm.is_configured():
        try:
            return _payloads_via_llm(
                db,
                workspace_id=workspace_id,
                target=target,
                control_payload=control_payload,
                profile=profile,
                count=count,
            ), "llm"
        except (LlmError, AdVantaError):
            pass
    return _payloads_deterministic(target, control_payload, count), "deterministic"


def _payloads_via_llm(
    db: Session,
    *,
    workspace_id: UUID,
    target: AbTestTarget,
    control_payload: dict[str, Any],
    profile: OnboardingProfile | None,
    count: int,
) -> list[dict[str, Any]]:
    llm = get_llm_client_for_workspace(db, workspace_id)

    if target == AbTestTarget.AD:
        schema_hint = (
            "{headline (<=40 chars), primary_text (<=125 chars), description, cta}"
        )
    else:
        schema_hint = "{url, hero_headline (<=80 chars), hero_subhead, cta}"

    offer_block = (
        f"Offer: {profile.offer_description}\nBrand voice: {profile.brand_voice}"
        if profile
        else "Offer / brand voice unspecified."
    )

    system = LlmMessage(
        role="system",
        content=(
            f"You are a senior performance copywriter. The control variant is "
            f"provided. Produce {count} NEW alternative variants as a JSON array "
            f"of {schema_hint}. Each must be meaningfully different from the "
            f"control on at least one of: angle, length, or proof type. Avoid "
            f"emojis unless the brand voice explicitly says so. Return JSON only."
        ),
    )
    user = LlmMessage(
        role="user",
        content=(
            f"{offer_block}\n\n"
            f"Control payload (do NOT repeat verbatim):\n{json.dumps(control_payload)}\n\n"
            "Return JSON array."
        ),
    )
    completion = llm.complete_metered(
        db=db,
        workspace_id=workspace_id,
        messages=[system, user],
        max_tokens=900,
        temperature=0.7,
        purpose="ab_variants.generate",
    )
    text = completion.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LlmError(f"Variant LLM returned non-JSON: {exc}") from exc
    if not isinstance(data, list):
        raise LlmError("Variant LLM did not return a JSON array.")
    return data[:count]


def _payloads_deterministic(
    target: AbTestTarget, control_payload: dict[str, Any], count: int
) -> list[dict[str, Any]]:
    """Conservative skeleton — preserves the control's structure but flags
    edits so operators don't ship as-is."""
    out: list[dict[str, Any]] = []
    for i in range(count):
        if target == AbTestTarget.AD:
            payload = {
                "headline": (control_payload.get("headline") or "Variant headline")[:40],
                "primary_text": (
                    f"[Edit me] Test angle {i + 1}: "
                    + (control_payload.get("primary_text") or "")
                )[:125],
                "description": control_payload.get("description")
                or "[Edit me] differentiate this variant",
                "cta": control_payload.get("cta") or "Learn more",
                "__name": f"Test angle {i + 1}",
            }
        else:
            payload = {
                "url": control_payload.get("url") or "",
                "hero_headline": (
                    f"[Edit me] {control_payload.get('hero_headline', 'Hero')}"
                )[:80],
                "hero_subhead": control_payload.get("hero_subhead")
                or "[Edit me] Differentiate this hero subhead",
                "cta": control_payload.get("cta") or "Get started",
                "__name": f"Test angle {i + 1}",
            }
        out.append(payload)
    return out
