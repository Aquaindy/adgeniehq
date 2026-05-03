"""Inbound email webhooks.

A parse service (Postmark, Sendgrid Inbound Parse, Mailgun Routes) POSTs
parsed messages here. We auth via a shared secret in `X-Inbound-Secret` so a
random caller can't forge replies.

The body is provider-agnostic — we read whichever of `To`/`Subject`/`From`/
`BounceType` are present. The token is pulled from the Reply-To address
`reply+<token>@<INBOUND_EMAIL_DOMAIN>` that we stamped onto the original
outreach email."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.db.session import get_db
from app.services import outreach_service

router = APIRouter()


class InboundConfigError(AdVantaError):
    status_code = 503
    code = "inbound_email_not_configured"


def _verify_secret(provided: str | None) -> None:
    expected = settings.inbound_email_secret
    if not expected:
        # Refuse rather than silently accept anything when the deployment
        # forgot to configure a secret.
        raise InboundConfigError(
            "INBOUND_EMAIL_SECRET is not set; reject all inbound webhooks."
        )
    if not provided or provided != expected:
        raise HTTPException(status_code=401, detail="Invalid inbound secret.")


class InboundResult(BaseModel):
    matched: bool
    outreach_email_id: str | None = None
    is_bounce: bool | None = None
    reason: str | None = None


@router.post("/email", response_model=InboundResult)
async def inbound_email(
    request: Request,
    db: Session = Depends(get_db),
    x_inbound_secret: str | None = Header(default=None, alias="X-Inbound-Secret"),
) -> InboundResult:
    _verify_secret(x_inbound_secret)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object.")
    result = outreach_service.handle_inbound_email(
        db, payload=payload, request=request
    )
    return InboundResult(**result)
