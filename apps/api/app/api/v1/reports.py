from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.models.workspace_member import WorkspaceMember
from app.schemas.reports import ReportDetail, ReportGenerateRequest, ReportSummary
from app.security.dependencies import get_current_member, require_role
from app.security.permissions import Role
from app.services import report_service
from app.services.email_service import build_report_email_body, send_email
from app.services.report_renderer import render_csv, render_pdf

router = APIRouter()


class ReportNotFoundError(AdVantaError):
    status_code = 404
    code = "report_not_found"


class UnsupportedFormatError(AdVantaError):
    status_code = 400
    code = "unsupported_format"


@router.get("/{workspace_id}/reports", response_model=list[ReportSummary])
def list_reports_endpoint(
    workspace_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[ReportSummary]:
    rows = report_service.list_reports(db, workspace_id=workspace_id)
    return [ReportSummary.model_validate(r) for r in rows]


@router.post(
    "/{workspace_id}/reports/generate",
    response_model=ReportDetail,
    status_code=status.HTTP_201_CREATED,
)
def generate_report_endpoint(
    workspace_id: UUID,
    payload: ReportGenerateRequest,
    member: WorkspaceMember = Depends(require_role(Role.MARKETER)),
    db: Session = Depends(get_db),
) -> ReportDetail:
    report = report_service.generate_report(
        db,
        workspace_id=workspace_id,
        period=payload.period,
        actor_user_id=member.user_id,
    )

    if payload.email_to and report.payload:
        draft = build_report_email_body(report.payload, title=report.title)
        if send_email(to=payload.email_to, draft=draft):
            report.email_sent_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(report)

    return ReportDetail.model_validate(report)


@router.get(
    "/{workspace_id}/reports/{report_id}",
    response_model=ReportDetail,
)
def get_report_endpoint(
    workspace_id: UUID,
    report_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> ReportDetail:
    report = report_service.get_report(
        db, workspace_id=workspace_id, report_id=report_id
    )
    if report is None:
        raise ReportNotFoundError("Report not found in this workspace.")
    return ReportDetail.model_validate(report)


@router.get("/{workspace_id}/reports/{report_id}/download")
def download_report(
    workspace_id: UUID,
    report_id: UUID,
    fmt: str = Query(default="pdf", alias="format"),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> Response:
    report = report_service.get_report(
        db, workspace_id=workspace_id, report_id=report_id
    )
    if report is None:
        raise ReportNotFoundError("Report not found in this workspace.")

    # Content-Disposition headers are latin-1 only — strip everything else.
    raw_title = report.title.replace(" ", "_").replace("/", "-")
    safe_title = raw_title.encode("ascii", errors="ignore").decode("ascii")[:80] or "report"
    if fmt.lower() == "pdf":
        body = render_pdf(report.payload, title=report.title)
        return Response(
            content=body,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_title}.pdf"'
            },
        )
    if fmt.lower() == "csv":
        body = render_csv(report.payload)
        return Response(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_title}.csv"'
            },
        )
    raise UnsupportedFormatError("Use ?format=pdf or ?format=csv.")
