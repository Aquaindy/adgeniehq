"""Registry of payment-collection providers.

Adding a processor = one adapter file + an entry here. The billing service and
the fee ledger are unchanged."""

from app.core.exceptions import AdVantaError
from app.payments.base import PaymentProvider
from app.payments.manual import ManualPaymentProvider
from app.payments.paddle import PaddlePaymentProvider
from app.payments.paypal import PayPalPaymentProvider
from app.payments.stripe_provider import StripePaymentProvider


class UnknownPaymentProviderError(AdVantaError):
    status_code = 404
    code = "unknown_payment_provider"


PAYMENT_REGISTRY: dict[str, type[PaymentProvider]] = {
    ManualPaymentProvider.provider_id: ManualPaymentProvider,
    StripePaymentProvider.provider_id: StripePaymentProvider,
    PaddlePaymentProvider.provider_id: PaddlePaymentProvider,
    PayPalPaymentProvider.provider_id: PayPalPaymentProvider,
}


def get_payment_provider(provider_id: str) -> type[PaymentProvider]:
    cls = PAYMENT_REGISTRY.get(provider_id)
    if cls is None:
        raise UnknownPaymentProviderError(f"Unknown payment provider: {provider_id}.")
    return cls


def list_payment_providers() -> list[type[PaymentProvider]]:
    return list(PAYMENT_REGISTRY.values())
