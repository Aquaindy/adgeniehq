"""CSV export helpers.

The functions return raw CSV bytes (UTF-8, BOM-prefixed so Excel renders
non-ASCII correctly). Used by the per-resource export endpoints.

Every column listed below corresponds to a real attribute on the underlying
SQLAlchemy model OR a documented derived value (e.g. `word_count` from body).
Tests in `tests/test_csv_export.py` pin the contract.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session


_BOM = b"\xef\xbb\xbf"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bool):
        # `bool` is a subclass of `int`; check first so we don't fall through.
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return "; ".join(_stringify(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}={_stringify(v)}" for k, v in value.items())
    if hasattr(value, "value") and not isinstance(value, (int, float)):
        # StrEnum / IntEnum
        return str(value.value)
    return str(value)


def _to_csv(rows: Iterable[dict[str, Any]], columns: list[str]) -> bytes:
    """Render rows under `columns` (in order) into BOM-prefixed CSV bytes."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_stringify(row.get(c)) for c in columns])
    return _BOM + buffer.getvalue().encode("utf-8")


def export_prospects(db: Session, *, workspace_id: UUID) -> bytes:
    """Backlink-prospect CSV. Columns map 1:1 onto BacklinkProspect attributes
    so a downstream BI tool can re-import without remapping."""
    from app.models.backlink_prospect import BacklinkProspect

    rows = (
        db.query(BacklinkProspect)
        .filter(BacklinkProspect.workspace_id == workspace_id)
        .order_by(BacklinkProspect.created_at.desc())
        .all()
    )
    columns = [
        "id",
        "domain",
        "page_url",
        "contact_name",
        "contact_email",
        "contact_role",
        "relevance_score",
        "domain_authority",
        "status",
        "source",
        "notes",
        "last_contacted_at",
        "won_at",
        "backlink_url",
        "created_at",
    ]
    return _to_csv(
        ({c: getattr(p, c, None) for c in columns} for p in rows),
        columns,
    )


def export_content_drafts(db: Session, *, workspace_id: UUID) -> bytes:
    """Content-draft CSV. `keywords` is JSONB and serialized as `a; b; c`.
    `word_count` is derived from `body` because we don't store it."""
    from app.models.content_draft import ContentDraft

    rows = (
        db.query(ContentDraft)
        .filter(ContentDraft.workspace_id == workspace_id)
        .order_by(ContentDraft.created_at.desc())
        .all()
    )
    columns = [
        "id",
        "type",
        "status",
        "title",
        "target_url",
        "keywords",
        "word_count",
        "source",
        "model_used",
        "approved_at",
        "published_at",
        "created_at",
    ]

    def _row(d: ContentDraft) -> dict[str, Any]:
        body = d.body or ""
        # Naive word count is fine for an export — splitting on whitespace
        # matches what most CMSes report. Strip trailing whitespace tokens.
        word_count = sum(1 for tok in body.split() if tok)
        return {
            "id": d.id,
            "type": d.type,
            "status": d.status,
            "title": d.title,
            "target_url": d.target_url,
            "keywords": d.keywords or [],
            "word_count": word_count,
            "source": d.source,
            "model_used": d.model_used,
            "approved_at": d.approved_at,
            "published_at": d.published_at,
            "created_at": d.created_at,
        }

    return _to_csv((_row(d) for d in rows), columns)


def export_executions(db: Session, *, workspace_id: UUID) -> bytes:
    """Recommendation-execution CSV. Auditors review these to reconcile what
    was actually written to provider platforms."""
    from app.models.recommendation_execution import RecommendationExecution

    rows = (
        db.query(RecommendationExecution)
        .filter(RecommendationExecution.workspace_id == workspace_id)
        .order_by(RecommendationExecution.created_at.desc())
        .all()
    )
    columns = [
        "id",
        "recommendation_id",
        "provider",
        "action_type",
        "status",
        "is_revert",
        "target_external_id",
        "target_external_account_id",
        "error_message",
        "executed_by",
        "executed_at",
        "created_at",
    ]
    return _to_csv(
        ({c: getattr(e, c, None) for c in columns} for e in rows),
        columns,
    )
