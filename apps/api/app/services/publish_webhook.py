"""Workspace-level CMS publish hook.

A workspace can configure a `publish_webhook_url` + `publish_webhook_secret`.
When an Admin publishes an approved content draft, we POST the draft to that
URL with the secret in `Authorization: Bearer …`. The receiver returns
`{"published_url": "https://…"}`, which we record on the draft.

This keeps the integration generic: WordPress, Webflow, Ghost, Contentful,
Zapier/Make, or a custom server-side adapter all just need to implement the
same JSON contract.

The contract is documented in `docs/cms-publish-webhook.md`."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.models.content_draft import ContentDraft
from app.models.workspace import Workspace
from app.security.encryption import decrypt

log = get_logger(__name__)


class PublishWebhookError(AdVantaError):
    status_code = 502
    code = "publish_webhook_failed"


class PublishWebhookNotConfiguredError(AdVantaError):
    status_code = 409
    code = "publish_webhook_not_configured"


@dataclass
class PublishResult:
    published_url: str | None
    response_body: dict | None


def is_configured(workspace: Workspace) -> bool:
    return bool(workspace.publish_webhook_url)


def push_to_webhook(*, workspace: Workspace, draft: ContentDraft) -> PublishResult:
    """POST the draft to the workspace's configured webhook. Returns the
    `published_url` the receiver reports (may be None if the receiver does
    a write but doesn't expose the published URL — we still mark the draft
    as published in that case)."""

    if not workspace.publish_webhook_url:
        raise PublishWebhookNotConfiguredError(
            "This workspace has no publish_webhook_url configured."
        )

    headers = {"Content-Type": "application/json"}
    if workspace.encrypted_publish_webhook_secret:
        try:
            secret = decrypt(workspace.encrypted_publish_webhook_secret)
        except Exception as exc:  # pragma: no cover — defensive
            raise PublishWebhookError(
                f"Could not decrypt publish webhook secret: {exc}"
            ) from exc
        headers["Authorization"] = f"Bearer {secret}"

    payload = {
        "draft_id": str(draft.id),
        "workspace_id": str(draft.workspace_id),
        "type": draft.type.value,
        "title": draft.title,
        "body": draft.body,
        "target_url": draft.target_url,
        "keywords": draft.keywords or [],
        "seo_metadata": draft.seo_metadata or {},
        "notes": draft.notes,
        "model_used": draft.model_used,
        "source": draft.source,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    }

    try:
        response = httpx.post(
            workspace.publish_webhook_url,
            headers=headers,
            json=payload,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        log.warning(
            "publish_webhook.http_error",
            workspace_id=str(workspace.id),
            error=str(exc),
        )
        raise PublishWebhookError(f"Webhook request failed: {exc}") from exc

    if response.status_code >= 400:
        body_preview = (response.text or "")[:200]
        log.warning(
            "publish_webhook.bad_status",
            workspace_id=str(workspace.id),
            status=response.status_code,
            body=body_preview,
        )
        raise PublishWebhookError(
            f"Webhook returned HTTP {response.status_code}: {body_preview}"
        )

    body: dict | None = None
    if response.content:
        try:
            body = response.json()
        except ValueError:
            body = None

    published_url = None
    if isinstance(body, dict):
        candidate = body.get("published_url") or body.get("url")
        if isinstance(candidate, str) and candidate.strip():
            published_url = candidate.strip()

    log.info(
        "publish_webhook.delivered",
        workspace_id=str(workspace.id),
        draft_id=str(draft.id),
        published_url=published_url,
    )
    return PublishResult(published_url=published_url, response_body=body)
