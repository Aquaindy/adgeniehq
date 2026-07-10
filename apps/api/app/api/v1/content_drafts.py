from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.exceptions import AdGenieError
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


class _UnsupportedFormatError(AdGenieError):
    status_code = 400
    code = "unsupported_format"


class _NothingToExportError(AdGenieError):
    status_code = 404
    code = "nothing_to_export"


def _export_response(body: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_ids(ids: str | None) -> list[UUID]:
    if not ids:
        return []
    out: list[UUID] = []
    for chunk in ids.split(","):
        chunk = chunk.strip()
        if chunk:
            try:
                out.append(UUID(chunk))
            except ValueError as exc:
                raise _UnsupportedFormatError(f"Invalid draft id: {chunk}") from exc
    return out


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


# NOTE: declared BEFORE `/{draft_id}` so the literal "download" segment isn't
# parsed as a draft-id UUID.
@router.get("/{workspace_id}/content-drafts/download")
def download_drafts_bundle(
    workspace_id: UUID,
    fmt: str = Query(default="docx", alias="format"),
    ids: str | None = Query(
        default=None, description="Comma-separated draft ids; omit for all (filtered)."
    ),
    type: ContentDraftType | None = Query(default=None),
    status: ContentDraftStatus | None = Query(default=None),
    platform: str | None = Query(default=None),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> Response:
    """Download several drafts as one .txt or .docx. Pass `ids` for a specific
    set (e.g. a freshly generated social pack), or filters for a slice."""

    from app.services import content_draft_export_service as export

    parsed_ids = _parse_ids(ids)
    if parsed_ids:
        drafts = export.get_drafts_by_ids(db, workspace_id=workspace_id, ids=parsed_ids)
    else:
        drafts = content_draft_service.list_drafts(
            db, workspace_id=workspace_id, type=type, status=status
        )
        if platform:
            drafts = [d for d in drafts if d.platform == platform]
    if not drafts:
        raise _NothingToExportError("No drafts matched — nothing to download.")

    base = export.safe_filename("social_content", platform or "")
    fmt_lower = fmt.lower()
    if fmt_lower == "txt":
        body = export.render_bundle_txt(drafts, title="Social content")
        return _export_response(body, "text/plain; charset=utf-8", f"{base}.txt")
    if fmt_lower == "docx":
        body = export.render_bundle_docx(drafts, title="Social content")
        return _export_response(body, export.DOCX_MEDIA_TYPE, f"{base}.docx")
    raise _UnsupportedFormatError("Use ?format=txt or ?format=docx.")


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


@router.get("/{workspace_id}/content-drafts/{draft_id}/download")
def download_draft(
    workspace_id: UUID,
    draft_id: UUID,
    fmt: str = Query(default="docx", alias="format"),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> Response:
    """Download one draft as .txt or .docx (the .docx embeds its image)."""

    from app.services import content_draft_export_service as export

    draft = content_draft_service.get_draft(
        db, workspace_id=workspace_id, draft_id=draft_id
    )
    base = export.safe_filename(draft.platform or "content", str(draft.title)[:40])
    fmt_lower = fmt.lower()
    if fmt_lower == "txt":
        return _export_response(
            export.render_txt(draft), "text/plain; charset=utf-8", f"{base}.txt"
        )
    if fmt_lower == "docx":
        return _export_response(
            export.render_docx(draft), export.DOCX_MEDIA_TYPE, f"{base}.docx"
        )
    raise _UnsupportedFormatError("Use ?format=txt or ?format=docx.")


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
    "/{workspace_id}/content-drafts/{draft_id}/image",
    response_model=ContentDraftPublic,
)
def generate_image(
    workspace_id: UUID,
    draft_id: UUID,
    request: Request,
    style: str = Query(
        default="concept",
        description="'concept' (headline + graphics) or 'product' (product-box promo).",
    ),
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ContentDraftPublic:
    """Generate an AI creative image for the draft and stamp it onto
    `image_url`. Requires an OpenAI key and Marketer+; costs image credits."""

    from app.services import image_generation_service

    draft = image_generation_service.generate_for_draft(
        db,
        workspace_id=workspace_id,
        draft_id=draft_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        style=style,
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
