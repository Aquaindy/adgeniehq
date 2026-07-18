"""ElevenLabs text-to-speech adapter.

Synthesizes narration audio (MP3) from article text using a PLATFORM ElevenLabs
key — this powers the built-in Help/Knowledge-Base "Audio" tab, so the content
is AdGenieHQ's own and the platform key is correct (not a per-workspace BYO
key). ElevenLabs authenticates with a single API key sent as the ``xi-api-key``
header.

Docs: https://elevenlabs.io/docs/api-reference/text-to-speech
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.exceptions import AdGenieError

API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsError(AdGenieError):
    status_code = 502
    code = "elevenlabs_error"


class ElevenLabsNotConfiguredError(AdGenieError):
    status_code = 503
    code = "elevenlabs_not_configured"


@dataclass
class AudioResult:
    """Synthesized audio bytes + their content type (mirrors the shape of the
    LLM client's ImageResult so callers store binaries the same way)."""

    audio_bytes: bytes
    content_type: str = "audio/mpeg"


def is_configured() -> bool:
    """TTS is usable only with both a platform API key and a default voice id."""
    return bool(settings.elevenlabs_api_key and settings.elevenlabs_default_voice_id)


def _headers(api_key: str) -> dict[str, str]:
    return {"xi-api-key": api_key, "Content-Type": "application/json"}


def synthesize(
    text: str,
    *,
    voice_id: str | None = None,
    model: str | None = None,
) -> AudioResult:
    """Synthesize `text` to MP3 via ElevenLabs and return the raw bytes.

    Raises ElevenLabsNotConfiguredError when the platform key/voice is unset, and
    ElevenLabsError on any API/transport failure."""
    api_key = settings.elevenlabs_api_key
    voice = voice_id or settings.elevenlabs_default_voice_id
    if not api_key or not voice:
        raise ElevenLabsNotConfiguredError(
            "ElevenLabs is not configured (set ELEVENLABS_API_KEY + "
            "ELEVENLABS_DEFAULT_VOICE_ID)."
        )
    if not text.strip():
        raise ElevenLabsError("Cannot synthesize empty text.")

    body = {
        "text": text,
        "model_id": model or settings.elevenlabs_model,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    try:
        resp = httpx.post(
            f"{API_BASE}/text-to-speech/{voice}",
            headers=_headers(api_key),
            json=body,
            timeout=settings.tts_http_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise ElevenLabsError(f"Could not reach ElevenLabs: {exc}") from exc
    if resp.status_code >= 400:
        raise ElevenLabsError(
            f"ElevenLabs synthesis failed: HTTP {resp.status_code} {resp.text[:200]}"
        )
    return AudioResult(audio_bytes=resp.content, content_type="audio/mpeg")
