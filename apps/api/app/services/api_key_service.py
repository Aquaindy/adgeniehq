"""API key minting + verification.

Wire format: `ak_<prefix>.<secret>` where:
- prefix: 8 base32 chars, stored on the row for O(1) lookup
- secret: 32 base64url chars, SHA-256 hashed at rest

The plaintext key is returned exactly once at create time. Rotating means
revoking + creating a new key.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.models.api_key import ApiKey
from app.models.audit_log import AuditActorType
from app.security.permissions import Role, require_role_at_least
from app.services import audit_service


_PREFIX_LEN = 8
_SECRET_BYTES = 24  # 32 chars base64url


class ApiKeyNotFoundError(AdVantaError):
    status_code = 404
    code = "api_key_not_found"


class ApiKeyAlreadyRevokedError(AdVantaError):
    status_code = 409
    code = "api_key_already_revoked"


def create_key(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    label: str,
    role: Role = Role.MARKETER,
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    """Mint a new API key. Returns (row, plaintext)."""
    require_role_at_least(actor_role, Role.OWNER)

    prefix = _gen_prefix(db)
    secret = _gen_secret()
    plaintext = f"ak_{prefix}.{secret}"
    secret_hash = _hash_secret(secret)

    key = ApiKey(
        workspace_id=workspace_id,
        created_by=actor_user_id,
        label=label.strip()[:120] or "untitled",
        prefix=prefix,
        secret_hash=secret_hash,
        role=role,
        expires_at=expires_at,
    )
    db.add(key)
    db.flush()

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="api_key.created",
        resource_type="api_key",
        resource_id=key.id,
        metadata={"label": key.label, "role": key.role.value},
    )
    db.commit()
    db.refresh(key)
    return key, plaintext


def list_keys(db: Session, *, workspace_id: UUID) -> list[ApiKey]:
    return (
        db.query(ApiKey)
        .filter(ApiKey.workspace_id == workspace_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


def revoke_key(
    db: Session,
    *,
    workspace_id: UUID,
    key_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
) -> ApiKey:
    require_role_at_least(actor_role, Role.OWNER)
    key = (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.workspace_id == workspace_id)
        .first()
    )
    if key is None:
        raise ApiKeyNotFoundError("API key not found.")
    if key.revoked_at is not None:
        raise ApiKeyAlreadyRevokedError("Key is already revoked.")
    key.revoked_at = datetime.now(timezone.utc)
    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="api_key.revoked",
        resource_type="api_key",
        resource_id=key.id,
        metadata={"label": key.label},
    )
    db.commit()
    db.refresh(key)
    return key


def verify_plaintext(db: Session, *, plaintext: str) -> ApiKey | None:
    """Lookup the key row matching `ak_<prefix>.<secret>`. Returns None for
    missing/revoked/expired keys. On success, bumps `last_used_at`."""
    if not plaintext or not plaintext.startswith("ak_"):
        return None
    try:
        prefix_part, secret = plaintext[3:].split(".", 1)
    except ValueError:
        return None
    if len(prefix_part) != _PREFIX_LEN or not secret:
        return None

    key = (
        db.query(ApiKey)
        .filter(ApiKey.prefix == prefix_part)
        .first()
    )
    if key is None or key.revoked_at is not None:
        return None
    if key.expires_at is not None and key.expires_at < datetime.now(timezone.utc):
        return None

    if not secrets.compare_digest(key.secret_hash, _hash_secret(secret)):
        return None

    key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(key)
    return key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gen_prefix(db: Session) -> str:
    """Random 8-char base32 prefix that doesn't collide with an existing one."""
    for _ in range(8):
        candidate = (
            base64.b32encode(secrets.token_bytes(5))
            .decode("ascii")
            .rstrip("=")[:_PREFIX_LEN]
            .lower()
        )
        if not db.query(ApiKey.id).filter(ApiKey.prefix == candidate).first():
            return candidate
    raise RuntimeError("Could not generate a unique API-key prefix; retry.")


def _gen_secret() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(_SECRET_BYTES)).decode(
        "ascii"
    ).rstrip("=")


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()
