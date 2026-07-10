from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.content_drafts import ContentDraftPublic
from app.schemas.social_content import (
    GenerateSocialPackRequest,
    SocialPackResponse,
    SocialPlatformPublic,
)
from app.security.dependencies import get_current_member
from app.security.permissions import Role, require_role_at_least
from app.services import content_draft_service
from app.social.catalog import SocialFormat, list_platforms

router = APIRouter()


@router.get(
    "/{workspace_id}/social/platforms",
    response_model=list[SocialPlatformPublic],
)
def list_social_platforms(
    workspace_id: UUID,
    format: SocialFormat | None = Query(
        default=None, description="Narrow to `post` or `video_script`."
    ),
    _member: WorkspaceMember = Depends(get_current_member),
) -> list[SocialPlatformPublic]:
    """The supported platforms and their authoring constraints. Static
    reference data; the workspace scope exists only to enforce membership."""

    return [SocialPlatformPublic.from_platform(p) for p in list_platforms(format)]


@router.post(
    "/{workspace_id}/social/generate",
    response_model=SocialPackResponse,
)
def generate_social_pack(
    workspace_id: UUID,
    payload: GenerateSocialPackRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> SocialPackResponse:
    """Turn one topic into a platform-native draft per selected platform.

    Drafts land in `draft` status and are never auto-published. Generation
    spends AI credits for the whole pack, so it needs Marketer or above."""

    require_role_at_least(member.role, Role.MARKETER)

    drafts = content_draft_service.generate_social_pack(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        topic=payload.topic,
        platforms=payload.platforms,
        keywords=payload.keywords,
        audience=payload.audience,
        target_url=payload.target_url,
        notes=payload.notes,
        call_to_action=payload.call_to_action,
        source_url=payload.source_url,
        request=request,
    )
    # Drafts share the topic actually used — the page title when generated from
    # a link with no explicit topic. Reading it off the first draft keeps the
    # response honest rather than echoing back an empty request topic.
    resolved_topic = (
        (drafts[0].seo_metadata or {}).get("topic")
        if drafts
        else None
    ) or payload.topic or ""
    return SocialPackResponse(
        topic=resolved_topic,
        drafts=[ContentDraftPublic.model_validate(d) for d in drafts],
    )
