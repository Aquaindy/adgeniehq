from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.integrations.base import (
    BaseProvider,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderTokens,
)
from app.integrations.registry import get_provider, list_providers
from app.models.audit_log import AuditActorType
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.oauth_token import OAuthToken
from app.models.sync_log import SyncLog, SyncLogStatus
from app.schemas.integrations import (
    ConnectUrlResponse,
    IntegrationStatus,
    SyncLogPublic,
)
from app.security.encryption import decrypt, encrypt
from app.security.oauth_state import issue_state, parse_state
from app.services import audit_service

log = get_logger(__name__)


class AccountNotConnectedError(AdVantaError):
    status_code = 409
    code = "account_not_connected"


class TokenRefreshFailedError(AdVantaError):
    """Raised when a stored refresh_token can no longer mint a fresh access
    token — typically because the user revoked access at the provider. Surface
    as 401 so the UI redirects the user to reconnect."""

    status_code = 401
    code = "token_refresh_failed"


# Refresh slightly before the actual expiry so an in-flight provider call
# doesn't race the clock.
_REFRESH_BUFFER = timedelta(seconds=60)


def get_fresh_access_token(
    db: Session, *, account: ConnectedAccount
) -> str:
    """Decrypt and return the access token for `account`, refreshing it first
    if it has expired (or is within `_REFRESH_BUFFER` of expiring).

    The caller must have already verified the account is `CONNECTED` and has a
    token row attached. On a successful refresh, the encrypted access token,
    optional new refresh token, and expiry are persisted in the same session.

    If refresh fails (network or provider error), the account is flipped to
    `ERROR` with a user-readable `last_error` so the next render of the
    integrations page prompts the user to reconnect."""

    token = account.token
    if token is None:
        raise AccountNotConnectedError(
            f"{account.provider} has no token stored for this workspace."
        )

    needs_refresh = (
        token.expires_at is not None
        and token.expires_at - datetime.now(timezone.utc) <= _REFRESH_BUFFER
    )
    if not needs_refresh:
        return decrypt(token.encrypted_access_token)

    if token.encrypted_refresh_token is None:
        # Provider didn't issue a refresh token (e.g. some long-lived LinkedIn
        # tokens). Hand back what we have and let the provider call fail
        # clearly if it is in fact expired.
        log.info(
            "token.refresh.no_refresh_token",
            provider=account.provider,
            account_id=str(account.id),
        )
        return decrypt(token.encrypted_access_token)

    refresh_token = decrypt(token.encrypted_refresh_token)
    provider_cls = get_provider(account.provider)
    try:
        new_tokens: ProviderTokens = provider_cls.refresh_access_token(
            refresh_token=refresh_token
        )
    except (ProviderError, ProviderNotConfiguredError) as exc:
        log.warning(
            "token.refresh.failed",
            provider=account.provider,
            account_id=str(account.id),
            error=str(exc),
        )
        account.status = ConnectionStatus.ERROR
        account.last_error = f"Token refresh failed: {exc}"
        db.commit()
        raise TokenRefreshFailedError(
            f"{account.provider} token refresh failed; reconnect the integration "
            "from Integrations → Reconnect."
        ) from exc

    token.encrypted_access_token = encrypt(new_tokens.access_token)
    # Some providers (e.g., Google) return a new refresh_token only on first
    # consent; subsequent refreshes omit it. Keep the existing one in that case.
    if new_tokens.refresh_token:
        token.encrypted_refresh_token = encrypt(new_tokens.refresh_token)
    token.expires_at = new_tokens.expires_at
    if new_tokens.scopes:
        token.scopes = new_tokens.scopes
    # Clear any stale ERROR status from a previous failed refresh.
    if account.status == ConnectionStatus.ERROR:
        account.status = ConnectionStatus.CONNECTED
        account.last_error = None
    db.commit()

    log.info(
        "token.refreshed",
        provider=account.provider,
        account_id=str(account.id),
    )
    return new_tokens.access_token


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_integrations_for_workspace(
    db: Session, *, workspace_id: UUID
) -> list[IntegrationStatus]:
    accounts: dict[str, ConnectedAccount] = {
        a.provider: a
        for a in db.query(ConnectedAccount)
        .filter(ConnectedAccount.workspace_id == workspace_id)
        .all()
    }

    out: list[IntegrationStatus] = []
    for provider in list_providers():
        account = accounts.get(provider.provider_id)
        recent_syncs: list[SyncLogPublic] = []
        if account:
            recent = (
                db.query(SyncLog)
                .filter(SyncLog.connected_account_id == account.id)
                .order_by(SyncLog.created_at.desc())
                .limit(5)
                .all()
            )
            recent_syncs = [SyncLogPublic.model_validate(s) for s in recent]

        out.append(
            IntegrationStatus(
                provider=provider.provider_id,
                display_name=provider.display_name,
                description=provider.description,
                configured=provider.is_configured(),
                status=account.status if account else ConnectionStatus.DISCONNECTED,
                provider_account_id=account.provider_account_id if account else None,
                display_account_name=account.display_name if account else None,
                scopes=account.scopes if account else None,
                connected_at=account.connected_at if account else None,
                last_sync_at=account.last_sync_at if account else None,
                last_error=account.last_error if account else None,
                recent_syncs=recent_syncs,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Connect URL
# ---------------------------------------------------------------------------


def build_connect_url(
    *, workspace_id: UUID, user_id: UUID, provider_id: str
) -> ConnectUrlResponse:
    provider = get_provider(provider_id)
    state = issue_state(workspace_id=workspace_id, user_id=user_id, provider=provider_id)
    return ConnectUrlResponse(
        authorization_url=provider.build_authorization_url(state=state),
        state=state,
        redirect_uri=provider.callback_url(),
    )


# ---------------------------------------------------------------------------
# Callback — runs without a workspace_id in the URL; resolves it from `state`.
# ---------------------------------------------------------------------------


def handle_oauth_callback(
    db: Session,
    *,
    provider_id: str,
    code: str | None,
    state_token: str | None,
    error: str | None,
    request: Request | None = None,
) -> tuple[UUID, str, ConnectionStatus, str | None]:
    """Returns (workspace_id, provider_id, status, error_message). The router
    uses this to build a redirect URL back to the frontend."""

    if not state_token:
        raise ProviderError("OAuth callback missing state.")
    payload = parse_state(state_token)

    workspace_id = UUID(payload["ws"])
    user_id = UUID(payload["uid"])
    if payload["p"] != provider_id:
        raise ProviderError("OAuth state was issued for a different provider.")

    if error or not code:
        message = error or "OAuth flow returned no authorization code."
        _record_failure(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            provider_id=provider_id,
            message=message,
            request=request,
        )
        return workspace_id, provider_id, ConnectionStatus.ERROR, message

    provider_cls = get_provider(provider_id)
    try:
        tokens = provider_cls.exchange_code(code=code)
    except (ProviderError, ProviderNotConfiguredError) as exc:
        _record_failure(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            provider_id=provider_id,
            message=str(exc),
            request=request,
        )
        return workspace_id, provider_id, ConnectionStatus.ERROR, str(exc)

    account_info = None
    try:
        account_info = provider_cls.fetch_account_info(access_token=tokens.access_token)
    except ProviderError as exc:
        log.warning("integration.account_info.failed", provider=provider_id, error=str(exc))

    account = _upsert_account(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        provider_id=provider_id,
        tokens=tokens,
        provider_account_id=account_info.provider_account_id if account_info else None,
        display_name=account_info.display_name if account_info else None,
    )

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action="integration.connected",
        resource_type="connected_account",
        resource_id=account.id,
        metadata={"provider": provider_id, "scopes": tokens.scopes},
        request=request,
    )

    db.commit()
    return workspace_id, provider_id, ConnectionStatus.CONNECTED, None


def _record_failure(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    provider_id: str,
    message: str,
    request: Request | None,
) -> None:
    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == provider_id,
        )
        .first()
    )
    if account is None:
        account = ConnectedAccount(
            workspace_id=workspace_id,
            provider=provider_id,
            status=ConnectionStatus.ERROR,
            connected_by=user_id,
            last_error=message,
        )
        db.add(account)
        db.flush()
    else:
        account.status = ConnectionStatus.ERROR
        account.last_error = message

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action="integration.connect_failed",
        resource_type="connected_account",
        resource_id=account.id,
        metadata={"provider": provider_id, "error": message},
        request=request,
    )
    db.commit()


