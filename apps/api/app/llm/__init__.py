"""LLM client abstraction.

Skills that need a generative model call `get_llm_client()` (env-default) or
`get_llm_client_for_workspace(db, ws_id)` (BYOK-aware) and use the same
`complete()` / `complete_metered()` / `complete_json()` interface — provider-
agnostic, trivially mockable in tests.

Implementations:
  * OpenAIClient — real, talks to the chat-completions API (also works against
    any OpenAI-compatible base_url such as Azure / self-hosted gateways).
  * AnthropicClient — Claude Messages API. Default model: claude-sonnet-4-6.
  * GoogleAIClient — Gemini generateContent API.
  * NullClient — used when no API key is configured. Refuses to fabricate
    text, surfacing a clear error so the caller can fall back to a
    deterministic template instead of pretending it generated something.
"""

from app.llm.client import (
    AnthropicClient,
    GoogleAIClient,
    ImageResult,
    LlmClient,
    LlmError,
    LlmMessage,
    LlmNotConfiguredError,
    NullClient,
    OpenAIClient,
    get_llm_client,
    get_llm_client_for_workspace,
)

__all__ = [
    "AnthropicClient",
    "GoogleAIClient",
    "ImageResult",
    "LlmClient",
    "LlmError",
    "LlmMessage",
    "LlmNotConfiguredError",
    "NullClient",
    "OpenAIClient",
    "get_llm_client",
    "get_llm_client_for_workspace",
]
