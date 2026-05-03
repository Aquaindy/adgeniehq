"""BYOK provider credentials service.

Stores third-party API keys (OpenAI, Anthropic, Google AI) that the
workspace wants AdVanta to use *on its behalf* for LLM calls. Plaintext
is encrypted via Fernet at rest (same primitive as OAuth tokens) and is
never returned to the frontend.

A single active credential per (workspace, provider) is enforced by a
partial-unique index. Adding a new key for a provider that already has
one revokes the prior row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.audit_log import AuditActorType
from app.models.provider_credential import (
    ProviderCredential,
    ProviderCredentialProvider,
    ProviderCredentialTestStatus,
)
from app.security.encryption import decrypt, encrypt
from app.security.permissions import Role, require_role_at_least
from app.services import audit_service


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProviderCredentialNotFoundError(AdVantaError):
    status_code = 404
    code = "provider_credential_not_found"


class ProviderCredentialInvalidError(AdVantaError):
    status_code = 400
    code = "provider_credential_invalid"


class ProviderCredentialAlreadyRevokedError(AdVantaError):
    status_code = 409
    code = "provider_credential_already_revoked"


# ---------------------------------------------------------------------------
# Provider registry — one place to look up display name + test endpoint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: ProviderCredentialProvider
    display_name: str
    docs_url: str
    secret_hint: str  # short instruction shown in the UI


PROVIDER_SPECS: dict[ProviderCredentialProvider, ProviderSpec] = {
    ProviderCredentialProvider.OPENAI: ProviderSpec(
        provider_id=ProviderCredentialProvider.OPENAI,
        display_name="OpenAI",
        docs_url="https://platform.openai.com/api-keys",
        secret_hint="Starts with `sk-…`",
    ),
    ProviderCredentialProvider.ANTHROPIC: ProviderSpec(
        provider_id=ProviderCredentialProvider.ANTHROPIC,
        display_name="Anthropic",
        docs_url="https://console.anthropic.com/settings/keys",
        secret_hint="Starts with `sk-ant-…`",
    ),
    ProviderCredentialProvider.GOOGLE_AI: ProviderSpec(
        provider_id=ProviderCredentialProvider.GOOGLE_AI,
        display_name="Google AI (Gemini)",
        docs_url="https://aistudio.google.com/app/apikey",
        secret_hint="From Google AI Studio",
    ),
}


def list_provider_specs() -> list[ProviderSpec]:
    return list(PROVIDER_SPECS.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_credentials(
    db: Session, *, workspace_id: UUID, include_revoked: bool = False
) -> list[ProviderCredential]:
    q = db.query(ProviderCredential).filter(
        ProviderCredential.workspace_id == workspace_id
    )
    if not include_revoked:
        q = q.filter(ProviderCredential.revoked_at.is_(None))
    return q.order_by(ProviderCredential.created_at.desc()).all()


def add_credential(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    provider: ProviderCredentialProvider,
    secret: str,
    label: str | None = None,
) -> ProviderCredential:
    """Encrypt + store. Revokes any existing active credential for the same
    provider on this workspace first (one active per provider rule)."""

    require_role_at_least(actor_role, Role.ADMIN)
    secret = (secret or "").strip()
    if len(secret) < 12:
        raise ProviderCredentialInvalidError(
            "Secret looks too short to be a valid API key.",
        )

    # Revoke any existing active credential for this provider — keeps the
    # partial-unique index satisfied without a separate update path.
    existing = (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.workspace_id == workspace_id,
            ProviderCredential.provider == provider,
            ProviderCredential.revoked_at.is_(None),
        )
        .first()
    )
    if existing is not None:
        existing.revoked_at = datetime.now(timezone.utc)
        existing.revoked_by = actor_user_id
        db.flush()

    cred = ProviderCredential(
        workspace_id=workspace_id,
        created_by=actor_user_id,
        provider=provider,
        label=(label.strip()[:120] if label else None),
        encrypted_secret=encrypt(secret),
        last_four=secret[-4:],
    )
    db.add(cred)
    db.flush()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="provider_credential.added",
        resource_type="provider_credential",
        resource_id=cred.id,
        metadata={"provider": provider.value, "label": cred.label},
    )
    db.commit()
    db.refresh(cred)
    return cred


def revoke_credential(
    db: Session,
    *,
    workspace_id: UUID,
    credential_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
) -> ProviderCredential:
    require_role_at_least(actor_role, Role.ADMIN)
    cred = (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.id == credential_id,
            ProviderCredential.workspace_id == workspace_id,
        )
        .first()
    )
    if cred is None:
        raise ProviderCredentialNotFoundError("Credential not found.")
    if cred.revoked_at is not None:
        raise ProviderCredentialAlreadyRevokedError("Credential already revoked.")

    cred.revoked_at = datetime.now(timezone.utc)
    cred.revoked_by = actor_user_id

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="provider_credential.revoked",
        resource_type="provider_credential",
        resource_id=cred.id,
        metadata={"provider": cred.provider.value},
    )
    db.commit()
    db.refresh(cred)
    return cred


def test_credential(
    db: Session,
    *,
    workspace_id: UUID,
    credential_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
) -> ProviderCredential:
    """Hit a cheap provider endpoint to validate the key. Persists the
    result on the row so the UI can show "last tested 2 min ago — OK"."""

    require_role_at_least(actor_role, Role.ADMIN)
    cred = (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.id == credential_id,
            ProviderCredential.workspace_id == workspace_id,
            ProviderCredential.revoked_at.is_(None),
        )
        .first()
    )
    if cred is None:
        raise ProviderCredentialNotFoundError(
            "Credential not found or already revoked.",
        )

    plaintext = decrypt(cred.encrypted_secret)
    ok, error = _ping_provider(cred.provider, plaintext)

    cred.last_tested_at = datetime.now(timezone.utc)
    cred.last_test_status = (
        ProviderCredentialTestStatus.OK if ok else ProviderCredentialTestStatus.FAILED
    )
    cred.last_test_error = None if ok else (error or "unknown error")[:500]

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="provider_credential.tested",
        resource_type="provider_credential",
        resource_id=cred.id,
        metadata={
            "provider": cred.provider.value,
            "status": cred.last_test_status.value,
        },
    )
    db.commit()
    db.refresh(cred)
    return cred


def get_secret_or_none(
    db: Session,
    *,
    workspace_id: UUID,
    provider: ProviderCredentialProvider,
) -> str | None:
    """Decrypt the active secret for this workspace+provider, if any."""
    cred = (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.workspace_id == workspace_id,
            ProviderCredential.provider == provider,
            ProviderCredential.revoked_at.is_(None),
        )
        .first()
    )
    if cred is None:
        return None
    return decrypt(cred.encrypted_secret)


def get_active_credentials(
    db: Session, *, workspace_id: UUID
) -> list[ProviderCredential]:
    return (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.workspace_id == workspace_id,
            ProviderCredential.revoked_at.is_(None),
        )
        .order_by(ProviderCredential.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Provider ping (cheap validation calls)
# ---------------------------------------------------------------------------


def _ping_provider(
    provider: ProviderCredentialProvider, secret: str
) -> tuple[bool, str | None]:
    """Hit a low-cost endpoint per provider. Returns (ok, error_message)."""
    try:
        if provider == ProviderCredentialProvider.OPENAI:
            r = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {secret}"},
                timeout=15.0,
            )
            return _interpret_http(r)
        if provider == ProviderCredentialProvider.ANTHROPIC:
            # The /v1/models endpoint is the cheapest authenticated read.
            r = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": secret,
                    "anthropic-version": "2023-06-01",
                },
                timeout=15.0,
            )
            return _interpret_http(r)
        if provider == ProviderCredentialProvider.GOOGLE_AI:
            # Google AI Studio uses a query-string key.
            r = httpx.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": secret},
                timeout=15.0,
            )
            return _interpret_http(r)
    except httpx.HTTPError as exc:
        return False, f"network error: {exc}"
    return False, "unsupported provider"


def _interpret_http(r: httpx.Response) -> tuple[bool, str | None]:
    if r.status_code < 300:
        return True, None
    if r.status_code in (401, 403):
        return False, "authentication failed (key rejected)"
    return False, f"HTTP {r.status_code}: {r.text[:200]}"


# Hook used by tests to inspect / monkeypatch which providers were pinged.
def _get_provider_specs() -> Iterable[ProviderSpec]:  # pragma: no cover
    return list_provider_specs()