def _upsert_account(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    provider_id: str,
    tokens: ProviderTokens,
    provider_account_id: str | None,
    display_name: str | None,
) -> ConnectedAccount:
    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == provider_id,
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if account is None:
        account = ConnectedAccount(workspace_id=workspace_id, provider=provider_id)
        db.add(account)
        db.flush()

    account.status = ConnectionStatus.CONNECTED
    account.scopes = tokens.scopes or get_provider(provider_id).scopes
    account.connected_by = user_id
    account.connected_at = now
    account.last_error = None
    if provider_account_id:
        account.provider_account_id = provider_account_id
    if display_name:
        account.display_name = display_name

    encrypted_access = encrypt(tokens.access_token)
    encrypted_refresh = encrypt(tokens.refresh_token) if tokens.refresh_token else None

    if account.token is None:
        account.token = OAuthToken(
            connected_account_id=account.id,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            expires_at=tokens.expires_at,
            scopes=tokens.scopes,
        )
    else:
        account.token.encrypted_access_token = encrypted_access
        if encrypted_refresh:
            account.token.encrypted_refresh_token = encrypted_refresh
        account.token.expires_at = tokens.expires_at
        account.token.scopes = tokens.scopes

    db.flush()
    return account


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


def disconnect(
    db: Session,
    *,
    workspace_id: UUID,
    provider_id: str,
    user_id: UUID,
    request: Request | None = None,
) -> ConnectedAccount:
    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == provider_id,
        )
        .first()
    )
    if account is None:
        raise AccountNotConnectedError(f"{provider_id} is not connected for this workspace.")

    # Drop the encrypted tokens entirely. Keep the ConnectedAccount row so we
    # retain connect/disconnect history for audit purposes.
    if account.token is not None:
        db.delete(account.token)
        account.token = None

    account.status = ConnectionStatus.DISCONNECTED
    account.last_error = None

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action="integration.disconnected",
        resource_type="connected_account",
        resource_id=account.id,
        metadata={"provider": provider_id},
        request=request,
    )

    db.commit()
    db.refresh(account)
    return account


