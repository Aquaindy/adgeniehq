from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.backlink_prospect import ProspectStatus
from app.models.workspace_member import WorkspaceMember
from app.schemas.outreach import (
    BacklinkProspectPublic,
    BulkImportRequest,
    BulkImportResultPublic,
    CreateProspectRequest,
    DiscoverProspectsRequest,
    DiscoveryResultPublic,
    DraftOutreachRequest,
    MarkRepliedRequest,
    OutreachEmailPublic,
    UpdateOutreachRequest,
    UpdateProspectRequest,
)
from app.security.dependencies import get_current_member
from app.services import outreach_service
from app.workers.dispatch import run_or_dispatch
from app.workers.tasks import send_outreach_email_task

router = APIRouter()


# ------------------------------------------------------------------
# Prospects
# ------------------------------------------------------------------


@router.get(
    "/{workspace_id}/backlink-prospects",
    response_model=list[BacklinkProspectPublic],
)
def list_prospects(
    workspace_id: UUID,
    status: ProspectStatus | None = Query(default=None),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[BacklinkProspectPublic]:
    rows = outreach_service.list_prospects(
        db, workspace_id=workspace_id, status=status
    )
    return [BacklinkProspectPublic.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/backlink-prospects",
    response_model=BacklinkProspectPublic,
)
def create_prospect(
    workspace_id: UUID,
    payload: CreateProspectRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> BacklinkProspectPublic:
    prospect = outreach_service.create_prospect(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        domain=payload.domain,
        page_url=payload.page_url,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_role=payload.contact_role,
        relevance_score=payload.relevance_score,
        domain_authority=payload.domain_authority,
        notes=payload.notes,
        request=request,
    )
    return BacklinkProspectPublic.model_validate(prospect)


@router.get(
    "/{workspace_id}/backlink-prospects/{prospect_id}",
    response_model=BacklinkProspectPublic,
)
def get_prospect(
    workspace_id: UUID,
    prospect_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> BacklinkProspectPublic:
    return BacklinkProspectPublic.model_validate(
        outreach_service.get_prospect(
            db, workspace_id=workspace_id, prospect_id=prospect_id
        )
    )


@router.post(
    "/{workspace_id}/backlink-prospects/discover",
    response_model=DiscoveryResultPublic,
)
def discover_prospects(
    workspace_id: UUID,
    payload: DiscoverProspectsRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> DiscoveryResultPublic:
    """Crawl a competitor URL and add the external sites it links to as
    prospects. New domains only — existing prospects are left alone."""

    result = outreach_service.discover_prospects_from_competitor(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        competitor_url=payload.competitor_url,
        max_pages=payload.max_pages,
        max_prospects=payload.max_prospects,
        request=request,
    )
    return DiscoveryResultPublic(
        competitor_url=result.competitor_url,
        pages_crawled=result.pages_crawled,
        prospects_added=result.prospects_added,
        prospects_skipped_duplicate=result.prospects_skipped_duplicate,
        prospects=[BacklinkProspectPublic.model_validate(p) for p in result.prospects],
    )


@router.post(
    "/{workspace_id}/backlink-prospects/bulk",
    response_model=BulkImportResultPublic,
)
def bulk_import(
    workspace_id: UUID,
    payload: BulkImportRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> BulkImportResultPublic:
    """Import a batch of prospects from a CSV-style payload. Per-row errors
    don't abort the batch; the response surfaces what was added vs skipped
    (duplicate or invalid)."""

    result = outreach_service.bulk_import_prospects(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        items=[item.model_dump() for item in payload.items],
        request=request,
    )
    return BulkImportResultPublic(
        added=[BacklinkProspectPublic.model_validate(p) for p in result.added],
        skipped_duplicate=result.skipped_duplicate,
        skipped_invalid=result.skipped_invalid,
    )


@router.patch(
    "/{workspace_id}/backlink-prospects/{prospect_id}",
    response_model=BacklinkProspectPublic,
)
def update_prospect(
    workspace_id: UUID,
    prospect_id: UUID,
    payload: UpdateProspectRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> BacklinkProspectPublic:
    prospect = outreach_service.update_prospect(
        db,
        workspace_id=workspace_id,
        prospect_id=prospect_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        updates=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return BacklinkProspectPublic.model_validate(prospect)


# ------------------------------------------------------------------
# Outreach emails
# ------------------------------------------------------------------


@router.post(
    "/{workspace_id}/backlink-prospects/{prospect_id}/draft-email",
    response_model=OutreachEmailPublic,
)
def draft_email(
    workspace_id: UUID,
    prospect_id: UUID,
    payload: DraftOutreachRequest | None,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> OutreachEmailPublic:
    email = outreach_service.draft_email_for_prospect(
        db,
        workspace_id=workspace_id,
        prospect_id=prospect_id,
        actor_user_id=member.user_id,
        angle=payload.angle if payload else None,
        sender_name=payload.sender_name if payload else None,
        request=request,
    )
    return OutreachEmailPublic.model_validate(email)


@router.get(
    "/{workspace_id}/backlink-prospects/{prospect_id}/emails",
    response_model=list[OutreachEmailPublic],
)
def list_emails(
    workspace_id: UUID,
    prospect_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[OutreachEmailPublic]:
    rows = outreach_service.list_emails_for_prospect(
        db, workspace_id=workspace_id, prospect_id=prospect_id
    )
    return [OutreachEmailPublic.model_validate(r) for r in rows]


@router.get(
    "/{workspace_id}/outreach-emails/{email_id}",
    response_model=OutreachEmailPublic,
)
def get_email(
    workspace_id: UUID,
    email_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> OutreachEmailPublic:
    return OutreachEmailPublic.model_validate(
        outreach_service.get_email(
            db, workspace_id=workspace_id, email_id=email_id
        )
    )


@router.patch(
    "/{workspace_id}/outreach-emails/{email_id}",
    response_model=OutreachEmailPublic,
)
def update_email(
    workspace_id: UUID,
    email_id: UUID,
    payload: UpdateOutreachRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> OutreachEmailPublic:
    email = outreach_service.update_email(
        db,
        workspace_id=workspace_id,
        email_id=email_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        subject=payload.subject,
        body=payload.body,
        request=request,
    )
    return OutreachEmailPublic.model_validate(email)


@router.post(
    "/{workspace_id}/outreach-emails/{email_id}/approve",
    response_model=OutreachEmailPublic,
)
def approve_email(
    workspace_id: UUID,
    email_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> OutreachEmailPublic:
    email = outreach_service.approve_email(
        db,
        workspace_id=workspace_id,
        email_id=email_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return OutreachEmailPublic.model_validate(email)


@router.post(
    "/{workspace_id}/outreach-emails/{email_id}/send",
    response_model=OutreachEmailPublic,
)
def send_email(
    workspace_id: UUID,
    email_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> OutreachEmailPublic:
    # SMTP can take 10+ seconds; offload to a worker when WORKERS_ENABLED=1.
    # The Request object can't cross process boundaries (it carries open
    # sockets), so the task receives None for `request` and audit log entries
    # are written without IP/UA when run async — acceptable trade-off.
    result = run_or_dispatch(
        send_outreach_email_task,
        workspace_id=str(workspace_id),
        email_id=str(email_id),
        actor_user_id=str(member.user_id),
        actor_role=member.role.value,
    )
    data = result.get(timeout=120)
    email = outreach_service.get_email(
        db, workspace_id=workspace_id, email_id=UUID(data["email_id"])
    )
    return OutreachEmailPublic.model_validate(email)


@router.post(
    "/{workspace_id}/outreach-emails/{email_id}/follow-up",
    response_model=OutreachEmailPublic,
)
def draft_followup(
    workspace_id: UUID,
    email_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> OutreachEmailPublic:
    """Draft a follow-up email for a prior SENT outreach. Lands in DRAFT
    status — Admin must still approve before send."""

    email = outreach_service.draft_followup_for_email(
        db,
        workspace_id=workspace_id,
        email_id=email_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return OutreachEmailPublic.model_validate(email)


@router.post(
    "/{workspace_id}/outreach-emails/{email_id}/replied",
    response_model=OutreachEmailPublic,
)
def mark_replied(
    workspace_id: UUID,
    email_id: UUID,
    payload: MarkRepliedRequest | None,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> OutreachEmailPublic:
    email = outreach_service.mark_email_replied(
        db,
        workspace_id=workspace_id,
        email_id=email_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        won=payload.won if payload else False,
        backlink_url=payload.backlink_url if payload else None,
        request=request,
    )
    return OutreachEmailPublic.model_validate(email)


@router.get("/{workspace_id}/backlink-prospects.csv")
def export_prospects_csv(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
):
    from fastapi import Response

    from app.services.csv_export import export_prospects

    body = export_prospects(db, workspace_id=workspace_id)
    return Response(
        content=body,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="prospects.csv"'
        },
    )
