from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.report import ReportPeriod, ReportStatus


class ReportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    title: str
    period: ReportPeriod
    period_start: datetime
    period_end: datetime
    status: ReportStatus
    error_message: str | None
    email_sent_at: datetime | None
    created_at: datetime


class ReportDetail(ReportSummary):
    payload: dict


class ReportGenerateRequest(BaseModel):
    period: ReportPeriod
    email_to: EmailStr | None = None
