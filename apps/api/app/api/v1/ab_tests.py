from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ab_test import AbTestStatus, AbTestTarget
from app.models.workspace_member import WorkspaceMember
from app.models.ab_test import AbTestTarget as _AbTestTarget
from app.schemas.ab_tests import (
    AbTestPublic,
    CreateAbTestRequest,
    DeclareWinnerRequest,
    RecordMetricsRequest,
    TestStatisticsPublic,
    VariantStatsPublic,
)
from app.security.dependencies import get_current_member
from app.services import ab_statistics, ab_test_service, ab_variant_generator
from app.workers.dispatch import run_or_dispatch
from app.workers.tasks import launch_ab_test_task

router = APIRouter()


def _serialize(test) -> AbTestPublic:
    """Serialize an AbTest, attaching live statistics for landing-page tests
    (visits/conversions from public events) and ad tests with metrics
    populated (e.g. via /metrics or a GA4/ads sync)."""

    public = AbTestPublic.model_validate(test)
    has_any_metrics = any(
        (v.metrics or {}).get("visits") or (v.metrics or {}).get("conversions")
        for v in test.variants
    )
    if test.target == _AbTestTarget.LANDING_PAGE or has_any_metrics:
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
        public.statistics = TestStatisticsPublic(
            variants=[
                VariantStatsPublic(
                    variant_id=vs.variant_id,
                    name=vs.name,
                    visits=vs.visits,
                    conversions=vs.conversions,
                    conversion_rate=vs.conversion_rate,
                    ci_low=vs.ci_low,
                    ci_high=vs.ci_high,
                )
                for vs in stats.variants
            ],
            p_value=stats.p_value,
            z_score=stats.z_score,
            relative_lift=stats.relative_lift,
            significant=stats.significant,
            confidence=stats.confidence,
            min_sample_per_variant=stats.min_sample_per_variant,
            underpowered=stats.underpowered,
            suggested_winner_variant_id=stats.winner_variant_id,
        )
    return public


@router.get("/{workspace_id}/ab-tests", response_model=list[AbTestPublic])
def list_tests(
    workspace_id: UUID,
    target: AbTestTarget | None = Query(default=None),
    status: AbTestStatus | None = Query(default=None),
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> list[AbTestPublic]:
    rows = ab_test_service.list_tests(
        db, workspace_id=workspace_id, target=target, status=status
    )
    return [_serialize(r) for r in rows]


@router.post("/{workspace_id}/ab-tests", response_model=AbTestPublic)
def create_test(
    workspace_id: UUID,
    payload: CreateAbTestRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AbTestPublic:
    test = ab_test_service.create_test(
        db,
        workspace_id=workspace_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        name=payload.name,
        hypothesis=payload.hypothesis,
        target=payload.target,
        objective=payload.objective,
        provider=payload.provider,
        external_account_id=payload.external_account_id,
        variants=[v.model_dump() for v in payload.variants],
        metadata=payload.metadata,
        bandit_strategy=payload.bandit_strategy,
        request=request,
    )
    return _serialize(test)


@router.get("/{workspace_id}/ab-tests/{test_id}", response_model=AbTestPublic)
def get_test(
    workspace_id: UUID,
    test_id: UUID,
    _member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AbTestPublic:
    return _serialize(
        ab_test_service.get_test(db, workspace_id=workspace_id, test_id=test_id)
    )


@router.post(
    "/{workspace_id}/ab-tests/{test_id}/launch",
    response_model=AbTestPublic,
)
def launch(
    workspace_id: UUID,
    test_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AbTestPublic:
    # Ad-target launches make 1 provider HTTP call per variant — offload to a
    # worker when configured so the API thread isn't tied up. Sync mode
    # (default) runs inline, identical to the previous behaviour.
    result = run_or_dispatch(
        launch_ab_test_task,
        workspace_id=str(workspace_id),
        test_id=str(test_id),
        actor_user_id=str(member.user_id),
        actor_role=member.role.value,
    )
    result.get(timeout=300)
    test = ab_test_service.get_test(
        db, workspace_id=workspace_id, test_id=test_id
    )
    return _serialize(test)


@router.post(
    "/{workspace_id}/ab-tests/{test_id}/variants/{variant_id}/metrics",
    response_model=AbTestPublic,
)
def record_metrics(
    workspace_id: UUID,
    test_id: UUID,
    variant_id: UUID,
    payload: RecordMetricsRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AbTestPublic:
    ab_test_service.record_variant_metrics(
        db,
        workspace_id=workspace_id,
        test_id=test_id,
        variant_id=variant_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        metrics=payload.metrics,
        request=request,
    )
    test = ab_test_service.get_test(
        db, workspace_id=workspace_id, test_id=test_id
    )
    return _serialize(test)


@router.post(
    "/{workspace_id}/ab-tests/{test_id}/sync-ga4",
    response_model=AbTestPublic,
)
def sync_ga4(
    workspace_id: UUID,
    test_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
    property_id: str | None = None,
    conversion_event: str | None = None,
) -> AbTestPublic:
    """Pull sessions + conversions from the workspace's GA4 account into
    each variant's metrics. Requires google_analytics to be connected."""

    test = ab_test_service.sync_metrics_from_ga4(
        db,
        workspace_id=workspace_id,
        test_id=test_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        property_id=property_id,
        conversion_event=conversion_event,
        request=request,
    )
    return _serialize(test)


@router.post(
    "/{workspace_id}/ab-tests/{test_id}/declare-winner",
    response_model=AbTestPublic,
)
def declare_winner(
    workspace_id: UUID,
    test_id: UUID,
    payload: DeclareWinnerRequest,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AbTestPublic:
    test = ab_test_service.declare_winner(
        db,
        workspace_id=workspace_id,
        test_id=test_id,
        variant_id=payload.variant_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        force=payload.force,
        request=request,
    )
    return _serialize(test)


@router.post(
    "/{workspace_id}/ab-tests/{test_id}/archive",
    response_model=AbTestPublic,
)
def archive(
    workspace_id: UUID,
    test_id: UUID,
    request: Request,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
) -> AbTestPublic:
    test = ab_test_service.archive_test(
        db,
        workspace_id=workspace_id,
        test_id=test_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        request=request,
    )
    return _serialize(test)


@router.post(
    "/{workspace_id}/ab-tests/{test_id}/generate-variants",
    response_model=AbTestPublic,
)
def generate_variants(
    workspace_id: UUID,
    test_id: UUID,
    member: WorkspaceMember = Depends(get_current_member),
    db: Session = Depends(get_db),
    count: int = Query(default=2, ge=1, le=4),
) -> AbTestPublic:
    """Generate N additional variants from the test's control payload. The
    test must be in DRAFT or READY status. Variants are persisted with
    even traffic-share distribution and tagged source='ai_generated' in the
    audit log."""
    ab_variant_generator.generate_variants_for_test(
        db,
        workspace_id=workspace_id,
        test_id=test_id,
        actor_user_id=member.user_id,
        actor_role=member.role,
        count=count,
    )
    test = ab_test_service.get_test(db, workspace_id=workspace_id, test_id=test_id)
    return _serialize(test)
