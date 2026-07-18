from fastapi import APIRouter

from app.api.v1 import (
    ab_tests,
    ad_hierarchy,
    admin,
    agents,
    analytics,
    api_keys,
    appsumo,
    auth,
    autopilot,
    autoresponders,
    billing,
    campaigns,
    content_drafts,
    email_campaigns,
    fees,
    health,
    help,
    inbound,
    integrations,
    landing_pages,
    omnisend,
    onboarding,
    outreach,
    provider_credentials,
    provider_webhooks,
    public_ab,
    public_blog,
    recommendations,
    reports,
    seo,
    social_content,
    solo_ads,
    suggested_copies,
    traffic,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(help.router, tags=["help"])
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
api_router.include_router(email_campaigns.router, prefix="/workspaces", tags=["email-campaigns"])
api_router.include_router(traffic.router, prefix="/workspaces", tags=["traffic"])
api_router.include_router(solo_ads.router, prefix="/workspaces", tags=["solo-ads"])
api_router.include_router(omnisend.router, prefix="/workspaces", tags=["omnisend"])
api_router.include_router(seo.router, prefix="/workspaces", tags=["seo"])
api_router.include_router(landing_pages.router, prefix="/workspaces", tags=["website"])
api_router.include_router(reports.router, prefix="/workspaces", tags=["reports"])
api_router.include_router(content_drafts.router, prefix="/workspaces", tags=["content"])
api_router.include_router(
    social_content.router, prefix="/workspaces", tags=["social-content"]
)
api_router.include_router(
    suggested_copies.router, prefix="/workspaces", tags=["suggested-copies"]
)
api_router.include_router(outreach.router, prefix="/workspaces", tags=["outreach"])
api_router.include_router(ab_tests.router, prefix="/workspaces", tags=["ab-tests"])
api_router.include_router(public_ab.router, prefix="/public", tags=["public"])
api_router.include_router(public_blog.router, prefix="/public", tags=["public-blog"])
api_router.include_router(inbound.router, prefix="/inbound", tags=["inbound"])
api_router.include_router(billing.workspace_router, prefix="/workspaces", tags=["billing"])
api_router.include_router(billing.public_router, prefix="/billing", tags=["billing"])
api_router.include_router(appsumo.workspace_router, prefix="/workspaces", tags=["appsumo"])
api_router.include_router(appsumo.admin_router, prefix="/appsumo", tags=["appsumo"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(analytics.router, prefix="/workspaces", tags=["analytics"])
api_router.include_router(fees.workspace_router, prefix="/workspaces", tags=["fees"])
api_router.include_router(fees.admin_router, prefix="/admin", tags=["admin-fees"])
api_router.include_router(autopilot.router, prefix="/workspaces", tags=["autopilot"])
api_router.include_router(api_keys.router, prefix="/workspaces", tags=["api-keys"])
api_router.include_router(
    provider_credentials.router,
    prefix="/workspaces",
    tags=["provider-credentials"],
)
api_router.include_router(ad_hierarchy.router, prefix="/workspaces", tags=["ad-hierarchy"])
api_router.include_router(
    autoresponders.router, prefix="/workspaces", tags=["autoresponders"]
)
api_router.include_router(provider_webhooks.router, tags=["webhooks"])
