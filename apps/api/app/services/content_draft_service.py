"""Service layer for ContentDraft objects.

Drafts are produced one of two ways:
  1. `generate_via_agent` runs the ContentWriter agent (which uses the LLM
     when configured) and converts the resulting skill output into a
     ContentDraft row.
  2. `create_manual` accepts a fully human-authored draft.

Status flow:
    draft  → approved (Admin+) → published
           → rejected
           → archived
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.agents.runtime import run_agent
from app.core.exceptions import AdVantaError
from app.models.audit_log import AuditActorType
from app.models.content_draft import (
    ContentDraft,
    ContentDraftStatus,
    ContentDraftType,
)
from app.models.skill_output import SkillOutput
from app.models.usage_event import UsageEventType
from app.security.permissions import Role, require_role_at_least
from app.services import audit_service, billing_service


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContentDraftNotFoundError(AdVantaError):
    status_code = 404
    code = "content_draft_not_found"


class InvalidDraftStateError(AdVantaError):
    status_code = 409
    code = "invalid_draft_state"


class GenerationFailedError(AdVantaError):
    status_code = 500
    code = "content_generation_failed"


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


def generate_via_agent(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    type: ContentDraftType,
    topic: str,
    keywords: list[str] | None = None,
    target_url: str | None = None,
    audience: str | None = None,
    notes: str | None = None,
    request: Request | None = None,
) -> ContentDraft:
    """Run the ContentWriter agent and persist its output as a ContentDraft."""

    billing_service.assert_within_content_draft_limit(
        db, workspace_id=workspace_id
    )

    run = run_agent(
        db,
        workspace_id=workspace_id,
        agent_type="content_writer",
        triggered_by_user_id=actor_user_id,
        input_payload={
            "type": type.value,
            "topic": topic,
            "keywords": keywords or [],
            "target_url": target_url,
            "audience": audience,
            "notes": notes,
        },
    )

    if run.status.value != "succeeded":
        raise GenerationFailedError(
            run.error_message or "Content writer agent failed without an error message."
        )

    skill_output = (
        db.query(SkillOutput)
        .filter(
            SkillOutput.agent_run_id == run.id,
            SkillOutput.output_type == "content_draft_payload",
        )
        .order_by(SkillOutput.created_at.desc())
        .first()
    )
    if skill_output is None:
        raise GenerationFailedError(
            "Content writer produced no draft payload — check the run details."
        )

    payload = skill_output.payload or {}

    draft = ContentDraft(
        workspace_id=workspace_id,
        agent_run_id=run.id,
        type=type,
        status=ContentDraftStatus.DRAFT,
        title=payload.get("title") or topic,
        body=payload.get("body") or "",
        target_url=target_url or payload.get("target_url"),
        image_url=payload.get("image_url"),
        keywords=payload.get("keywords") or keywords or [],
        seo_metadata=payload.get("seo_metadata") or {},
        notes=notes,
        source="agent",
        model_used=payload.get("model_used"),
        created_by=actor_user_id,
    )
    db.add(draft)
    db.flush()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.generated",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={
            "type": type.value,
            "topic": topic,
            "source": payload.get("source"),
            "agent_run_id": str(run.id),
        },
        request=request,
    )
    billing_service.record_usage_event(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.CONTENT_DRAFT,
        metadata={"type": type.value, "source": payload.get("source")},
    )

    db.commit()
    db.refresh(draft)
    return draft


# ---------------------------------------------------------------------------
# Manual create
# ---------------------------------------------------------------------------


def create_manual(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    type: ContentDraftType,
    title: str,
    body: str,
    target_url: str | None,
    keywords: list[str] | None,
    seo_metadata: dict | None,
    notes: str | None,
    slug: str | None = None,
    excerpt: str | None = None,
    image_url: str | None = None,
    request: Request | None = None,
) -> ContentDraft:
    billing_service.assert_within_content_draft_limit(
        db, workspace_id=workspace_id
    )
    draft = ContentDraft(
        workspace_id=workspace_id,
        type=type,
        status=ContentDraftStatus.DRAFT,
        title=title.strip()[:512],
        body=body,
        target_url=target_url,
        slug=_normalize_slug(slug) if slug else None,
        excerpt=excerpt,
        image_url=image_url,
        keywords=keywords or [],
        seo_metadata=seo_metadata or {},
        notes=notes,
        source="manual",
        model_used=None,
        created_by=actor_user_id,
    )
    db.add(draft)
    db.flush()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.created_manually",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={"type": type.value},
        request=request,
    )
    billing_service.record_usage_event(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.CONTENT_DRAFT,
        metadata={"type": type.value, "source": "manual"},
    )

    db.commit()
    db.refresh(draft)
    return draft


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def list_drafts(
    db: Session,
    *,
    workspace_id: UUID,
    type: ContentDraftType | None = None,
    status: ContentDraftStatus | None = None,
    limit: int = 50,
) -> list[ContentDraft]:
    query = db.query(ContentDraft).filter(ContentDraft.workspace_id == workspace_id)
    if type is not None:
        query = query.filter(ContentDraft.type == type)
    if status is not None:
        query = query.filter(ContentDraft.status == status)
    return query.order_by(desc(ContentDraft.created_at)).limit(limit).all()


def get_draft(
    db: Session, *, workspace_id: UUID, draft_id: UUID
) -> ContentDraft:
    row = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.id == draft_id,
            ContentDraft.workspace_id == workspace_id,
        )
        .first()
    )
    if row is None:
        raise ContentDraftNotFoundError("Content draft not found in this workspace.")
    return row


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


EDITABLE_FIELDS = {
    "title",
    "body",
    "target_url",
    "slug",
    "excerpt",
    "image_url",
    "keywords",
    "seo_metadata",
    "notes",
}


def _normalize_slug(raw: str) -> str:
    """Lowercase, replace whitespace + invalid chars with '-', collapse runs.
    Stays under 255 chars to fit the column. Used both at create-manual time
    and on publish (auto-generation from title)."""

    import re

    s = (raw or "").strip().lower()
    # Replace anything that's not [a-z0-9-] with a single dash.
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:255] or "post"


def _ensure_unique_slug(db: Session, *, workspace_id: UUID, base: str) -> str:
    """Append `-2`, `-3`, ... until the slug is unique within the workspace."""

    candidate = base
    suffix = 2
    while True:
        clash = (
            db.query(ContentDraft.id)
            .filter(
                ContentDraft.workspace_id == workspace_id,
                ContentDraft.slug == candidate,
            )
            .first()
        )
        if clash is None:
            return candidate
        candidate = f"{base[:250]}-{suffix}"
        suffix += 1


def update_draft(
    db: Session,
    *,
    workspace_id: UUID,
    draft_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    updates: dict,
    request: Request | None = None,
) -> ContentDraft:
    draft = get_draft(db, workspace_id=workspace_id, draft_id=draft_id)
    require_role_at_least(actor_role, Role.MARKETER)

    if draft.status in (ContentDraftStatus.PUBLISHED, ContentDraftStatus.ARCHIVED):
        raise InvalidDraftStateError(
            f"Cannot edit a {draft.status.value} draft."
        )

    changes: dict = {}
    for field, value in updates.items():
        if field not in EDITABLE_FIELDS or value is None:
            continue
        # Normalize slug on the way in so we don't store "Hello World!" as a
        # URL component. The unique-per-workspace partial index will reject
        # collisions; surface that as a 409 in the route layer.
        if field == "slug":
            value = _normalize_slug(value)
        current = getattr(draft, field)
        if current != value:
            changes[field] = {"from": current, "to": value}
            setattr(draft, field, value)

    if not changes:
        return draft

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.edited",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={"fields_changed": list(changes.keys())},
        request=request,
    )

    db.commit()
    db.refresh(draft)
    return draft


def approve_draft(
    db: Session,
    *,
    workspace_id: UUID,
    draft_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> ContentDraft:
    draft = get_draft(db, workspace_id=workspace_id, draft_id=draft_id)
    require_role_at_least(actor_role, Role.ADMIN)

    if draft.status != ContentDraftStatus.DRAFT:
        raise InvalidDraftStateError(
            f"Cannot approve a draft in `{draft.status.value}` state."
        )

    now = datetime.now(timezone.utc)
    draft.status = ContentDraftStatus.APPROVED
    draft.approved_by = actor_user_id
    draft.approved_at = now

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.approved",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={"type": draft.type.value},
        request=request,
    )

    db.commit()
    db.refresh(draft)
    return draft


def reject_draft(
    db: Session,
    *,
    workspace_id: UUID,
    draft_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    reason: str | None = None,
    request: Request | None = None,
) -> ContentDraft:
    draft = get_draft(db, workspace_id=workspace_id, draft_id=draft_id)
    require_role_at_least(actor_role, Role.MARKETER)

    if draft.status not in (ContentDraftStatus.DRAFT, ContentDraftStatus.APPROVED):
        raise InvalidDraftStateError(
            f"Cannot reject a draft in `{draft.status.value}` state."
        )

    draft.status = ContentDraftStatus.REJECTED
    draft.approved_by = None
    draft.approved_at = None

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.rejected",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={"reason": reason},
        request=request,
    )

    db.commit()
    db.refresh(draft)
    return draft


def publish_draft(
    db: Session,
    *,
    workspace_id: UUID,
    draft_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    publication_url: str | None = None,
    use_webhook: bool = True,
    request: Request | None = None,
) -> ContentDraft:
    """Publish an approved draft.

    Three modes, in order of preference:
      1. `publication_url` provided  → record it, mark published.
      2. Workspace has a `publish_webhook_url` and `use_webhook=True` →
         POST the draft to the configured CMS hook; record the
         `published_url` it returns.
      3. Neither configured              → record the publish step but leave
         `target_url` alone (manual publishing path)."""

    from app.models.workspace import Workspace
    from app.services import publish_webhook

    draft = get_draft(db, workspace_id=workspace_id, draft_id=draft_id)
    require_role_at_least(actor_role, Role.ADMIN)

    if draft.status != ContentDraftStatus.APPROVED:
        raise InvalidDraftStateError(
            "Only approved drafts can be published. Approve it first."
        )

    workspace = (
        db.query(Workspace).filter(Workspace.id == workspace_id).first()
    )
    webhook_used = False
    webhook_published_url: str | None = None

    if (
        publication_url is None
        and use_webhook
        and workspace is not None
        and publish_webhook.is_configured(workspace)
    ):
        # Errors here surface as 502 publish_webhook_failed; the caller can
        # retry once the receiver is healthy. We deliberately don't flip the
        # draft to PUBLISHED unless the receiver confirms.
        result = publish_webhook.push_to_webhook(
            workspace=workspace, draft=draft
        )
        webhook_used = True
        webhook_published_url = result.published_url

    draft.status = ContentDraftStatus.PUBLISHED
    draft.published_at = datetime.now(timezone.utc)
    final_url = publication_url or webhook_published_url
    if final_url:
        draft.target_url = final_url

    # Blog publishing: auto-fill slug + excerpt when blank so the post is
    # ready to render at /blog/{slug} without a follow-up edit.
    if draft.type == ContentDraftType.BLOG_POST:
        if not draft.slug:
            base = _normalize_slug(draft.title or "post")
            draft.slug = _ensure_unique_slug(
                db, workspace_id=workspace_id, base=base
            )
        if not draft.excerpt:
            # First ~280 chars of the body, stripped of any leading whitespace
            # / markdown noise. A real excerpt the editor can override later.
            cleaned = " ".join((draft.body or "").split())
            draft.excerpt = cleaned[:280] + ("…" if len(cleaned) > 280 else "")

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.published",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={
            "type": draft.type.value,
            "publication_url": final_url,
            "webhook_used": webhook_used,
        },
        request=request,
    )

    db.commit()
    db.refresh(draft)
    return draft


def refresh_draft(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    source_draft_id: UUID | None = None,
    source_url: str | None = None,
    instructions: str | None = None,
    request: Request | None = None,
) -> ContentDraft:
    """Create a new draft by refreshing an existing one (by id) or any
    public URL (by url). Counts against the content_drafts plan cap.

    The new draft references its origin via metadata.refreshed_from so the
    audit trail and dashboard can link the two."""

    from app.models.onboarding_profile import OnboardingProfile
    from app.skills.content.generation import (
        RefreshRequest,
        refresh_content_draft,
    )

    require_role_at_least(actor_role, Role.MARKETER)
    billing_service.assert_within_content_draft_limit(
        db, workspace_id=workspace_id
    )

    existing_title = ""
    existing_body = ""
    keywords: list[str] = []
    target_url: str | None = None
    content_type: ContentDraftType | None = None
    refreshed_from: dict = {}

    if source_draft_id is not None:
        source = get_draft(db, workspace_id=workspace_id, draft_id=source_draft_id)
        existing_title = source.title
        existing_body = source.body
        keywords = list(source.keywords or [])
        target_url = source.target_url
        content_type = source.type
        refreshed_from = {"draft_id": str(source.id), "title": source.title}
    elif source_url is not None:
        from app.skills.website.fetch import WebsiteFetchError, fetch_html

        try:
            page = fetch_html(source_url)
        except WebsiteFetchError as exc:
            raise AdVantaError(f"Could not fetch {source_url}: {exc}") from exc
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(page.html, "html.parser")
        # Best-effort title + body extraction from common semantic landmarks.
        title_tag = soup.find("h1") or soup.find("title")
        existing_title = (title_tag.get_text() if title_tag else source_url).strip()[:512]
        article = soup.find("article") or soup.find("main") or soup.body
        existing_body = (article.get_text("\n\n") if article else soup.get_text("\n\n")).strip()
        # Default to blog_post when fetching from URL.
        content_type = ContentDraftType.BLOG_POST
        target_url = source_url
        refreshed_from = {"source_url": source_url}
    else:
        class MissingSource(AdVantaError):
            status_code = 400
            code = "missing_source"

        raise MissingSource("Provide either source_draft_id or source_url to refresh.")

    if not existing_body.strip():
        class EmptySource(AdVantaError):
            status_code = 400
            code = "empty_source"

        raise EmptySource("Source content is empty — nothing to refresh.")

    profile = (
        db.query(OnboardingProfile)
        .filter(OnboardingProfile.workspace_id == workspace_id)
        .first()
    )

    payload = refresh_content_draft(
        request=RefreshRequest(
            type=content_type or ContentDraftType.BLOG_POST,
            existing_title=existing_title,
            existing_body=existing_body,
            instructions=instructions,
            keywords=keywords,
            target_url=target_url,
        ),
        profile=profile,
        db=db,
        workspace_id=workspace_id,
    )

    draft = ContentDraft(
        workspace_id=workspace_id,
        type=content_type or ContentDraftType.BLOG_POST,
        status=ContentDraftStatus.DRAFT,
        title=payload.title,
        body=payload.body,
        target_url=target_url,
        keywords=payload.keywords or keywords,
        seo_metadata=payload.seo_metadata or {},
        notes=instructions,
        source="refresh",
        model_used=payload.model_used,
        created_by=actor_user_id,
    )
    # Stamp the lineage onto seo_metadata so it round-trips on read.
    draft.seo_metadata = {
        **(draft.seo_metadata or {}),
        "refreshed_from": refreshed_from,
        "refresh_source_kind": payload.source,
    }
    db.add(draft)
    db.flush()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.refreshed",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={
            "refreshed_from": refreshed_from,
            "instructions": instructions,
            "source_kind": payload.source,
        },
        request=request,
    )
    billing_service.record_usage_event(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.CONTENT_DRAFT,
        metadata={"type": draft.type.value, "source": "refresh"},
    )

    db.commit()
    db.refresh(draft)
    return draft


def archive_draft(
    db: Session,
    *,
    workspace_id: UUID,
    draft_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> ContentDraft:
    draft = get_draft(db, workspace_id=workspace_id, draft_id=draft_id)
    require_role_at_least(actor_role, Role.MARKETER)

    if draft.status == ContentDraftStatus.ARCHIVED:
        return draft

    draft.status = ContentDraftStatus.ARCHIVED

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="content_draft.archived",
        resource_type="content_draft",
        resource_id=draft.id,
        metadata={"type": draft.type.value},
        request=request,
    )

    db.commit()
    db.refresh(draft)
    return draft
