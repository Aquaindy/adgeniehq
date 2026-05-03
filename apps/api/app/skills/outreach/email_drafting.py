"""Outreach email drafting.

Given a prospect (a domain we'd like a backlink from), produce a personalized
subject + body. The result is saved as an OutreachEmail row in `draft` status
and never auto-sent. An Admin must approve before any actual send."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.llm import LlmClient, LlmError, LlmMessage, LlmNotConfiguredError, get_llm_client
from app.llm.client import get_llm_client_for_workspace
from app.models.backlink_prospect import BacklinkProspect
from app.models.onboarding_profile import OnboardingProfile


@dataclass
class OutreachDraft:
    subject: str
    body: str
    model_used: str | None
    source: str  # "llm" | "deterministic"


def draft_outreach_email(
    *,
    prospect: BacklinkProspect,
    profile: OnboardingProfile | None,
    angle: str | None = None,
    sender_name: str | None = None,
    llm: LlmClient | None = None,
    db: Session | None = None,
    workspace_id: UUID | None = None,
) -> OutreachDraft:
    client = llm or (
        get_llm_client_for_workspace(db, workspace_id)
        if db is not None and workspace_id is not None
        else get_llm_client()
    )
    if client.is_configured():
        try:
            return _draft_with_llm(
                client=client,
                prospect=prospect,
                profile=profile,
                angle=angle,
                sender_name=sender_name,
                db=db,
                workspace_id=workspace_id,
            )
        except (LlmError, LlmNotConfiguredError, AdVantaError):
            pass
    return _draft_deterministic(
        prospect=prospect,
        profile=profile,
        angle=angle,
        sender_name=sender_name,
    )


# ---------------------------------------------------------------------------
# LLM path
# ---------------------------------------------------------------------------


def _draft_with_llm(
    *,
    client: LlmClient,
    prospect: BacklinkProspect,
    profile: OnboardingProfile | None,
    angle: str | None,
    sender_name: str | None,
    db: Session | None = None,
    workspace_id: UUID | None = None,
) -> OutreachDraft:
    business_name = (profile.business_name if profile and profile.business_name else "the business")
    business_url = (profile.website_url if profile and profile.website_url else "(no website yet)")
    offer = (profile.offer_description if profile and profile.offer_description else "what we do")
    voice = (profile.brand_voice if profile and profile.brand_voice else "Professional, concrete, no fluff.")
    sender = sender_name or "the team"

    system = (
        "You are AdVanta AI's backlink-outreach drafter. Write a single short, "
        "respectful, personalized cold email to a publication or website owner "
        "asking for a contextual mention or a guest contribution. Do not invent "
        "metrics, customer counts, or claims you cannot support. "
        "Keep it under 150 words. Return strict JSON with keys 'subject' and 'body'."
    )
    user_lines = [
        f"Sender business: {business_name} ({business_url})",
        f"What we do: {offer}",
        f"Brand voice: {voice}",
        f"Sender name: {sender}",
        f"Target site: {prospect.domain}",
    ]
    if prospect.contact_name:
        user_lines.append(f"Recipient name: {prospect.contact_name}")
    if prospect.contact_role:
        user_lines.append(f"Recipient role: {prospect.contact_role}")
    if prospect.page_url:
        user_lines.append(f"Specific page we noticed: {prospect.page_url}")
    if angle:
        user_lines.append(f"Angle to use: {angle}")
    user_lines.append('Return: {"subject": "...", "body": "..."}')

    msgs = [
        LlmMessage(role="system", content=system),
        LlmMessage(role="user", content="\n".join(user_lines)),
    ]
    if db is not None and workspace_id is not None:
        completion = client.complete_metered(
            db=db,
            workspace_id=workspace_id,
            messages=msgs,
            max_tokens=600,
            temperature=0.5,
            purpose="outreach_email",
        )
    else:
        completion = client.complete(messages=msgs, max_tokens=600, temperature=0.5)
    parsed = _parse_payload(completion.text)
    subject = (parsed.get("subject") or f"Quick note about {prospect.domain}").strip()
    body = (parsed.get("body") or "").strip()
    if not body:
        raise LlmError("LLM produced an empty outreach body.")
    return OutreachDraft(
        subject=subject[:512],
        body=body,
        model_used=completion.model,
        source="llm",
    )


def _parse_payload(text: str) -> dict:
    import json

    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)
    if not body.startswith("{") and "{" in body:
        body = body[body.index("{") :]
    try:
        return json.loads(body)
    except ValueError as exc:
        raise LlmError(f"Could not parse LLM JSON output: {exc}") from exc


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------


def _draft_deterministic(
    *,
    prospect: BacklinkProspect,
    profile: OnboardingProfile | None,
    angle: str | None,
    sender_name: str | None,
) -> OutreachDraft:
    business_name = (
        profile.business_name if profile and profile.business_name else "our team"
    )
    business_url = profile.website_url if profile and profile.website_url else None
    offer = (
        profile.offer_description
        if profile and profile.offer_description
        else "what we do"
    )
    sender = sender_name or "the team"
    salutation = f"Hi {prospect.contact_name}" if prospect.contact_name else "Hi there"
    angle_line = (
        f"\n\nThe angle I had in mind: {angle}." if angle else ""
    )
    page_line = (
        f"\n\nI noticed this page in particular: {prospect.page_url}."
        if prospect.page_url
        else ""
    )
    sig_line = (
        f"\n\nThanks,\n{sender} ({business_name})"
        if not business_url
        else f"\n\nThanks,\n{sender} — {business_name}\n{business_url}"
    )

    subject = f"Quick note from {business_name} about {prospect.domain}"
    body = (
        f"{salutation},\n\nI lead growth at {business_name}. We help with {offer}. "
        f"I came across {prospect.domain} while researching the space and wanted to reach out — "
        f"I think there's a good fit between what your readers care about and the work we're doing."
        f"{page_line}{angle_line}\n\n"
        f"Worth a quick look? Happy to share a one-paragraph pitch if you'd like, "
        f"or feel free to point me at a guidelines page.{sig_line}"
    )
    return OutreachDraft(
        subject=subject[:512],
        body=body,
        model_used=None,
        source="deterministic",
    )
