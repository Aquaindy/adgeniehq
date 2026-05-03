"""A/B test runner.

Two test targets:
  * `ad` — variants launch as separate campaigns on the ad provider via the
    Phase A write pipeline (provider.create_campaign). Once launched, each
    variant has its own `external_id`; the orchestrator can later route
    pause/budget changes through the same pipeline.
  * `landing_page` — variants are URL/copy pairs whose outcome metrics are
    recorded manually (or via a future analytics-sync skill). No provider
    write is needed; "launching" just timestamps the variants and flips the
    test to LAUNCHED so reporting starts counting.

Production rules:
  * Tests don't auto-launch. Admin must call `launch_test`.
  * Traffic shares must sum to 1.0 (within rounding) at launch time.
  * Provider failure during ad-test launch surfaces as ProviderError; any
    variants already launched stay launched (so the user can retry the
    failed ones rather than rolling back a partial spend).
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import Request
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AdVantaError
from app.core.logging import get_logger
from app.integrations.base import (
    BaseProvider,
    ProviderError,
    ProviderNotConfiguredError,
)
from app.integrations.registry import get_provider
from app.models.ab_test import (
    AbTest,
    AbTestStatus,
    AbTestTarget,
    AbTestVariant,
    BanditStrategy,
)
from app.models.ab_test_event import AbTestConversion, AbTestExposure
from app.models.audit_log import AuditActorType
from app.models.connected_account import ConnectedAccount, ConnectionStatus
from app.models.usage_event import UsageEventType
from app.security.permissions import Role, require_role_at_least
from app.services import audit_service, billing_service, integration_service

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AbTestNotFoundError(AdVantaError):
    status_code = 404
    code = "ab_test_not_found"


class AbTestVariantNotFoundError(AdVantaError):
    status_code = 404
    code = "ab_test_variant_not_found"


class InvalidAbTestError(AdVantaError):
    status_code = 400
    code = "invalid_ab_test"


class InvalidAbTestStateError(AdVantaError):
    status_code = 409
    code = "invalid_ab_test_state"


class AbTestLaunchFailedError(AdVantaError):
    status_code = 502
    code = "ab_test_launch_failed"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_variants(*, target: AbTestTarget, variants: list[dict]) -> None:
    if len(variants) < 2:
        raise InvalidAbTestError("An A/B test needs at least two variants.")
    names = [v.get("name") for v in variants]
    if len(set(names)) != len(names) or any(not n for n in names):
        raise InvalidAbTestError("Variants must have unique non-empty names.")
    control_count = sum(1 for v in variants if v.get("is_control"))
    if control_count > 1:
        raise InvalidAbTestError("At most one variant can be the control.")
    total_share = sum(float(v.get("traffic_share") or 0) for v in variants)
    if total_share == 0:
        # Auto-fill: split equally.
        equal = round(1.0 / len(variants), 4)
        for v in variants:
            v["traffic_share"] = equal
    elif abs(total_share - 1.0) > 0.01:
        raise InvalidAbTestError(
            f"Variant traffic_share must sum to 1.0 (got {total_share:.3f})."
        )

    if target == AbTestTarget.AD:
        for v in variants:
            payload = v.get("payload") or {}
            if not payload.get("name"):
                raise InvalidAbTestError(
                    f"Ad variant `{v.get('name')}` is missing payload.name."
                )
            if not payload.get("daily_budget_cents"):
                raise InvalidAbTestError(
                    f"Ad variant `{v.get('name')}` is missing payload.daily_budget_cents."
                )
    elif target == AbTestTarget.LANDING_PAGE:
        for v in variants:
            payload = v.get("payload") or {}
            if not payload.get("url"):
                raise InvalidAbTestError(
                    f"Landing-page variant `{v.get('name')}` is missing payload.url."
                )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_test(
    db: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    name: str,
    hypothesis: str | None,
    target: AbTestTarget,
    objective: str,
    provider: str | None,
    external_account_id: str | None,
    variants: list[dict],
    metadata: dict | None = None,
    bandit_strategy: BanditStrategy = BanditStrategy.STATIC,
    request: Request | None = None,
) -> AbTest:
    require_role_at_least(actor_role, Role.MARKETER)
    billing_service.assert_within_ab_test_limit(db, workspace_id=workspace_id)
    _validate_variants(target=target, variants=variants)

    if target == AbTestTarget.AD:
        if not provider or not external_account_id:
            raise InvalidAbTestError(
                "Ad-target tests need provider and external_account_id."
            )
        # Best-effort: surface a clear error if the provider isn't configured.
        get_provider(provider)

    test = AbTest(
        workspace_id=workspace_id,
        name=name.strip()[:255],
        hypothesis=hypothesis,
        target=target,
        objective=objective,
        provider=provider,
        external_account_id=external_account_id,
        status=AbTestStatus.READY,
        metadata_json=metadata,
        created_by=actor_user_id,
        bandit_strategy=bandit_strategy,
    )
    db.add(test)
    db.flush()

    for idx, v in enumerate(variants):
        db.add(
            AbTestVariant(
                workspace_id=workspace_id,
                ab_test_id=test.id,
                name=v["name"][:64],
                position=idx,
                is_control=bool(v.get("is_control")),
                traffic_share=Decimal(str(v.get("traffic_share") or 0.5)),
                payload=v.get("payload") or {},
                metrics={},
            )
        )

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="ab_test.created",
        resource_type="ab_test",
        resource_id=test.id,
        metadata={
            "target": target.value,
            "objective": objective,
            "variant_count": len(variants),
        },
        request=request,
    )
    billing_service.record_usage_event(
        db,
        workspace_id=workspace_id,
        event_type=UsageEventType.AB_TEST_CREATED,
        metadata={"target": target.value},
    )

    db.commit()
    db.refresh(test)
    return test


def list_tests(
    db: Session,
    *,
    workspace_id: UUID,
    target: AbTestTarget | None = None,
    status: AbTestStatus | None = None,
    limit: int = 50,
) -> list[AbTest]:
    query = db.query(AbTest).filter(AbTest.workspace_id == workspace_id)
    if target is not None:
        query = query.filter(AbTest.target == target)
    if status is not None:
        query = query.filter(AbTest.status == status)
    return query.order_by(desc(AbTest.created_at)).limit(limit).all()


def get_test(db: Session, *, workspace_id: UUID, test_id: UUID) -> AbTest:
    row = (
        db.query(AbTest)
        .filter(AbTest.id == test_id, AbTest.workspace_id == workspace_id)
        .first()
    )
    if row is None:
        raise AbTestNotFoundError("A/B test not found in this workspace.")
    # Overlay live exposure/conversion counts onto landing-page-test variants
    # so the dashboard always reads current numbers without a sync job.
    return hydrate_metrics(db, test=row)


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------


def _resolve_provider_for_test(
    db: Session, *, workspace_id: UUID, provider_id: str
) -> tuple[type[BaseProvider], str]:
    provider_cls = get_provider(provider_id)
    if not provider_cls.is_configured():
        raise ProviderNotConfiguredError(
            f"{provider_cls.display_name} is not configured on this server."
        )
    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == provider_id,
        )
        .first()
    )
    if (
        account is None
        or account.status != ConnectionStatus.CONNECTED
        or account.token is None
    ):
        raise InvalidAbTestStateError(
            f"{provider_id} is not connected for this workspace; connect it before launching."
        )
    return provider_cls, integration_service.get_fresh_access_token(
        db, account=account
    )


def launch_test(
    db: Session,
    *,
    workspace_id: UUID,
    test_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> AbTest:
    require_role_at_least(actor_role, Role.ADMIN)
    test = get_test(db, workspace_id=workspace_id, test_id=test_id)
    if test.status not in (AbTestStatus.READY, AbTestStatus.PAUSED):
        raise InvalidAbTestStateError(
            f"Cannot launch a test in `{test.status.value}` state."
        )

    if test.target == AbTestTarget.LANDING_PAGE:
        # Just timestamp variants — no provider write.
        now = datetime.now(timezone.utc)
        for variant in test.variants:
            if variant.launched_at is None:
                variant.launched_at = now
        test.status = AbTestStatus.LAUNCHED
        if test.started_at is None:
            test.started_at = now
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER,
            actor_id=actor_user_id,
            action="ab_test.launched",
            resource_type="ab_test",
            resource_id=test.id,
            metadata={"target": "landing_page"},
            request=request,
        )
        db.commit()
        db.refresh(test)
        return test

    # target == AD. Launch each non-launched variant via provider.create_campaign.
    if not test.provider or not test.external_account_id:
        raise InvalidAbTestStateError(
            "Ad-target test is missing provider or external_account_id."
        )
    provider_cls, access_token = _resolve_provider_for_test(
        db, workspace_id=workspace_id, provider_id=test.provider
    )

    failures: list[dict] = []
    for variant in test.variants:
        if variant.launched_at is not None and variant.external_id:
            continue
        # Stamp the variant name onto the campaign so it's identifiable in the
        # provider's UI.
        payload = dict(variant.payload or {})
        if not payload.get("name"):
            payload["name"] = f"{test.name} — {variant.name}"
        # Default new ad campaigns to PAUSED in providers — the user can flip to
        # active explicitly. This avoids surprise spend.
        payload.setdefault("status", "PAUSED")

        try:
            result = provider_cls.create_campaign(
                access_token=access_token,
                external_account_id=test.external_account_id,
                payload=payload,
            )
        except (ProviderError, ProviderNotConfiguredError) as exc:
            failures.append({"variant": variant.name, "error": str(exc)})
            continue

        variant.external_id = result.get("external_id")
        variant.launched_at = datetime.now(timezone.utc)

    if failures and not any(v.launched_at for v in test.variants):
        # No variant launched — surface the error so the user sees it instead
        # of a "launched" test with zero campaigns.
        audit_service.log_event(
            db,
            workspace_id=workspace_id,
            actor_type=AuditActorType.USER,
            actor_id=actor_user_id,
            action="ab_test.launch_failed",
            resource_type="ab_test",
            resource_id=test.id,
            metadata={"failures": failures},
            request=request,
        )
        db.commit()
        raise AbTestLaunchFailedError(
            f"All {len(failures)} variant launches failed. First error: {failures[0]['error']}"
        )

    if all(v.launched_at for v in test.variants):
        test.status = AbTestStatus.LAUNCHED
    else:
        # Partial success — keep status READY so the user can retry the failed
        # variants, but record a launch attempt.
        pass

    if test.started_at is None and test.status == AbTestStatus.LAUNCHED:
        test.started_at = datetime.now(timezone.utc)

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="ab_test.launched" if test.status == AbTestStatus.LAUNCHED else "ab_test.partial_launch",
        resource_type="ab_test",
        resource_id=test.id,
        metadata={
            "target": "ad",
            "provider": test.provider,
            "failures": failures,
        },
        request=request,
    )

    db.commit()
    db.refresh(test)
    return test


# ---------------------------------------------------------------------------
# Metrics + winner
# ---------------------------------------------------------------------------


def record_variant_metrics(
    db: Session,
    *,
    workspace_id: UUID,
    test_id: UUID,
    variant_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    metrics: dict,
    request: Request | None = None,
) -> AbTestVariant:
    require_role_at_least(actor_role, Role.MARKETER)
    test = get_test(db, workspace_id=workspace_id, test_id=test_id)
    variant = next((v for v in test.variants if v.id == variant_id), None)
    if variant is None:
        raise AbTestVariantNotFoundError("Variant not found on this test.")

    merged = dict(variant.metrics or {})
    merged.update(metrics)
    variant.metrics = merged

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="ab_test_variant.metrics_recorded",
        resource_type="ab_test_variant",
        resource_id=variant.id,
        metadata={"keys": list(metrics.keys())},
        request=request,
    )

    db.commit()
    db.refresh(variant)
    return variant


def declare_winner(
    db: Session,
    *,
    workspace_id: UUID,
    test_id: UUID,
    variant_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    force: bool = False,
    request: Request | None = None,
) -> AbTest:
    """Declare a winner. Refuses when any variant is below the
    minimum-sample-per-variant threshold OR the headline two-proportion
    z-test isn't significant — pass `force=True` to override (e.g. when the
    user has off-platform context like a qualitative win)."""

    require_role_at_least(actor_role, Role.ADMIN)
    test = get_test(db, workspace_id=workspace_id, test_id=test_id)
    variant = next((v for v in test.variants if v.id == variant_id), None)
    if variant is None:
        raise AbTestVariantNotFoundError("Variant not found on this test.")

    if not force and test.target == AbTestTarget.LANDING_PAGE:
        # Only enforce the guard for landing-page tests because that's where
        # we have authoritative visit/conversion counts (from the public
        # exposure/conversion events). Ad tests rely on user-entered metrics
        # that may already include external-data confidence.
        from app.services import ab_statistics

        stats = ab_statistics.compute_test_statistics(
            variants=[
                {
                    "id": v.id,
                    "name": v.name,
                    "visits": int((v.metrics or {}).get("visits", 0) or 0),
                    "conversions": int((v.metrics or {}).get("conversions", 0) or 0),
                    "is_control": bool(v.is_control),
                }
                for v in test.variants
            ],
        )
        if stats.underpowered:
            raise InvalidAbTestStateError(
                f"Underpowered: each variant needs at least "
                f"{stats.min_sample_per_variant} visitors before a winner "
                f"can be declared. Pass force=true to override."
            )
        if not stats.significant:
            p = stats.p_value
            p_str = f"{p:.3f}" if p is not None else "n/a"
            raise InvalidAbTestStateError(
                f"Result is not statistically significant (p={p_str}). "
                f"Keep running the test or pass force=true to override."
            )

    test.winner_variant_id = variant.id
    test.status = AbTestStatus.COMPLETED
    test.ended_at = datetime.now(timezone.utc)

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="ab_test.winner_declared",
        resource_type="ab_test",
        resource_id=test.id,
        metadata={
            "winner_variant_id": str(variant.id),
            "variant_name": variant.name,
            "forced": force,
        },
        request=request,
    )

    db.commit()
    db.refresh(test)
    return test


def archive_test(
    db: Session,
    *,
    workspace_id: UUID,
    test_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    request: Request | None = None,
) -> AbTest:
    require_role_at_least(actor_role, Role.MARKETER)
    test = get_test(db, workspace_id=workspace_id, test_id=test_id)
    if test.status == AbTestStatus.ARCHIVED:
        return test
    test.status = AbTestStatus.ARCHIVED
    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="ab_test.archived",
        resource_type="ab_test",
        resource_id=test.id,
        metadata={},
        request=request,
    )
    db.commit()
    db.refresh(test)
    return test


# ---------------------------------------------------------------------------
# Public traffic split (called by the customer's site, not by an authenticated
# user). The /assign endpoint picks a sticky variant for each visitor; /convert
# records an outcome event for the previously-assigned variant.
# ---------------------------------------------------------------------------


class TestNotLaunchedError(AdVantaError):
    status_code = 409
    code = "ab_test_not_launched"


class UnknownVisitorError(AdVantaError):
    status_code = 404
    code = "ab_test_unknown_visitor"


def _pick_variant_static(variants: list[AbTestVariant]) -> AbTestVariant:
    """Pick a variant weighted by traffic_share."""

    weights = [float(v.traffic_share) for v in variants]
    total = sum(weights)
    if total <= 0:
        return random.choice(variants)
    r = random.random() * total
    acc = 0.0
    for variant, w in zip(variants, weights):
        acc += w
        if r <= acc:
            return variant
    return variants[-1]


def _pick_variant_thompson(
    db: Session, *, test: AbTest, variants: list[AbTestVariant]
) -> AbTestVariant:
    """Thompson sampling over a Beta(α=successes+1, β=failures+1) posterior
    per variant. Sample once per variant, pick the variant with the highest
    sample. Naturally explores while exploiting — an under-tested variant
    has a wide posterior so it still gets occasional traffic."""

    aggregates = aggregate_metrics(db, test=test)
    samples: list[tuple[AbTestVariant, float]] = []
    for variant in variants:
        agg = aggregates.get(variant.id, {})
        visits = int(agg.get("visits", 0))
        conversions = int(agg.get("conversions", 0))
        # Beta(α, β) with priors α=1, β=1 (uniform). After data: α=1+conversions,
        # β=1+(visits-conversions).
        alpha = 1 + conversions
        beta = 1 + max(0, visits - conversions)
        # `random.betavariate` is in stdlib — no scipy needed.
        sample = random.betavariate(alpha, beta)
        samples.append((variant, sample))
    # Highest sample wins.
    return max(samples, key=lambda s: s[1])[0]


def _pick_variant(
    db: Session, *, test: AbTest, variants: list[AbTestVariant]
) -> AbTestVariant:
    """Dispatcher: routes to the strategy configured on the test."""

    if test.bandit_strategy == BanditStrategy.THOMPSON_SAMPLING:
        return _pick_variant_thompson(db, test=test, variants=variants)
    return _pick_variant_static(variants)


def assign_visitor(
    db: Session,
    *,
    test_id: UUID,
    visitor_id: str,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[AbTest, AbTestVariant]:
    """Sticky-assign a variant to a visitor. The first call rolls a weighted
    pick and inserts an exposure row; subsequent calls for the same visitor
    return the variant captured then."""

    test = (
        db.query(AbTest)
        .filter(AbTest.id == test_id)
        .first()
    )
    if test is None:
        raise AbTestNotFoundError("A/B test not found.")
    if test.target != AbTestTarget.LANDING_PAGE:
        raise InvalidAbTestError(
            "Public traffic-split is only supported for landing-page tests."
        )
    if test.status != AbTestStatus.LAUNCHED:
        raise TestNotLaunchedError(
            f"A/B test is `{test.status.value}` — assignments only happen while LAUNCHED."
        )

    visitor_id = visitor_id.strip()[:64]
    if not visitor_id:
        raise InvalidAbTestError("visitor_id is required.")

    existing = (
        db.query(AbTestExposure)
        .filter(
            AbTestExposure.ab_test_id == test.id,
            AbTestExposure.visitor_id == visitor_id,
        )
        .first()
    )
    if existing is not None:
        variant = next(
            (v for v in test.variants if v.id == existing.ab_test_variant_id),
            None,
        )
        if variant is not None:
            return test, variant
        # Stored variant disappeared (cascade SET NULL would have left None,
        # but variants are CASCADE delete so this is unreachable in practice).
        # Fall through to a fresh pick.

    variant = _pick_variant(db, test=test, variants=list(test.variants))
    exposure = AbTestExposure(
        workspace_id=test.workspace_id,
        ab_test_id=test.id,
        ab_test_variant_id=variant.id,
        visitor_id=visitor_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(exposure)
    try:
        db.commit()
    except IntegrityError:
        # Race: a concurrent request inserted the exposure first. Re-read.
        db.rollback()
        existing = (
            db.query(AbTestExposure)
            .filter(
                AbTestExposure.ab_test_id == test.id,
                AbTestExposure.visitor_id == visitor_id,
            )
            .first()
        )
        if existing is None:  # pragma: no cover — defensive
            raise
        variant = next(v for v in test.variants if v.id == existing.ab_test_variant_id)
    return test, variant


def record_conversion(
    db: Session,
    *,
    test_id: UUID,
    visitor_id: str,
    value_cents: int | None = None,
    metadata: dict | None = None,
) -> AbTestConversion:
    """Record an outcome event for the variant the visitor was previously
    assigned to. Refuses (404) if the visitor wasn't seen — recording a
    conversion against an unknown visitor would silently miscount."""

    test = (
        db.query(AbTest)
        .filter(AbTest.id == test_id)
        .first()
    )
    if test is None:
        raise AbTestNotFoundError("A/B test not found.")

    visitor_id = visitor_id.strip()[:64]
    exposure = (
        db.query(AbTestExposure)
        .filter(
            AbTestExposure.ab_test_id == test.id,
            AbTestExposure.visitor_id == visitor_id,
        )
        .first()
    )
    if exposure is None:
        raise UnknownVisitorError(
            "Visitor has no exposure for this test — call /assign first."
        )

    conversion = AbTestConversion(
        workspace_id=test.workspace_id,
        ab_test_id=test.id,
        ab_test_variant_id=exposure.ab_test_variant_id,
        visitor_id=visitor_id,
        occurred_at=datetime.now(timezone.utc),
        value_cents=value_cents,
        metadata_json=metadata,
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)
    return conversion


def aggregate_metrics(db: Session, *, test: AbTest) -> dict[UUID, dict]:
    """Compute per-variant {visits, conversions, conversion_rate, revenue_cents}
    from exposure + conversion rows. Returns a dict keyed by variant id; the
    caller decides whether to persist by writing into variant.metrics."""

    visits_q = (
        db.query(
            AbTestExposure.ab_test_variant_id.label("variant_id"),
            func.count(AbTestExposure.id).label("visits"),
        )
        .filter(AbTestExposure.ab_test_id == test.id)
        .group_by(AbTestExposure.ab_test_variant_id)
    )
    visits_by_variant = {row.variant_id: int(row.visits) for row in visits_q}

    conversions_q = (
        db.query(
            AbTestConversion.ab_test_variant_id.label("variant_id"),
            func.count(AbTestConversion.id).label("conversions"),
            func.coalesce(func.sum(AbTestConversion.value_cents), 0).label("revenue_cents"),
        )
        .filter(AbTestConversion.ab_test_id == test.id)
        .group_by(AbTestConversion.ab_test_variant_id)
    )
    conv_by_variant: dict[UUID, dict] = {
        row.variant_id: {
            "conversions": int(row.conversions),
            "revenue_cents": int(row.revenue_cents or 0),
        }
        for row in conversions_q
    }

    out: dict[UUID, dict] = {}
    for variant in test.variants:
        visits = visits_by_variant.get(variant.id, 0)
        c = conv_by_variant.get(variant.id, {})
        conversions = int(c.get("conversions", 0))
        out[variant.id] = {
            "visits": visits,
            "conversions": conversions,
            "conversion_rate": (conversions / visits) if visits > 0 else 0.0,
            "revenue_cents": int(c.get("revenue_cents", 0)),
        }
    return out


def sync_metrics_from_ga4(
    db: Session,
    *,
    workspace_id: UUID,
    test_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
    property_id: str | None = None,
    conversion_event: str | None = None,
    request: Request | None = None,
) -> AbTest:
    """Pull sessions + conversions from the workspace's connected GA4
    account, keyed by the path component of each variant's payload.url.
    Folds the result into variant.metrics so the dashboard + statistics
    block reflect real-world traffic."""

    require_role_at_least(actor_role, Role.MARKETER)
    test = get_test(db, workspace_id=workspace_id, test_id=test_id)
    if test.target != AbTestTarget.LANDING_PAGE:
        raise InvalidAbTestError(
            "GA4 sync is only supported for landing-page tests."
        )

    from app.integrations.google_analytics import (
        GoogleAnalyticsProvider,
        url_to_path,
    )

    account = (
        db.query(ConnectedAccount)
        .filter(
            ConnectedAccount.workspace_id == workspace_id,
            ConnectedAccount.provider == "google_analytics",
        )
        .first()
    )
    if (
        account is None
        or account.status != ConnectionStatus.CONNECTED
        or account.token is None
    ):
        raise InvalidAbTestStateError(
            "Connect Google Analytics first to sync metrics from GA4."
        )

    access_token = integration_service.get_fresh_access_token(db, account=account)

    if not property_id:
        properties = GoogleAnalyticsProvider.list_properties(access_token=access_token)
        if not properties:
            raise InvalidAbTestStateError(
                "GA4 account has no properties; cannot sync metrics."
            )
        property_id = properties[0]["property"]

    path_to_variant: dict[str, AbTestVariant] = {}
    for variant in test.variants:
        url = (variant.payload or {}).get("url")
        if not url:
            continue
        path = url_to_path(url)
        path_to_variant[path] = variant

    if not path_to_variant:
        return test

    rows = GoogleAnalyticsProvider.report_page_metrics(
        access_token=access_token,
        property_id=property_id,
        page_paths=list(path_to_variant.keys()),
        conversion_event=conversion_event,
    )

    for path, variant in path_to_variant.items():
        agg = rows.get(path, {"sessions": 0, "conversions": 0})
        merged = dict(variant.metrics or {})
        merged.update(
            {
                "visits": agg["sessions"],
                "conversions": agg["conversions"],
                "ga4_synced_at": datetime.now(timezone.utc).isoformat(),
                "ga4_property_id": property_id,
            }
        )
        variant.metrics = merged

    audit_service.log_event(
        db,
        workspace_id=workspace_id,
        actor_type=AuditActorType.USER,
        actor_id=actor_user_id,
        action="ab_test.metrics_synced_ga4",
        resource_type="ab_test",
        resource_id=test.id,
        metadata={
            "property_id": property_id,
            "paths_synced": len(path_to_variant),
        },
        request=request,
    )

    db.commit()
    db.refresh(test)
    return test


def hydrate_metrics(db: Session, *, test: AbTest) -> AbTest:
    """For landing-page tests with real exposures, fold the public-event
    aggregates into each variant's `metrics` so the dashboard stays current
    without a separate sync job.

    If the test has zero exposures (e.g. a brand-new test, or one tracked
    entirely through manual metric updates), we leave `variant.metrics` alone
    — overwriting it with zeros would clobber the user's hand-entered numbers."""

    if test.target != AbTestTarget.LANDING_PAGE:
        return test
    aggregates = aggregate_metrics(db, test=test)
    has_exposures = any(a.get("visits", 0) > 0 for a in aggregates.values())
    if not has_exposures:
        return test
    for variant in test.variants:
        merged = dict(variant.metrics or {})
        merged.update(aggregates.get(variant.id, {}))
        variant.metrics = merged
    # No commit — caller decides whether the metrics overlay should persist.
    return test
