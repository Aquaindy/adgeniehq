from app.agents.base import BaseAgent
from app.agents.campaign_builder import CampaignBuilderAgent
from app.agents.content_writer import ContentWriterAgent
from app.agents.creative_strategy import CreativeStrategyAgent
from app.agents.icp_persona import IcpPersonaAgent
from app.agents.landing_page_audit import LandingPageAuditAgent
from app.agents.market_intelligence import MarketIntelligenceAgent
from app.agents.onboarding_insight import OnboardingInsightAgent
from app.agents.orchestrator import MasterOrchestratorAgent
from app.agents.paid_ads import PaidAdsAgent
from app.agents.seo_audit import SEOAuditAgent
from app.agents.tracking_attribution import TrackingAttributionAgent
from app.agents.website_audit import WebsiteAuditAgent

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    WebsiteAuditAgent.type: WebsiteAuditAgent,
    OnboardingInsightAgent.type: OnboardingInsightAgent,
    PaidAdsAgent.type: PaidAdsAgent,
    SEOAuditAgent.type: SEOAuditAgent,
    LandingPageAuditAgent.type: LandingPageAuditAgent,
    ContentWriterAgent.type: ContentWriterAgent,
    MarketIntelligenceAgent.type: MarketIntelligenceAgent,
    IcpPersonaAgent.type: IcpPersonaAgent,
    CreativeStrategyAgent.type: CreativeStrategyAgent,
    CampaignBuilderAgent.type: CampaignBuilderAgent,
    TrackingAttributionAgent.type: TrackingAttributionAgent,
    MasterOrchestratorAgent.type: MasterOrchestratorAgent,
}


def list_catalog() -> list[dict]:
    return [
        {
            "type": cls.type,
            "title": cls.title,
            "description": cls.description,
        }
        for cls in AGENT_REGISTRY.values()
    ]


def get_agent(agent_type: str) -> type[BaseAgent] | None:
    return AGENT_REGISTRY.get(agent_type)
