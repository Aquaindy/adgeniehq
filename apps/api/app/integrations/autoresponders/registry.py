"""Pluggable registry of autoresponder adapters.

Adding a new provider = write one adapter file and register it here. Everything
else (connect form, audience listing, push/pull, audit) is driven off the
adapter's class metadata and the common interface."""

from app.core.exceptions import AdVantaError
from app.integrations.autoresponders.base import AutoresponderAdapter
from app.integrations.autoresponders.custom import CustomWebhookAdapter
from app.integrations.autoresponders.getresponse import GetResponseAdapter
from app.integrations.autoresponders.omnisend import OmnisendAdapter


class UnknownAutoresponderError(AdVantaError):
    status_code = 404
    code = "unknown_autoresponder"


# Order here is the order shown in the connect UI. Omnisend ships first.
AUTORESPONDER_REGISTRY: dict[str, type[AutoresponderAdapter]] = {
    OmnisendAdapter.provider_id: OmnisendAdapter,
    GetResponseAdapter.provider_id: GetResponseAdapter,
    CustomWebhookAdapter.provider_id: CustomWebhookAdapter,
}


def get_adapter(provider_id: str) -> type[AutoresponderAdapter]:
    adapter = AUTORESPONDER_REGISTRY.get(provider_id)
    if adapter is None:
        raise UnknownAutoresponderError(f"Unknown autoresponder provider: {provider_id}.")
    return adapter


def list_adapters() -> list[type[AutoresponderAdapter]]:
    return list(AUTORESPONDER_REGISTRY.values())
