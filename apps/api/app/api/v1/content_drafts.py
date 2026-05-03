from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.content_draft import ContentDraftStatus, ContentDraftType
from app.models.workspace_member import WorkspaceMember
from app.schemas.content_drafts import (
    ContentDraftPublic,
    CreateManualContentDraftRequest,
    GenerateContentDraftRequest,
    PublishContentDraftRequest,
    RefreshContentDraftRequest,
    RejectContentDraftRequest,
    UpdateContentDraftRequest,
)
from app.security.dependencies import get_current_member
from app.security.permissions import Role, require_role_at_least
from app.services import content_draft_service, image_upload_service

router = APIRouter()


@router.get(
    "/{workspace_id}/content-drafts",
    response_model=list[ContentDraftPublic],
)
def list_drafts(
    workspace_id: UUID,
    type: ContentDraftType | None = Query(default=None),
    status: ContentDraftStatus | None = Query(default=None),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[ContentDraftPublic]:
    rows = content_draft_service.list_drafts(
        db, workspace_id=workspace_id, type=type, status=status
    )
    return [ContentDraftPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/content-drafts/generate",
    response_model=ContentDraftPublic,
)
def generate(
    workspace_id: UUID,
    payload: GenerateContentDraftRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    draft = content_draft_service.generate_via_agent(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        type=payload.type,
        topic=payload.topic,
        keywords=payload.keywords,
        target_url=payload.target_url,
        audience=payload.audience,
        notes=payload.notes,
        request=request,
    )
    return ContentDraftPublic.model_validate(draft)


@router.post(
    "/{workspace_id}/content-drafts/refresh",
    response_model=ContentDraftPublic,
)
def refresh(
    workspace_id: UUID,
    payload: RefreshContentDraftRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    """Rewrite an existing draft (by id) or any URL (we fetch + parse it)
    into a new draft. The new draft references its origin via
    seo_metadata.refreshed_from."""

    draft = content_draft_service.refresh_draft(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        source_draft_id=payload.source_draft_id,
        source_url=payload.source_url,
        instructions=payload.instructions,
        request=request,
    )
    return ContentDraftPublic.model_validate(draft)


@router.post(
    "/{workspace_id}/content-drafts",
    response_model=ContentDraftPublic,
)
def create_manual(
    workspace_id: UUID,
    payload: CreateManualContentDraftRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    draft = content_draft_service.create_manual(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        type=payload.type,
        title=payload.title,
        body=payload.body,
        target_url=payload.target_url,
        keywords=payload.keywords,
        seo_metadata=payload.seo_metadata,
        notes=payload.notes,
        slug=payload.slug,
        excerpt=payload.excerpt,
        image_url=payload.image_url,
        request=request,
    )
    return ContentDraftPublic.model_validate(draft)


@router.get(
    "/{workspace_id}/content-drafts/{draft_id}",
    response_model=ContentDraftPublic,
)
def get_one(
    workspace_id: UUID,
    draft_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    draft = content_draft_service.get_draft(
        db, workspace_id=workspace_id, draft_id=draft_id
    )
    return ContentDraftPublic.model_validate(draft)


@router.patch(
    "/{workspace_id}/content-drafts/{draft_id}",
    response_model=ContentDraftPublic,
)
def update_draft(
    workspace_id: UUID,
    draft_id: UUID,
    payload: UpdateContentDraftRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    draft = content_draft_service.update_draft(
        db,
        workspace_id=workspace_id,
        draft_id=draft_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        updates=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return ContentDraftPublic.model_validate(draft)


@router.post(
    "/{workspace_id}/content-drafts/{draft_id}/approve",
    response_model=ContentDraftPublic,
)
def approve(
    workspace_id: UUID,
    draft_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    draft = content_draft_service.approve_draft(
        db,
        workspace_id=workspace_id,
        draft_id=draft_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return ContentDraftPublic.model_validate(draft)


@router.post(
    "/{workspace_id}/content-drafts/{draft_id}/reject",
    response_model=ContentDraftPublic,
)
def reject(
    workspace_id: UUID,
    draft_id: UUID,
    request: Request,
    payload: RejectContentDraftRequest | None = None,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    draft = content_draft_service.reject_draft(
        db,
        workspace_id=workspace_id,
        draft_id=draft_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        reason=payload.reason if payload else None,
        request=request,
    )
    return ContentDraftPublic.model_validate(draft)


@router.post(
    "/{workspace_id}/content-drafts/{draft_id}/publish",
    response_model=ContentDraftPublic,
)
def publish(
    workspace_id: UUID,
    draft_id: UUID,
    request: Request,
    payload: PublishContentDraftRequest | None = None,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    draft = content_draft_service.publish_draft(
        db,
        workspace_id=workspace_id,
        draft_id=draft_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        publication_url=payload.publication_url if payload else None,
        request=request,
    )
    return ContentDraftPublic.model_validate(draft)


@router.post(
    "/{workspace_id}/content-drafts/{draft_id}/archive",
    response_model=ContentDraftPublic,
)
def archive(
    workspace_id: UUID,
    draft_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    draft = content_draft_service.archive_draft(
        db,
        workspace_id=workspace_id,
        draft_id=draft_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return ContentDraftPublic.model_validate(draft)


@router.get("/{workspace_id}/content-drafts.csv")
def export_content_drafts_csv(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    from fastapi import Response

    from app.services.csv_export import export_content_drafts

    body = export_content_drafts(db, workspace_id=workspace_id)
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="content-drafts.csv"'
        },
    )


# ---------------------------------------------------------------------------
# Image uploads
# ---------------------------------------------------------------------------


class ImageUploadResponse(BaseModel):
    url: str
    bytes: int
    content_type: str
    filename: str


@router.post(
    "/{workspace_id}/content-drafts/images",
    response_model=ImageUploadResponse,
)
def upload_image(
    workspace_id: UUID,
    file: UploadFile = File(...),
    member: WorkspaceMember = Depends(get_current_member),
    _db: Session = Depends(get_db),
) -> ImageUploadResponse:
    """Upload a blog cover or inline image. Marketers and above can upload;
    viewers / analysts can't. Returns the URL the editor can stamp into the
    draft body or the cover_image field."""

    require_role_at_least(member.role, Role.MARKETER)
    saved = image_upload_service.save_image(
        workspace_id=workspace_id, upload=file
    )
    return ImageUploadResponse(**saved)


# ---------------------------------------------------------------------------
# AI Assistant
# ---------------------------------------------------------------------------


class AiAssistRequest(BaseModel):
    """Body for /content-drafts/{id}/ai-assist.

    `action` is one of: outline, expand, refine, suggest_title, suggest_meta.
    `selection` is required for expand + refine. `instructions` is the
    writer's free-text guidance ("more concrete examples", "tighten",
    "explain like the reader has never used GA4").
    """

    action: str
    selection: str | None = None
    instructions: str | None = None


class AiAssistResponse(BaseModel):
    action: str
    source: str  # "llm" or "deterministic"
    result: dict


@router.post(
    "/{workspace_id}/content-drafts/{draft_id}/ai-assist",
    response_model=AiAssistResponse,
)
def ai_assist(
    workspace_id: UUID,
    draft_id: UUID,
    payload: AiAssistRequest,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AiAssistResponse:
    """Run a single AI Assistant action against the draft. Returns the
    AI's suggestion — the operator decides whether to insert / replace /
    discard. Token + dollar cost are recorded against the workspace's
    LLM_CALL meter automatically."""

    require_role_at_least(member.role, Role.MARKETER)

    from app.services import blog_ai_assist_service

    draft = content_draft_service.get_draft(
        db, workspace_id=workspace_id, draft_id=draft_id
    )
    result = blog_ai_assist_service.assist(
        db,
        workspace_id=workspace_id,
        draft=draft,
        action=payload.action,
        selection=payload.selection,
        instructions=payload.instructions,
    )
    return AiAssistResponse(**result)
