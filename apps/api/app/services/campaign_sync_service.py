"""Cross-provider campaign sync.

Drives the Paid Ads Agent's view of the world: pull campaigns from every
connected ad-platform account in a workspace, normalize them, upsert into the
`campaigns` table, and record a `SyncLog` per attempt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.integrations.base import (
    BaseProvider,
    CampaignData,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderNotImplementedError,
)
from app.integrations.registry import PROVIDER_REGISTRY, get_provider
from app.models.campaign import Campaign
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.sync_log import SyncLog, SyncLogStatus
from app.services import integration_service

log = get_logger(__name__)

# Providers whose campaigns we sync. Other providers (GA4, Search Console)
# don't expose campaigns.
AD_PLATFORM_PROVIDERS: tuple[str, ...] = ("google_ads", "meta_ads", "linkedin_ads")


class NoConnectedAdAccountsError(AdVantaError):
    status_code = 409
    code = "no_connected_ad_accounts"


@dataclass
class ProviderSyncResult:
    provider: str
    sync_log_id: UUID
    status: SyncLogStatus
    fetched: int
    upserted: int
    error: str | None


@dataclass
class SyncSummary:
    workspace_id: UUID
    started_at: datetime
    completed_at: datetime
    providers: list[ProviderSyncResult]


def sync_workspace_campaigns(
    db: Session, *, workspace_id: UUID, only_provider: str | None = None
) -> SyncSummary:
    started_at = datetime.now(timezone.utc)

    accounts = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider.in_(AD_PLATFORM_PROVIDERS),
            ConnectedAccount.status == ConnectionStatus.CONNECTED,
        )
        .all()
    )

    if only_provider is not None:
        get_provider(only_provider)  # 404 on unknown id
        accounts = [a for a in accounts if a.provider == only_provider]

    if not accounts:
        raise NoConnectedAdAccountsError(
            "No connected ad-platform accounts to sync. Connect Google Ads, Meta Ads, "
            "or LinkedIn Ads first.",
        )

    results = [_sync_account(db, account) for account in accounts]

    return SyncSummary(
        workspace_id=workspace_id,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        providers=results,
    )


def _sync_account(db: Session, account: ConnectedAccount) -> ProviderSyncResult:
    provider_cls: type[BaseProvider] = PROVIDER_REGISTRY[account.provider]
    started_at = datetime.now(timezone.utc)

    sync_log = SyncLog(
        connected_account_id=account.id,
        status=SyncLogStatus.RUNNING,
        started_at=started_at,
    )
    db.add(sync_log)
    db.flush()

    try:
        if account.token is None:
            raise ProviderError("OAuth tokens are missing for this account.")
        access_token = integration_service.get_fresh_access_token(
            db, account=account
        )
        campaigns = provider_cls.sync_campaigns(access_token=access_token)
    except (ProviderNotImplementedError, ProviderNotConfiguredError, ProviderError) as exc:
        log.warning("campaign_sync.failed", provider=account.provider, error=str(exc))
        sync_log.status = SyncLogStatus.FAILED
        sync_log.completed_at = datetime.now(timezone.utc)
        sync_log.error_message = str(exc)
        account.last_error = str(exc)
        db.commit()
        return ProviderSyncResult(
            provider=account.provider,
            sync_log_id=sync_log.id,
            status=SyncLogStatus.FAILED,
            fetched=0,
            upserted=0,
            error=str(exc),
        )

    upserted = _upsert_campaigns(
        db, workspace_id=account.workspace_id, account=account, campaigns=campaigns
    )

    completed_at = datetime.now(timezone.utc)
    sync_log.status = SyncLogStatus.SUCCEEDED
    sync_log.completed_at = completed_at
    sync_log.summary = {
        "fetched": len(campaigns),
        "upserted": upserted,
    }
    account.last_sync_at = completed_at
    account.last_error = None

    db.commit()
    return ProviderSyncResult(
        provider=account.provider,
        sync_log_id=sync_log.id,
        status=SyncLogStatus.SUCCEEDED,
        fetched=len(campaigns),
        upserted=upserted,
        error=None,
    )


def _upsert_campaigns(
    db: Session,
    *,
    workspace_id: UUID,
    account: ConnectedAccount,
    campaigns: Iterable[CampaignData],
) -> int:
    now = datetime.now(timezone.utc)
    count = 0
    for data in campaigns:
        existing = (
            db.query(Campaign)
            .filter(
                Campaign.workspace_id == workspace_id,
                Campaign.provider == account.provider,
                Campaign.external_id == data.external_id,
            )
            .first()
        )
        if existing is None:
            existing = Campaign(
                workspace_id=workspace_id,
                provider=account.provider,
                external_id=data.external_id,
                last_synced_at=now,
            )
            db.add(existing)

        existing.connected_account_id = account.id
        existing.external_account_id = data.external_account_id
        existing.name = data.name
        existing.status = data.status
        existing.objective = data.objective
        existing.daily_budget_cents = data.daily_budget_cents
        existing.lifetime_budget_cents = data.lifetime_budget_cents
        existing.currency = data.currency
        existing.start_date = data.start_date
        existing.end_date = data.end_date
        existing.last_synced_at = now
        existing.raw_payload = data.raw
        count += 1
    db.flush()
    return count
