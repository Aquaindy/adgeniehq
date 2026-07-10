from app.agents.base import BaseAgent
from app.agents.campaign_builder import CampaignBuilderAgent
from app.agents.content_writer import ContentWriterAgent
from app.agents.creative_strategy import CreativeStrategyAgent
from app.agents.email_marketing import EmailMarketingAgent
from app.agents.growth_content import GrowthContentAgent
from app.agents.icp_persona import IcpPersonaAgent
from app.agents.landing_page_audit import LandingPageAuditAgent
from app.agents.market_intelligence import MarketIntelligenceAgent
from app.agents.omnisend_journey import OmnisendJourneyAgent
from app.agents.onboarding_insight import OnboardingInsightAgent
from app.agents.orchestrator import MasterOrchestratorAgent
from app.agents.paid_ads import PaidAdsAgent
from app.agents.seo_audit import SEOAuditAgent
from app.agents.social_content import SocialContentAgent
from app.agents.solo_ads import SoloAdsAgent
from app.agents.tracking_attribution import TrackingAttributionAgent
from app.agents.traffic_assets import TrafficAssetAgent
from app.agents.traffic_optimizer import TrafficOptimizerAgent
from app.agents.traffic_recommendation import TrafficRecommendationAgent
from app.agents.website_audit import WebsiteAuditAgent

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    WebsiteAuditAgent.type: WebsiteAuditAgent,
    OnboardingInsightAgent.type: OnboardingInsightAgent,
    PaidAdsAgent.type: PaidAdsAgent,
    SEOAuditAgent.type: SEOAuditAgent,
    LandingPageAuditAgent.type: LandingPageAuditAgent,
    ContentWriterAgent.type: ContentWriterAgent,
    SocialContentAgent.type: SocialContentAgent,
    MarketIntelligenceAgent.type: MarketIntelligenceAgent,
    IcpPersonaAgent.type: IcpPersonaAgent,
    CreativeStrategyAgent.type: CreativeStrategyAgent,
    GrowthContentAgent.type: GrowthContentAgent,
    CampaignBuilderAgent.type: CampaignBuilderAgent,
    TrackingAttributionAgent.type: TrackingAttributionAgent,
    EmailMarketingAgent.type: EmailMarketingAgent,
    TrafficRecommendationAgent.type: TrafficRecommendationAgent,
    TrafficAssetAgent.type: TrafficAssetAgent,
    TrafficOptimizerAgent.type: TrafficOptimizerAgent,
    SoloAdsAgent.type: SoloAdsAgent,
    OmnisendJourneyAgent.type: OmnisendJourneyAgent,
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
