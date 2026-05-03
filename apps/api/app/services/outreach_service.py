"""Backlink outreach: prospects → drafted emails → approved → sent.

Production rules in play:
  * Drafts never auto-send. An Admin must approve before send_email is allowed.
  * A send call with no SMTP_HOST configured records a FAILED row + audit
    entry; we never silently drop a message that the user thinks was sent.
  * Every send_email mutation is captured in the audit log with IP + UA.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from app.core.config import settings

from fastapi import Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.audit_log import AuditActorType
from app.models.backlink_prospect import BacklinkProspect, ProspectStatus
from app.models.onboarding_profile import OnboardingProfile
from app.models.outreach_email import OutreachEmail, OutreachEmailStatus
from app.models.usage_event import UsageEventType
from app.security.permissions import Role, require_role_at_least
from app.services import audit_service, billing_service
from app.services.email_service import EmailMessageDraft, send_email
from app.skills.outreach.email_drafting import draft_outreach_email


_DOMAIN_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})+$"
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProspectNotFoundError(AdVantaError):
    status_code = 404
    code = "prospect_not_found"


class OutreachEmailNotFoundError(AdVantaError):
    status_code = 404
    code = "outreach_email_not_found"


class InvalidProspectError(AdVantaError):
    status_code = 400
    code = "invalid_prospect"


class InvalidOutreachStateError(AdVantaError):
    status_code = 409
    code = "invalid_outreach_state"


class OutreachSendFailedError(AdVantaError):
    status_code = 502
    code = "outreach_send_failed"


# ---------------------------------------------------------------------------
# Prospect mutations
# ---------------------------------------------------------------------------


def _normalize_domain(value: str) -> str:
    domain = value.strip().lower()
    if domain.startswith(("http://", "https://")):
        from urllib.parse import urlparse

        domain = urlparse(domain).netloc or domain
    if domain.startswith("www."):
        domain = domain[4:]
    if not _DOMAIN_RE.match(domain):
        raise InvalidProspectError(f"`{value}` is not a valid domain.")
    return domain


def create_prospect(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    domain: str,
    page_url: str | None,
    contact_name: str | None,
    contact_email: str | None,
    contact_role: str | None,
    relevance_score: int | None,
    domain_authority: int | None,
    notes: str | None,
    source: str = "manual",
    request: Request | None = None,
) -> BacklinkProspect:
    normalized = _normalize_domain(domain)
    existing = (
        db.query(BacklinkProspect)
        .filter(
            BacklinkProspect.workspace_id == workspace_id,
            BacklinkProspect.domain == normalized,
        )
        .first()
    )
    if existing is not None:
        raise InvalidProspectError(
            f"A prospect for {normalized} already exists in this workspace."
        )

    prospect = BacklinkProspect(
        workspace_id=workspace_id,
        domain=normalized,
        page_url=page_url,
        contact_name=contact_name,
        contact_email=(contact_email or "").strip().lower() or None,
        contact_role=contact_role,
        relevance_score=relevance_score,
        domain_authority=domain_authority,
        notes=notes,
        source=source,
        status=ProspectStatus.NEW,
        created_by=actor_user_id,
    )
    db.add(prospect)
    db.flush()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="backlink_prospect.created",
        resource_type="backlink_prospect",
        resource_id=prospect.id,
        metadata={"domain": normalized, "source": source},
        request=request,
    )

    db.commit()
    db.refresh(prospect)
    return prospect


# ---------------------------------------------------------------------------
# Discovery + bulk import
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryResult:
    competitor_url: str
    pages_crawled: int
    prospects_added: int
    prospects_skipped_duplicate: int
    prospects: list[BacklinkProspect] = field(default_factory=list)


def discover_prospects_from_competitor(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    competitor_url: str,
    max_pages: int = 15,
    max_prospects: int = 50,
    request: Request | None = None,
) -> DiscoveryResult:
    """Crawl the competitor site, collect outbound external links, and add
    each new domain as a BacklinkProspect (source='discovered'). Existing
    domains in this workspace are skipped — discovery only adds, never
    overwrites a row the user has already touched."""

    require_role_at_least(actor_role, Role.MARKETER)

    from app.skills.outreach.prospect_discovery import (
        ProspectCandidate,
        discover_prospects,
    )

    try:
        candidates: list[ProspectCandidate] = discover_prospects(
            competitor_url=competitor_url,
            max_pages=max_pages,
            max_prospects=max_prospects,
        )
    except ValueError as exc:
        raise InvalidProspectError(str(exc)) from exc

    existing_domains = {
        row.domain
        for row in db.query(BacklinkProspect.domain).filter(
            BacklinkProspect.workspace_id == workspace_id
        )
    }

    added: list[BacklinkProspect] = []
    skipped = 0
    for cand in candidates:
        if cand.domain in existing_domains:
            skipped += 1
            continue
        prospect = BacklinkProspect(
            workspace_id=workspace_id,
            domain=cand.domain,
            page_url=cand.page_url,
            relevance_score=cand.relevance_score,
            notes=(
                f"Discovered from {competitor_url} — {cand.mention_count} mention(s)."
                + (
                    f" Sample anchor: '{cand.sample_anchor_text}'."
                    if cand.sample_anchor_text
                    else ""
                )
            ),
            source="discovered",
            status=ProspectStatus.NEW,
            created_by=actor_user_id,
            metadata_json={
                "competitor_url": competitor_url,
                "mention_count": cand.mention_count,
            },
        )
        db.add(prospect)
        added.append(prospect)
        existing_domains.add(cand.domain)

    db.flush()
    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="backlink_prospect.discovered",
        resource_type="backlink_prospect",
        resource_id=None,
        metadata={
            "competitor_url": competitor_url,
            "added": len(added),
            "skipped_duplicate": skipped,
        },
        request=request,
    )
    db.commit()
    for p in added:
        db.refresh(p)

    return DiscoveryResult(
        competitor_url=competitor_url,
        pages_crawled=min(max_pages, len(added) + skipped),
        prospects_added=len(added),
        prospects_skipped_duplicate=skipped,
        prospects=added,
    )


@dataclass
class BulkImportResult:
    added: list[BacklinkProspect] = field(default_factory=list)
    skipped_duplicate: list[str] = field(default_factory=list)
    skipped_invalid: list[dict] = field(default_factory=list)


def bulk_import_prospects(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    items: list[dict],
    request: Request | None = None,
) -> BulkImportResult:
    """Create up to N prospects in one shot. Each item must include
    `domain`; `contact_name`, `contact_email`, `notes` are optional. Items
    with duplicate or invalid domains are reported per-row instead of
    aborting the batch."""

    require_role_at_least(actor_role, Role.MARKETER)

    existing_domains = {
        row.domain
        for row in db.query(BacklinkProspect.domain).filter(
            BacklinkProspect.workspace_id == workspace_id
        )
    }

    added: list[BacklinkProspect] = []
    skipped_dup: list[str] = []
    skipped_invalid: list[dict] = []

    for item in items:
        domain_raw = (item.get("domain") or "").strip()
        if not domain_raw:
            skipped_invalid.append({"item": item, "error": "missing domain"})
            continue
        try:
            domain = _normalize_domain(domain_raw)
        except InvalidProspectError as exc:
            skipped_invalid.append({"item": item, "error": str(exc)})
            continue
        if domain in existing_domains:
            skipped_dup.append(domain)
            continue
        prospect = BacklinkProspect(
            workspace_id=workspace_id,
            domain=domain,
            contact_name=item.get("contact_name"),
            contact_email=(item.get("contact_email") or "").strip().lower() or None,
            notes=item.get("notes"),
            source="bulk_import",
            status=ProspectStatus.NEW,
            created_by=actor_user_id,
        )
        db.add(prospect)
        added.append(prospect)
        existing_domains.add(domain)

    db.flush()
    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="backlink_prospect.bulk_imported",
        resource_type="backlink_prospect",
        resource_id=None,
        metadata={
            "added": len(added),
            "skipped_duplicate": len(skipped_dup),
            "skipped_invalid": len(skipped_invalid),
        },
        request=request,
    )
    db.commit()
    for p in added:
        db.refresh(p)

    return BulkImportResult(
        added=added,
        skipped_duplicate=skipped_dup,
        skipped_invalid=skipped_invalid,
    )


def update_prospect(
    db: Session,
    *,
    workspace_id: UUID,
    prospect_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    updates: dict,
    request: Request | None = None,
) -> BacklinkProspect:
    require_role_at_least(actor_role, Role.MARKETER)
    prospect = get_prospect(db, workspace_id=workspace_id, prospect_id=prospect_id)

    fields = {
        "page_url",
        "contact_name",
        "contact_email",
        "contact_role",
        "relevance_score",
        "domain_authority",
        "notes",
        "status",
        "backlink_url",
    }
    for field, value in updates.items():
        if field not in fields or value is None:
            continue
        if field == "status":
            prospect.status = ProspectStatus(value)
            if prospect.status == ProspectStatus.WON and prospect.won_at is None:
                prospect.won_at = datetime.now(timezone.utc)
        else:
            setattr(prospect, field, value)

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="backlink_prospect.updated",
        resource_type="backlink_prospect",
        resource_id=prospect.id,
        metadata={"fields": list(updates.keys())},
        request=request,
    )

    db.commit()
    db.refresh(prospect)
    return prospect


def list_prospects(
    db: Session,
    *,
    workspace_id: UUID,
    status: ProspectStatus | None = None,
    limit: int = 100,
) -> list[BacklinkProspect]:
    query = db.query(BacklinkProspect).filter(
        BacklinkProspect.workspace_id == workspace_id
    )
    if status is not None:
        query = query.filter(BacklinkProspect.status == status)
    return (
        query.order_by(desc(BacklinkProspect.created_at)).limit(limit).all()
    )


def get_prospect(
    db: Session, *, workspace_id: UUID, prospect_id: UUID
) -> BacklinkProspect:
    row = (
        db.query(BacklinkProspect)
        .filter(
            BacklinkProspect.id == prospect_id,
            BacklinkProspect.workspace_id == workspace_id,
        )
        .first()
    )
    if row is None:
        raise ProspectNotFoundError("Prospect not found in this workspace.")
    return row


# ---------------------------------------------------------------------------
# Outreach drafts
# ---------------------------------------------------------------------------


def draft_email_for_prospect(
    db: Session,
    *,
    workspace_id: UUID,
    prospect_id: UUID,
    actor_user_id: UUID,
    angle: str | None = None,
    sender_name: str | None = None,
    request: Request | None = None,
) -> OutreachEmail:
    prospect = get_prospect(db, workspace_id=workspace_id, prospect_id=prospect_id)
    if not prospect.contact_email:
        raise InvalidProspectError(
            "Prospect has no contact_email — add one before drafting outreach."
        )

    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )

    draft = draft_outreach_email(
        prospect=prospect,
        profile=profile,
        angle=angle,
        sender_name=sender_name,
        db=db,
        workspace_id=workspace_id,
    )

    email = OutreachEmail(
        workspace_id=workspace_id,
        prospect_id=prospect.id,
        subject=draft.subject,
        body=draft.body,
        to_email=prospect.contact_email,
        status=OutreachEmailStatus.DRAFT,
        source=draft.source,
        model_used=draft.model_used,
        created_by=actor_user_id,
    )
    db.add(email)
    db.flush()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="outreach_email.drafted",
        resource_type="outreach_email",
        resource_id=email.id,
        metadata={"prospect_id": str(prospect.id), "source": draft.source},
        request=request,
    )

    db.commit()
    db.refresh(email)
    return email


def get_email(
    db: Session, *, workspace_id: UUID, email_id: UUID
) -> OutreachEmail:
    row = (
        db.query(OutreachEmail)
        .filter(
            OutreachEmail.id == email_id,
            OutreachEmail.workspace_id == workspace_id,
        )
        .first()
    )
    if row is None:
        raise OutreachEmailNotFoundError("Outreach email not found in this workspace.")
    return row


def list_emails_for_prospect(
    db: Session, *, workspace_id: UUID, prospect_id: UUID
) -> list[OutreachEmail]:
    return (
        db.query(OutreachEmail)
        .filter(
            OutreachEmail.workspace_id == workspace_id,
            OutreachEmail.prospect_id == prospect_id,
        )
        .order_by(OutreachEmail.created_at.desc())
        .all()
    )


def update_email(
    db: Session,
    *,
    workspace_id: UUID,
    email_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    subject: str | None,
    body: str | None,
    request: Request | None = None,
) -> OutreachEmail:
    require_role_at_least(actor_role, Role.MARKETER)
    email = get_email(db, workspace_id=workspace_id, email_id=email_id)
    if email.status not in (OutreachEmailStatus.DRAFT, OutreachEmailStatus.APPROVED):
        raise InvalidOutreachStateError(
            f"Cannot edit a `{email.status.value}` email."
        )
    if subject is not None:
        email.subject = subject.strip()[:512]
    if body is not None:
        email.body = body
    # Editing an approved email reverts it to DRAFT — needs re-approval.
    if email.status == OutreachEmailStatus.APPROVED and (
        subject is not None or body is not None
    ):
        email.status = OutreachEmailStatus.DRAFT
        email.approved_by = None
        email.approved_at = None

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="outreach_email.edited",
        resource_type="outreach_email",
        resource_id=email.id,
        metadata={},
        request=request,
    )

    db.commit()
    db.refresh(email)
    return email


def approve_email(
    db: Session,
    *,
    workspace_id: UUID,
    email_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> OutreachEmail:
    require_role_at_least(actor_role, Role.ADMIN)
    email = get_email(db, workspace_id=workspace_id, email_id=email_id)
    if email.status != OutreachEmailStatus.DRAFT:
        raise InvalidOutreachStateError(
            f"Cannot approve a `{email.status.value}` email."
        )
    email.status = OutreachEmailStatus.APPROVED
    email.approved_by = actor_user_id
    email.approved_at = datetime.now(timezone.utc)

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="outreach_email.approved",
        resource_type="outreach_email",
        resource_id=email.id,
        metadata={},
        request=request,
    )

    db.commit()
    db.refresh(email)
    return email


def send_approved_email(
    db: Session,
    *,
    workspace_id: UUID,
    email_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> OutreachEmail:
    """Send an approved outreach email via the configured SMTP transport.

    Failures are persisted as `status=failed` with the error message, and the
    caller receives a 502 so the UI surfaces the problem rather than silently
    losing the message."""

    require_role_at_least(actor_role, Role.ADMIN)
    email = get_email(db, workspace_id=workspace_id, email_id=email_id)
    if email.status != OutreachEmailStatus.APPROVED:
        raise InvalidOutreachStateError(
            "Email must be approved before it can be sent."
        )
    if not email.to_email:
        raise InvalidOutreachStateError("Email has no recipient address.")

    # Per-minute send throttle. Stops a misconfigured loop from spam-flagging
    # the sending domain. Counted from successful sends only (status=SENT) so
    # an SMTP outage doesn't artificially block recovery.
    if settings.outreach_send_per_minute > 0:
        from datetime import timedelta as _td

        window_start = datetime.now(timezone.utc) - _td(minutes=1)
        sent_in_window = (
            db.query(OutreachEmail)
            .filter(
                OutreachEmail.workspace_id == workspace_id,
                OutreachEmail.status == OutreachEmailStatus.SENT,
                OutreachEmail.sent_at >= window_start,
            )
            .count()
        )
        if sent_in_window >= settings.outreach_send_per_minute:
            raise OutreachSendFailedError(
                f"Outreach send throttle hit "
                f"({settings.outreach_send_per_minute}/minute). Wait ~60s and retry."
            )

    # Plan-limit gate. Sends count even if SMTP later fails — this is a cap on
    # *attempts* so a misconfigured deployment can't burn the whole quota
    # silently. Adjust if you want to only count successful sends.
    billing_service.assert_within_outreach_email_limit(
        db, workspace_id=workspace_id
    )

    # Generate a reply token the first time we send. Reuse on resend so a
    # single conversation thread keeps routing to the same outreach_email row.
    # Format: `<id>.<sig>` where id is 16 lowercase hex chars (8 bytes
    # entropy) and sig is the first 16 hex chars of
    # HMAC-SHA256(INBOUND_EMAIL_SECRET, id). Lowercase-only because the
    # inbound parser lowercases the email local part before lookup.
    if email.reply_token is None:
        email.reply_token = _build_reply_token()

    reply_to: str | None = None
    if settings.inbound_email_domain:
        reply_to = (
            f"reply+{email.reply_token}@{settings.inbound_email_domain.strip().lstrip('@')}"
        )

    final_body = _append_unsubscribe(email.body)
    draft = EmailMessageDraft(
        subject=email.subject,
        text_body=final_body,
        html_body=_to_html(final_body),
        reply_to=reply_to,
    )
    sent = send_email(to=email.to_email, draft=draft)

    if not sent:
        email.status = OutreachEmailStatus.FAILED
        email.error_message = (
            "SMTP not configured (set SMTP_HOST etc.) or transport rejected the message."
        )
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER,
            actor_id=actor_user_id,
            action="outreach_email.send_failed",
            resource_type="outreach_email",
            resource_id=email.id,
            metadata={"to": email.to_email},
            request=request,
        )
        db.commit()
        raise OutreachSendFailedError(email.error_message)

    now = datetime.now(timezone.utc)
    email.status = OutreachEmailStatus.SENT
    email.sent_at = now
    email.error_message = None

    prospect = (
        db.query(BacklinkProspect)
        .filter(BacklinkProspect.id == email.prospect_id)
        .first()
    )
    if prospect is not None:
        prospect.status = ProspectStatus.CONTACTED
        prospect.last_contacted_at = now

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="outreach_email.sent",
        resource_type="outreach_email",
        resource_id=email.id,
        metadata={"to": email.to_email, "prospect_id": str(email.prospect_id)},
        request=request,
    )
    billing_service.record_usage_event(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.OUTREACH_EMAIL_SENT,
        metadata={"prospect_id": str(email.prospect_id)},
    )

    db.commit()
    db.refresh(email)
    return email


# ---------------------------------------------------------------------------
# Inbound webhook handler
# ---------------------------------------------------------------------------


# Postmark / Sendgrid / Mailgun all flag bounces with one of these textual
# markers. We don't try to be exhaustive — if a parse provider sends a clear
# bounce signal in any common shape, we honour it.
_BOUNCE_MARKERS = ("bounce", "bounced", "undeliverable", "delivery-failure")


def _extract_reply_token(addr: str | None) -> str | None:
    """Pull `<token>` out of a Reply-To address shaped `reply+<token>@domain`."""

    if not addr:
        return None
    # Strip any name part: "Foo <reply+abc@x.com>" → "reply+abc@x.com"
    if "<" in addr and ">" in addr:
        addr = addr.split("<", 1)[1].split(">", 1)[0]
    addr = addr.strip().lower()
    local = addr.split("@", 1)[0]
    if "+" not in local:
        return None
    prefix, _, token = local.partition("+")
    if prefix != "reply" or not token:
        return None
    return token


def _looks_like_bounce(payload: dict) -> bool:
    # Postmark inbound JSON → bounce records have `Type` like "HardBounce".
    # Sendgrid event → category contains "bounce". Mailgun event-data shape
    # has `event` = "failed". Our handler treats any of these as bounce.
    bounce_type = (
        payload.get("BounceType")
        or payload.get("Type")
        or payload.get("event")
        or payload.get("Event")
        or ""
    )
    if not bounce_type:
        return False
    bt = str(bounce_type).lower()
    return any(marker in bt for marker in _BOUNCE_MARKERS)


def handle_inbound_email(
    db: Session,
    *,
    payload: dict,
    request: Request | None = None,
) -> dict:
    """Process a parsed inbound email or bounce notification.

    Looks up the matching outreach_email by reply_token, then:
      * If the payload smells like a bounce → mark email + prospect bounced
      * Otherwise → mark email replied + prospect replied

    Returns a small dict for logging; never raises on unknown tokens (we
    don't want to leak which tokens are valid)."""

    # Reply-To-style: the customer's reply lands at reply+<token>@<domain>,
    # which the parse service forwards to us as the inbound message's `To`.
    to_field = (
        payload.get("To")
        or payload.get("to")
        or payload.get("recipient")
        or ""
    )
    token = _extract_reply_token(to_field)
    if not token:
        return {"matched": False, "reason": "no_reply_token"}

    # Reject HMAC-signed tokens with a bad signature *before* hitting the DB —
    # an attacker hammering the endpoint with random tokens can't enumerate.
    if not verify_reply_token(token):
        return {"matched": False, "reason": "bad_signature"}

    email = (
        db.query(OutreachEmail)
        .filter(OutreachEmail.reply_token == token)
        .first()
    )
    if email is None:
        return {"matched": False, "reason": "unknown_token"}

    is_bounce = _looks_like_bounce(payload)
    now = datetime.now(timezone.utc)

    prospect = (
        db.query(BacklinkProspect)
        .filter(BacklinkProspect.id == email.prospect_id)
        .first()
    )

    if is_bounce:
        email.status = OutreachEmailStatus.BOUNCED
        if prospect is not None:
            prospect.status = ProspectStatus.BOUNCED
        action = "outreach_email.bounced_inbound"
    else:
        email.status = OutreachEmailStatus.REPLIED
        email.replied_at = now
        if prospect is not None:
            prospect.status = ProspectStatus.REPLIED
        action = "outreach_email.replied_inbound"

    audit_service.log_event(
        db,
        workspace_id=email.workspace_id,
        actor_type=AuditActorType.SYSTEM,
        actor_id=None,
        action=action,
        resource_type="outreach_email",
        resource_id=email.id,
        metadata={
            "from": payload.get("From") or payload.get("from"),
            "subject": payload.get("Subject") or payload.get("subject"),
            "is_bounce": is_bounce,
        },
        request=request,
    )

    db.commit()
    db.refresh(email)
    return {
        "matched": True,
        "outreach_email_id": str(email.id),
        "is_bounce": is_bounce,
    }


def mark_email_replied(
    db: Session,
    *,
    workspace_id: UUID,
    email_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    won: bool = False,
    backlink_url: str | None = None,
    request: Request | None = None,
) -> OutreachEmail:
    require_role_at_least(actor_role, Role.MARKETER)
    email = get_email(db, workspace_id=workspace_id, email_id=email_id)
    if email.status != OutreachEmailStatus.SENT:
        raise InvalidOutreachStateError(
            "Only sent emails can be marked as replied."
        )

    now = datetime.now(timezone.utc)
    email.status = OutreachEmailStatus.REPLIED
    email.replied_at = now

    prospect = (
        db.query(BacklinkProspect)
        .filter(BacklinkProspect.id == email.prospect_id)
        .first()
    )
    if prospect is not None:
        prospect.status = ProspectStatus.WON if won else ProspectStatus.REPLIED
        if won:
            prospect.won_at = now
            if backlink_url:
                prospect.backlink_url = backlink_url

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="outreach_email.replied",
        resource_type="outreach_email",
        resource_id=email.id,
        metadata={"won": won, "backlink_url": backlink_url},
        request=request,
    )

    db.commit()
    db.refresh(email)
    return email


