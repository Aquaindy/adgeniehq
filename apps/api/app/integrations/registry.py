from app.core.exceptions import AdVantaError
from app.integrations.base import BaseProvider
from app.integrations.google_ads import GoogleAdsProvider
from app.integrations.google_analytics import GoogleAnalyticsProvider
from app.integrations.google_search_console import GoogleSearchConsoleProvider
from app.integrations.linkedin_ads import LinkedInAdsProvider
from app.integrations.meta_ads import MetaAdsProvider


class UnknownProviderError(AdVantaError):
    status_code = 404
    code = "unknown_provider"


PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    GoogleAdsProvider.provider_id: GoogleAdsProvider,
    MetaAdsProvider.provider_id: MetaAdsProvider,
    LinkedInAdsProvider.provider_id: LinkedInAdsProvider,
    GoogleAnalyticsProvider.provider_id: GoogleAnalyticsProvider,
    GoogleSearchConsoleProvider.provider_id: GoogleSearchConsoleProvider,
}


def get_provider(provider_id: str) -> type[BaseProvider]:
    cls = PROVIDER_REGISTRY.get(provider_id)
    if cls is None:
        raise UnknownProviderError(f"Unknown integration provider: {provider_id}.")
    return cls


def list_providers() -> list[type[BaseProvider]]:
    return list(PROVIDER_REGISTRY.values())
