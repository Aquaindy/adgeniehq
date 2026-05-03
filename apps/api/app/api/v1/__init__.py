from fastapi import APIRouter

from app.api.v1 import (
    ab_tests,
    ad_hierarchy,
    admin,
    agents,
    api_keys,
    auth,
    autopilot,
    billing,
    campaigns,
    content_drafts,
    health,
    inbound,
    integrations,
    landing_pages,
    onboarding,
    outreach,
    provider_credentials,
    provider_webhooks,
    public_ab,
    public_blog,
    recommendations,
    reports,
    seo,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
api_router.include_router(onboarding.router, prefix="/workspaces", tags=["onboarding"])
api_router.include_router(agents.router, prefix="/workspaces", tags=["agents"])
api_router.include_router(recommendations.router, prefix="/workspaces", tags=["recommendations"])
api_router.include_router(
    integrations.workspace_router, prefix="/workspaces", tags=["integrations"]
)
api_router.include_router(
    integrations.public_router, prefix="/integrations", tags=["integrations"]
)
api_router.include_router(campaigns.router, prefix="/workspaces", tags=["campaigns"])
api_router.include_router(seo.router, prefix="/workspaces", tags=["seo"])
api_router.include_router(landing_pages.router, prefix="/workspaces", tags=["website"])
api_router.include_router(reports.router, prefix="/workspaces", tags=["reports"])
api_router.include_router(content_drafts.router, prefix="/workspaces", tags=["content"])
api_router.include_router(outreach.router, prefix="/workspaces", tags=["outreach"])
api_router.include_router(ab_tests.router, prefix="/workspaces", tags=["ab-tests"])
api_router.include_router(public_ab.router, prefix="/public", tags=["public"])
api_router.include_router(public_blog.router, prefix="/public", tags=["public-blog"])
api_router.include_router(inbound.router, prefix="/inbound", tags=["inbound"])
api_router.include_router(billing.workspace_router, prefix="/workspaces", tags=["billing"])
api_router.include_router(billing.public_router, prefix="/billing", tags=["billing"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(autopilot.router, prefix="/workspaces", tags=["autopilot"])
api_router.include_router(api_keys.router, prefix="/workspaces", tags=["api-keys"])
api_router.include_router(
    provider_credentials.router,
    prefix="/workspaces",
    tags=["provider-credentials"],
)
api_router.include_router(ad_hierarchy.router, prefix="/workspaces", tags=["ad-hierarchy"])
api_router.include_router(provider_webhooks.router, tags=["webhooks"])
