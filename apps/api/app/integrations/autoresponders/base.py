"""Autoresponder adapter abstraction.

Every email/SMS marketing platform (Omnisend, GetResponse, …) plugs in by
subclassing :class:`AutoresponderAdapter` and registering itself in
``registry.py``. The surface is deliberately tiny — enough to verify an API
key, enumerate the platform's lists/audiences, and move contacts in both
directions. New providers are added with a single adapter file; the long-tail
is covered by the generic HTTP connector.

These adapters make real HTTP calls and return normalized dataclasses. They
hold no database state — the service layer owns persistence, encryption, and
audit logging."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from app.core.exceptions import AdVantaError


class AutoresponderError(AdVantaError):
    """Upstream provider returned an unexpected/error response."""

    status_code = 502
    code = "autoresponder_error"


class AutoresponderAuthError(AdVantaError):
    """Supplied API key / credentials were rejected by the provider."""

    status_code = 401
    code = "autoresponder_auth_failed"


class AutoresponderNotSupportedError(AdVantaError):
    """Operation isn't supported by this provider (e.g. listing audiences on a
    tag-based platform with no enumeration endpoint)."""

    status_code = 501
    code = "autoresponder_not_supported"


@dataclass
class ConfigField:
    """Describes one connection-form field the UI should render (beyond the API
    key, which is handled generically)."""

    key: str
    label: str
    type: str = "text"  # text | password | url
    required: bool = True
    placeholder: str | None = None
    help_text: str | None = None


@dataclass
class AutoresponderAccountInfo:
    account_id: str | None
    display_name: str | None


@dataclass
class Audience:
    """A list / segment / tag the workspace can push to or pull from."""

    external_id: str
    name: str
    member_count: int | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Contact:
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    tags: list[str] = field(default_factory=list)
    custom_fields: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    def is_addressable(self) -> bool:
        return bool(self.email or self.phone)


@dataclass
class PushResult:
    requested: int
    succeeded: int
    failed: int
    errors: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class AutoresponderAdapter:
    """Provider interface. Subclasses set the class-level metadata and override
    the operations they support."""

    provider_id: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str]

    # The API key is collected generically; `config_fields` declares any
    # additional connection settings (store id, base URL, …).
    requires_api_key: ClassVar[bool] = True
    api_key_label: ClassVar[str] = "API key"
    api_key_help: ClassVar[str | None] = None
    config_fields: ClassVar[list[ConfigField]] = []

    # Capability flags consumed by the UI so it can render the right controls
    # (a dropdown of audiences vs. a free-text list/tag field, etc.).
    supports_audience_listing: ClassVar[bool] = True
    supports_contact_pull: ClassVar[bool] = True
    # When True, the audience id is a free-text value (tag name, list slug)
    # the user types rather than picking from a fetched list.
    freeform_audience: ClassVar[bool] = False

    docs_url: ClassVar[str | None] = None

    # ------------------------------------------------------------------
    # Operations — override per provider.
    # ------------------------------------------------------------------

    @classmethod
    def verify(cls, *, api_key: str | None, config: dict) -> AutoresponderAccountInfo:
        """Validate credentials. Raise AutoresponderAuthError on bad keys."""
        raise AutoresponderNotSupportedError(
            f"{cls.display_name} does not implement verify()."
        )

    @classmethod
    def list_audiences(cls, *, api_key: str | None, config: dict) -> list[Audience]:
        """Enumerate lists/segments. Default empty for tag-based providers."""
        return []

    @classmethod
    def push_contacts(
        cls,
        *,
        api_key: str | None,
        config: dict,
        audience_id: str | None,
        contacts: list[Contact],
    ) -> PushResult:
        raise AutoresponderNotSupportedError(
            f"{cls.display_name} does not support pushing contacts."
        )

    @classmethod
    def pull_contacts(
        cls,
        *,
        api_key: str | None,
        config: dict,
        audience_id: str | None,
        limit: int,
    ) -> list[Contact]:
        raise AutoresponderNotSupportedError(
            f"{cls.display_name} does not support pulling contacts."
        )

    # ------------------------------------------------------------------
    # Catalog entry for the connect UI.
    # ------------------------------------------------------------------

    @classmethod
    def catalog_entry(cls) -> dict:
        return {
            "provider": cls.provider_id,
            "display_name": cls.display_name,
            "description": cls.description,
            "requires_api_key": cls.requires_api_key,
            "api_key_label": cls.api_key_label,
            "api_key_help": cls.api_key_help,
            "config_fields": [
                {
                    "key": f.key,
                    "label": f.label,
                    "type": f.type,
                    "required": f.required,
                    "placeholder": f.placeholder,
                    "help_text": f.help_text,
                }
                for f in cls.config_fields
            ],
            "supports_audience_listing": cls.supports_audience_listing,
            "supports_contact_pull": cls.supports_contact_pull,
            "freeform_audience": cls.freeform_audience,
            "docs_url": cls.docs_url,
        }