# ---------------------------------------------------------------------------
# Sync — for M6 this just verifies the token still works and records a log
# entry. Real platform-data sync (campaigns, etc.) lands in M7+.
# ---------------------------------------------------------------------------


def trigger_sync(
    db: Session,
    *,
    workspace_id: UUID,
    provider_id: str,
    user_id: UUID,
    request: Request | None = None,
) -> SyncLog:
    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == provider_id,
        )
        .first()
    )
    if account is None or account.status != ConnectionStatus.CONNECTED or account.token is None:
        raise AccountNotConnectedError(f"{provider_id} is not connected for this workspace.")

    started_at = datetime.now(timezone.utc)
    sync_log = SyncLog(
        connected_account_id=account.id,
        status=SyncLogStatus.RUNNING,
        started_at=started_at,
    )
    db.add(sync_log)
    db.commit()
    db.refresh(sync_log)

    provider_cls = get_provider(provider_id)
    try:
        access_token = get_fresh_access_token(db, account=account)
        info = provider_cls.fetch_account_info(access_token=access_token)
        sync_log.status = SyncLogStatus.SUCCEEDED
        sync_log.completed_at = datetime.now(timezone.utc)
        sync_log.summary = {
            "verified_account": info.provider_account_id,
            "display_name": info.display_name,
            "milestone": "M6 — connection verification only; data sync lands in M7+",
        }
        account.last_sync_at = sync_log.completed_at
        account.last_error = None
        if info.display_name and not account.display_name:
            account.display_name = info.display_name
        if info.provider_account_id and not account.provider_account_id:
            account.provider_account_id = info.provider_account_id
    except Exception as exc:
        sync_log.status = SyncLogStatus.FAILED
        sync_log.completed_at = datetime.now(timezone.utc)
        sync_log.error_message = str(exc)
        account.last_error = str(exc)

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=user_id,
        action="integration.synced",
        resource_type="connected_account",
        resource_id=account.id,
        metadata={
            "provider": provider_id,
            "status": sync_log.status.value,
            "error": sync_log.error_message,
        },
        request=request,
    )

    db.commit()
    db.refresh(sync_log)
    return sync_log
