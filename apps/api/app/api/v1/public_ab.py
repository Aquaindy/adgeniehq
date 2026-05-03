"""Public traffic-split endpoints — called by the customer's site, not by an
authenticated AdVanta user.

Both routes set permissive CORS headers so a `<script>` snippet running on any
domain can hit them. They are the *only* endpoints in this codebase that
accept anonymous traffic; everything else is workspace-scoped + JWT-gated.

The test_id in the URL is a UUID and provides enough obscurity to prevent
casual abuse; rate-limiting is applied via the same global middleware that
guards the rest of /api/v1."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import ab_test_service

router = APIRouter()


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "600",
}


def _add_cors(response: Response) -> None:
    for k, v in CORS_HEADERS.items():
        response.headers.setdefault(k, v)


class AssignRequest(BaseModel):
    visitor_id: str = Field(min_length=1, max_length=64)


class AssignResponse(BaseModel):
    test_id: UUID
    variant_id: UUID
    variant_name: str
    is_control: bool
    payload: dict


class ConvertRequest(BaseModel):
    visitor_id: str = Field(min_length=1, max_length=64)
    value_cents: int | None = Field(default=None, ge=0)
    metadata: dict | None = None


class ConvertResponse(BaseModel):
    ok: bool


# ---------------------------------------------------------------------------
# Preflight — both endpoints share one OPTIONS handler.
# ---------------------------------------------------------------------------


@router.options("/ab-tests/{test_id}/assign")
@router.options("/ab-tests/{test_id}/convert")
def preflight(test_id: UUID, response: Response) -> Response:  # noqa: ARG001 — test_id only used for routing
    _add_cors(response)
    return Response(status_code=204, headers=dict(response.headers))


# ---------------------------------------------------------------------------
# Assign
# ---------------------------------------------------------------------------


@router.post("/ab-tests/{test_id}/assign", response_model=AssignResponse)
def assign(
    test_id: UUID,
    payload: AssignRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AssignResponse:
    _add_cors(response)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    test, variant = ab_test_service.assign_visitor(
        db,
        test_id=test_id,
        visitor_id=payload.visitor_id,
        ip_address=ip,
        user_agent=user_agent,
    )
    return AssignResponse(
        test_id=test.id,
        variant_id=variant.id,
        variant_name=variant.name,
        is_control=variant.is_control,
        payload=variant.payload or {},
    )


@router.post("/ab-tests/{test_id}/convert", response_model=ConvertResponse)
def convert(
    test_id: UUID,
    payload: ConvertRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> ConvertResponse:
    _add_cors(response)
    ab_test_service.record_conversion(
        db,
        test_id=test_id,
        visitor_id=payload.visitor_id,
        value_cents=payload.value_cents,
        metadata=payload.metadata,
    )
    return ConvertResponse(ok=True)
