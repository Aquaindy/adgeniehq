from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AdVantaError
from app.core.logging import get_logger

log = get_logger(__name__)


class LlmError(AdVantaError):
    status_code = 502
    code = "llm_error"


class LlmNotConfiguredError(AdVantaError):
    status_code = 503
    code = "llm_not_configured"


@dataclass
class LlmMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LlmCompletion:
    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw: dict | None = field(default=None)


@dataclass
class ImageResult:
    url: str
    model: str
    prompt: str
    raw: dict | None = field(default=None)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class LlmClient:
    """Subclasses must implement complete() at minimum."""

    provider_id: str = "abstract"

    def is_configured(self) -> bool:
        return False

    def complete(
        self,
        *,
        messages: list[LlmMessage],
        max_tokens: int = 800,
        temperature: float = 0.4,
    ) -> LlmCompletion:  # pragma: no cover — abstract
        raise NotImplementedError

    def generate_image(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
    ) -> ImageResult:  # pragma: no cover — abstract
        raise NotImplementedError

    def complete_json(
        self,
        *,
        messages: list[LlmMessage],
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        completion = self.complete(
            messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        try:
            return _coerce_json(completion.text)
        except ValueError as exc:
            raise LlmError(f"LLM returned non-JSON output: {exc}") from exc

    def complete_metered(
        self,
        *,
        db,  # Session — typed loosely to keep the LLM module dep-free
        workspace_id,  # UUID
        messages: list[LlmMessage],
        max_tokens: int = 800,
        temperature: float = 0.4,
        purpose: str | None = None,
    ) -> LlmCompletion:
        """Plan-gated wrapper around `complete()`.

        Checks the workspace's LLM token budget first; raises
        PlanLimitExceededError before any external call. After a successful
        completion, persists a usage event with `quantity = total tokens`
        so a subsequent budget check sees the spend.

        Skills that have a deterministic fallback should catch
        PlanLimitExceededError + LlmNotConfiguredError + LlmError and fall
        back rather than failing the request."""

        # Imports are local to avoid a circular dep at module load (services
        # import the llm package; llm shouldn't import services at top level).
        from app.models.usage_event import UsageEventType
        from app.services import billing_service

        billing_service.assert_within_llm_token_limit(
            db, workspace_id=workspace_id
        )
        completion = self.complete(
            messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        # The provider may not return token counts; estimate conservatively
        # from char length so the meter still ticks (~4 chars per token).
        prompt_tokens = completion.prompt_tokens
        if prompt_tokens is None:
            prompt_tokens = sum(len(m.content) for m in messages) // 4
        completion_tokens = completion.completion_tokens
        if completion_tokens is None:
            completion_tokens = max(1, len(completion.text) // 4)
        total = int(prompt_tokens) + int(completion_tokens)
        cost_micros = _estimate_cost_usd_micros(
            model=completion.model,
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
        )
        billing_service.record_usage_event(
            db,
            workspace_id=workspace_id,
            event_type=UsageEventType.LLM_CALL,
            quantity=total,
            metadata={
                "purpose": purpose,
                "model": completion.model,
                "prompt_tokens": int(prompt_tokens),
                "completion_tokens": int(completion_tokens),
                "estimated_cost_usd_micros": cost_micros,
            },
        )
        return completion


# ---------------------------------------------------------------------------
# OpenAI / OpenAI-compatible
# ---------------------------------------------------------------------------


class OpenAIClient(LlmClient):
    provider_id = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.model = model or settings.llm_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        *,
        messages: list[LlmMessage],
        max_tokens: int = 800,
        temperature: float = 0.4,
    ) -> LlmCompletion:
        if not self.is_configured():
            raise LlmNotConfiguredError(
                "OPENAI_API_KEY is not set. Configure it or use a deterministic fallback."
            )
        body = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise LlmError(f"OpenAI request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LlmError(
                f"OpenAI returned HTTP {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise LlmError("OpenAI returned no choices.")
        text = (choices[0].get("message") or {}).get("content") or ""
        usage = payload.get("usage") or {}
        return LlmCompletion(
            text=text.strip(),
            model=payload.get("model") or self.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            raw=payload,
        )

    def generate_image(
        self, *, prompt: str, size: str = "1024x1024"
    ) -> ImageResult:
        if not self.is_configured():
            raise LlmNotConfiguredError(
                "OPENAI_API_KEY is not set; image generation requires it."
            )
        try:
            response = httpx.post(
                f"{self.base_url}/images/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "size": size,
                    "n": 1,
                    "response_format": "url",
                },
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise LlmError(f"OpenAI image request failed: {exc}") from exc
        if response.status_code >= 400:
            raise LlmError(
                f"OpenAI image generation returned HTTP {response.status_code}: {response.text[:200]}"
            )
        body = response.json()
        urls = [d.get("url") for d in (body.get("data") or []) if d.get("url")]
        if not urls:
            raise LlmError("OpenAI image response had no URL.")
        return ImageResult(url=urls[0], model="dall-e-3", prompt=prompt, raw=body)


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------


class AnthropicClient(LlmClient):
    provider_id = "anthropic"

    # Sensible default; the workspace can override at install time.
    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, *, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = "https://api.anthropic.com/v1"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        *,
        messages: list[LlmMessage],
        max_tokens: int = 800,
        temperature: float = 0.4,
    ) -> LlmCompletion:
        if not self.is_configured():
            raise LlmNotConfiguredError("Anthropic credential is not configured.")

        # Anthropic's Messages API splits system messages out into their own
        # field rather than mixing them into the role stream.
        system_parts = [m.content for m in messages if m.role == "system"]
        chat = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

        body: dict[str, Any] = {
            "model": self.model,
            "messages": chat,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)

        try:
            response = httpx.post(
                f"{self.base_url}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise LlmError(f"Anthropic request failed: {exc}") from exc
        if response.status_code >= 400:
            raise LlmError(
                f"Anthropic returned HTTP {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        # content is a list of content blocks; the first text block carries the body.
        text_blocks = [
            b.get("text", "")
            for b in (payload.get("content") or [])
            if b.get("type") == "text"
        ]
        text = ("".join(text_blocks)).strip()
        usage = payload.get("usage") or {}
        return LlmCompletion(
            text=text,
            model=payload.get("model") or self.model,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            raw=payload,
        )


# ---------------------------------------------------------------------------
# Google AI (Gemini)
# ---------------------------------------------------------------------------


class GoogleAIClient(LlmClient):
    provider_id = "google_ai"

    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, *, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        *,
        messages: list[LlmMessage],
        max_tokens: int = 800,
        temperature: float = 0.4,
    ) -> LlmCompletion:
        if not self.is_configured():
            raise LlmNotConfiguredError("Google AI credential is not configured.")

        # Gemini's REST shape: contents = [{role, parts:[{text}]}], with
        # systemInstruction as a separate top-level field. role 'system' isn't
        # valid; map 'assistant' to 'model'.
        system_parts = [m.content for m in messages if m.role == "system"]
        contents: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                continue
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_parts:
            body["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}],
            }

        try:
            response = httpx.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json=body,
                timeout=60.0,
            )
        except httpx.HTTPError as exc:
            raise LlmError(f"Google AI request failed: {exc}") from exc
        if response.status_code >= 400:
            raise LlmError(
                f"Google AI returned HTTP {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            raise LlmError("Google AI returned no candidates.")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = ("".join(p.get("text", "") for p in parts)).strip()
        usage = payload.get("usageMetadata") or {}
        return LlmCompletion(
            text=text,
            model=self.model,
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
            raw=payload,
        )


# ---------------------------------------------------------------------------
# Null client — refuses rather than fabricating
# ---------------------------------------------------------------------------


class NullClient(LlmClient):
    provider_id = "null"

    def is_configured(self) -> bool:
        return False

    def complete(
        self,
        *,
        messages: list[LlmMessage],
        max_tokens: int = 800,
        temperature: float = 0.4,
    ) -> LlmCompletion:
        raise LlmNotConfiguredError(
            "No LLM is configured. Set OPENAI_API_KEY or use a deterministic fallback."
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


_INSTANCE: LlmClient | None = None


def get_llm_client() -> LlmClient:
    """Return the singleton LLM client based on config.

    The instance is cached so unit tests can replace it via
    `llm_module._INSTANCE = FakeClient()` if needed."""

    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE
    provider = (settings.llm_provider or "openai").lower()
    if provider == "openai":
        client: LlmClient = OpenAIClient()
    elif provider == "anthropic":
        client = AnthropicClient(
            api_key=settings.anthropic_api_key or "",
            model=settings.anthropic_model or AnthropicClient.DEFAULT_MODEL,
        )
    elif provider in ("google", "google_ai", "gemini"):
        client = GoogleAIClient(
            api_key=settings.google_ai_api_key or "",
            model=settings.google_ai_model or GoogleAIClient.DEFAULT_MODEL,
        )
    else:
        log.warning("llm.unknown_provider", provider=provider)
        client = NullClient()
    if not client.is_configured():
        log.info("llm.not_configured", provider=provider)
        client = NullClient()
    _INSTANCE = client
    return client


def get_llm_client_for_workspace(db, workspace_id) -> LlmClient:
    """Workspace-aware client lookup.

    Resolution order:
      1. Workspace-saved credential matching the configured `llm_provider`.
      2. Any other workspace-saved credential (most recent active wins).
      3. Env-backed singleton from `get_llm_client()`.

    Falling back to (3) keeps behavior unchanged for workspaces that
    haven't added a BYOK credential yet.
    """

    # Local imports avoid a circular dep at module load (services -> llm).
    from app.models.provider_credential import ProviderCredentialProvider
    from app.services import provider_credentials_service

    creds = provider_credentials_service.get_active_credentials(
        db, workspace_id=workspace_id
    )
    if not creds:
        return get_llm_client()

    # Prefer the credential matching the env-configured provider so a
    # workspace's "OpenAI key" overrides the env's OpenAI key, etc.
    env_provider = (settings.llm_provider or "openai").lower()
    env_match: ProviderCredentialProvider | None = None
    if env_provider == "openai":
        env_match = ProviderCredentialProvider.OPENAI
    elif env_provider == "anthropic":
        env_match = ProviderCredentialProvider.ANTHROPIC
    elif env_provider in ("google", "google_ai", "gemini"):
        env_match = ProviderCredentialProvider.GOOGLE_AI

    if env_match is not None:
        for c in creds:
            if c.provider == env_match:
                return _build_client_for(c)

    # Otherwise fall through to whichever credential was added most recently.
    return _build_client_for(creds[0])


def _build_client_for(cred) -> LlmClient:
    """Build a client instance for a saved credential row."""
    from app.models.provider_credential import ProviderCredentialProvider
    from app.security.encryption import decrypt

    secret = decrypt(cred.encrypted_secret)
    if cred.provider == ProviderCredentialProvider.OPENAI:
        return OpenAIClient(api_key=secret)
    if cred.provider == ProviderCredentialProvider.ANTHROPIC:
        return AnthropicClient(
            api_key=secret,
            model=settings.anthropic_model or AnthropicClient.DEFAULT_MODEL,
        )
    if cred.provider == ProviderCredentialProvider.GOOGLE_AI:
        return GoogleAIClient(
            api_key=secret,
            model=settings.google_ai_model or GoogleAIClient.DEFAULT_MODEL,
        )
    return NullClient()


# Approx $/1k-token pricing (conservative — OpenAI rates as of 2026-01).
# All values in **micros of USD per 1k tokens** so we can store as int.
# Add new models here as they're enabled. Falls back to gpt-4.1-mini rates
# when the model isn't recognized.
_PRICING_USD_MICROS_PER_1K_TOKENS: dict[str, dict[str, int]] = {
    "gpt-4.1": {"input": 5_000, "output": 15_000},
    "gpt-4.1-mini": {"input": 1_500, "output": 6_000},
    "gpt-4o": {"input": 5_000, "output": 15_000},
    "gpt-4o-mini": {"input": 150, "output": 600},
    "claude-3-5-sonnet-20241022": {"input": 3_000, "output": 15_000},
    "claude-3-5-haiku-20241022": {"input": 800, "output": 4_000},
    # Claude 4.x — published rates as of model launch.
    "claude-opus-4-7": {"input": 15_000, "output": 75_000},
    "claude-sonnet-4-6": {"input": 3_000, "output": 15_000},
    "claude-haiku-4-5-20251001": {"input": 1_000, "output": 5_000},
    # Gemini 1.5 — published rates.
    "gemini-1.5-pro": {"input": 1_250, "output": 5_000},
    "gemini-1.5-flash": {"input": 75, "output": 300},
}
_DEFAULT_PRICING = _PRICING_USD_MICROS_PER_1K_TOKENS["gpt-4.1-mini"]


def _estimate_cost_usd_micros(
    *, model: str | None, prompt_tokens: int, completion_tokens: int
) -> int:
    """Conservative cost estimate in micro-USD (1 USD = 1_000_000 micros).
    Stored on the usage_event so /billing surfaces dollar spend without
    re-fetching prices. Returns 0 if both token counts are zero."""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return 0
    rates = _PRICING_USD_MICROS_PER_1K_TOKENS.get(
        (model or "").lower(), _DEFAULT_PRICING
    )
    in_cost = (prompt_tokens * rates["input"]) // 1000
    out_cost = (completion_tokens * rates["output"]) // 1000
    return int(in_cost + out_cost)


def _coerce_json(text: str) -> dict[str, Any]:
    """Strip code fences / leading prose, then json.loads."""

    body = text.strip()
    if body.startswith("```"):
        # ```json\n…\n```
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        body = "\n".join(lines)

    # Some models prepend a sentence then the JSON. Find the first '{'.
    if not body.startswith("{") and "{" in body:
        body = body[body.index("{") :]

    return json.loads(body)