def _to_html(text: str) -> str:
    import html

    safe = html.escape(text)
    paragraphs = [f"<p>{p}</p>" for p in safe.split("\n\n") if p.strip()]
    return (
        "<html><body style=\"font-family:-apple-system,sans-serif;color:#111827;\">"
        + "".join(p.replace("\n", "<br>") for p in paragraphs)
        + "</body></html>"
    )


# ---------------------------------------------------------------------------
# Follow-ups + unsubscribe
# ---------------------------------------------------------------------------


def _build_reply_token() -> str:
    """Mint a fresh reply token of the form `<id>.<sig>`.

    The signature pins the token to the deployment's INBOUND_EMAIL_SECRET so
    even if the public reply address gets indexed somewhere, an attacker
    can't forge a synthetic token without the secret. Verification is
    constant-time."""

    import hashlib
    import hmac

    id_part = secrets.token_hex(8)  # 16 lowercase hex chars
    secret = (settings.inbound_email_secret or "").encode("utf-8")
    if not secret:
        # No secret configured → fall back to bare id (legacy mode). The
        # shared-secret X-Inbound-Secret header still gates the webhook.
        return id_part
    digest = hmac.new(secret, id_part.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{id_part}.{digest[:16]}"


def verify_reply_token(token: str | None) -> bool:
    """True iff the token has a valid HMAC signature for the configured
    secret. Bare tokens (no `.`) are considered valid for backward compat
    with messages sent before HMAC was rolled out — defense in depth still
    comes from the X-Inbound-Secret header on the webhook itself."""

    import hashlib
    import hmac as _hmac

    if not token:
        return False
    if "." not in token:
        return True  # legacy bare-token format
    id_part, _, sig = token.partition(".")
    if not id_part or not sig:
        return False
    secret = (settings.inbound_email_secret or "").encode("utf-8")
    if not secret:
        return False
    expected = _hmac.new(secret, id_part.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return _hmac.compare_digest(expected, sig)


def _append_unsubscribe(body: str) -> str:
    """Append a CAN-SPAM/GDPR-compliant unsubscribe footer. Uses the
    workspace-agnostic UNSUBSCRIBE_URL env var when configured, else a
    plain "reply with STOP" line so we always include *some* opt-out path."""

    body = body.rstrip()
    if settings.unsubscribe_url:
        footer = (
            f"\n\n---\nIf you'd rather not hear from us again, "
            f"unsubscribe at: {settings.unsubscribe_url}"
        )
    else:
        footer = (
            "\n\n---\nNot interested? Reply with STOP and we'll never contact you again."
        )
    return body + footer


def draft_followup_for_email(
    db: Session,
    *,
    workspace_id: UUID,
    email_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    instructions: str | None = None,
    request: Request | None = None,
) -> OutreachEmail:
    """Draft a follow-up email referencing a previously-sent outreach.

    The follow-up enters DRAFT status (Admin must still approve before send).
    Subject prepends 'Re: ' and the body opens with a gentle bump."""

    require_role_at_least(actor_role, Role.MARKETER)
    parent = get_email(db, workspace_id=workspace_id, email_id=email_id)
    if parent.status not in (OutreachEmailStatus.SENT, OutreachEmailStatus.REPLIED):
        raise InvalidOutreachStateError(
            "Can only follow up on a SENT (or REPLIED) email."
        )

    prospect = (
        db.query(BacklinkProspect)
        .filter(BacklinkProspect.id == parent.prospect_id)
        .first()
    )
    if prospect is None:
        raise ProspectNotFoundError("Parent email's prospect is gone.")

    salutation = (
        f"Hi {prospect.contact_name}" if prospect.contact_name else "Hi again"
    )
    bump = (
        "Bumping this to the top of your inbox in case it got buried. "
        "Happy to keep it brief if helpful."
    )
    extra = f"\n\n{instructions}" if instructions else ""
    body = (
        f"{salutation},\n\n{bump}{extra}\n\n"
        f"For context, here's the original note:\n\n"
        f"---\n{parent.body}"
    )
    subject = parent.subject if parent.subject.lower().startswith("re:") else f"Re: {parent.subject}"

    followup = OutreachEmail(
        workspace_id=workspace_id,
        prospect_id=parent.prospect_id,
        subject=subject[:512],
        body=body,
        to_email=parent.to_email,
        status=OutreachEmailStatus.DRAFT,
        source="followup",
        model_used=None,
        created_by=actor_user_id,
        parent_email_id=parent.id,
        step_index=parent.step_index + 1,
    )
    db.add(followup)
    db.flush()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="outreach_email.followup_drafted",
        resource_type="outreach_email",
        resource_id=followup.id,
        metadata={
            "parent_email_id": str(parent.id),
            "step_index": followup.step_index,
        },
        request=request,
    )

    db.commit()
    db.refresh(followup)
    return followup


def auto_draft_pending_followups(
    db: Session,
    *,
    days_silent: int | None = None,
) -> int:
    """Find SENT emails with no reply older than `days_silent` and lacking a
    follow-up — draft one for each. Designed to be invoked from a Celery
    beat job. Returns the number of follow-ups drafted."""

    from datetime import timedelta as _td

    cutoff_days = days_silent or settings.outreach_followup_after_days
    if cutoff_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - _td(days=cutoff_days)

    # SENT emails older than cutoff with no descendant follow-up.
    candidates = (
        db.query(OutreachEmail)
        .filter(
            OutreachEmail.status == OutreachEmailStatus.SENT,
            OutreachEmail.sent_at <= cutoff,
        )
        .all()
    )
    drafted = 0
    for parent in candidates:
        already = (
            db.query(OutreachEmail)
            .filter(OutreachEmail.parent_email_id == parent.id)
            .first()
        )
        if already is not None:
            continue
        # Use the system actor — no IP/UA available from a beat job.
        from app.security.permissions import Role as _Role

        try:
            draft_followup_for_email(
                db,
                workspace_id=parent.workspace_id,
                email_id=parent.id,
                actor_user_id=parent.created_by or parent.workspace_id,  # best-effort
                actor_role=_Role.MARKETER,
                instructions=None,
                request=None,
            )
            drafted += 1
        except Exception as exc:  # noqa: BLE001 — keep beat job moving
            log.warning(
                "outreach.followup_draft_failed",
                email_id=str(parent.id),
                error=str(exc),
            )
    return drafted
