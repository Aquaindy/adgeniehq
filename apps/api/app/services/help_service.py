"""Help / Knowledge-Base service.

Serves the built-in help articles (global, platform-level) and manages
generate-on-first-play ElevenLabs narration. Audio is cached globally by
(topic_id, content_hash, voice_id) — generated once, served to everyone after.
When the platform ElevenLabs key is unset, audio degrades to an "unavailable"
state (the UI shows "coming soon") instead of failing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.help import content as help_content
from app.integrations import elevenlabs
from app.models.help_audio_asset import HelpAudioAsset, HelpAudioStatus
from app.services import object_storage

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


def list_topics() -> list[help_content.HelpTopic]:
    return help_content.list_topics()


def get_topic(topic_id: str) -> help_content.HelpTopic | None:
    return help_content.get_topic(topic_id)


# ---------------------------------------------------------------------------
# Audio (generate-on-first-play + cache)
# ---------------------------------------------------------------------------


def _find_asset(db: Session, *, topic_id: str, content_hash: str, voice_id: str):
    return (
        db.query(HelpAudioAsset)
        .filter(
            HelpAudioAsset.topic_id == topic_id,
            HelpAudioAsset.content_hash == content_hash,
            HelpAudioAsset.voice_id == voice_id,
        )
        .first()
    )


def _status_payload(asset: HelpAudioAsset | None, *, configured: bool) -> dict[str, Any]:
    if asset is None:
        return {"status": "unavailable" if not configured else "none", "url": None}
    return {"status": asset.status.value, "url": asset.url}


def get_audio_status(db: Session, *, topic_id: str) -> dict[str, Any]:
    """Report the current audio state for a topic without starting generation."""
    topic = help_content.get_topic(topic_id)
    if topic is None:
        return {"status": "unavailable", "url": None}
    configured = elevenlabs.is_configured()
    if not configured:
        return {"status": "unavailable", "url": None}
    asset = _find_asset(
        db,
        topic_id=topic_id,
        content_hash=topic.content_hash(),
        voice_id=settings.elevenlabs_default_voice_id,
    )
    return _status_payload(asset, configured=configured)


def start_audio(db: Session, *, topic_id: str) -> dict[str, Any]:
    """Return cached audio if present, else kick off generation and report
    'generating'. Returns 'unavailable' when TTS isn't configured."""
    topic = help_content.get_topic(topic_id)
    if topic is None:
        return {"status": "unavailable", "url": None}
    if not elevenlabs.is_configured():
        return {"status": "unavailable", "url": None}

    content_hash = topic.content_hash()
    voice_id = settings.elevenlabs_default_voice_id

    asset = _find_asset(db, topic_id=topic_id, content_hash=content_hash, voice_id=voice_id)
    if asset is not None and asset.status in (
        HelpAudioStatus.READY,
        HelpAudioStatus.GENERATING,
    ):
        return _status_payload(asset, configured=True)

    if asset is None:
        asset = HelpAudioAsset(
            topic_id=topic_id,
            content_hash=content_hash,
            voice_id=voice_id,
            status=HelpAudioStatus.GENERATING,
        )
        db.add(asset)
        try:
            db.commit()
        except IntegrityError:
            # A concurrent request created the row first — reuse it.
            db.rollback()
            asset = _find_asset(
                db, topic_id=topic_id, content_hash=content_hash, voice_id=voice_id
            )
            if asset is not None:
                return _status_payload(asset, configured=True)
    else:
        # A previously FAILED row — retry it.
        asset.status = HelpAudioStatus.GENERATING
        asset.error = None
        db.commit()

    # Dispatch generation (runs inline when workers are disabled).
    from app.workers.dispatch import run_or_dispatch
    from app.workers.tasks import generate_help_audio_task

    run_or_dispatch(generate_help_audio_task, topic_id=topic_id)

    db.refresh(asset)
    return _status_payload(asset, configured=True)


def generate_audio(db: Session, *, topic_id: str) -> None:
    """Synthesize + store a topic's narration MP3 and mark the asset READY.
    Idempotent: if the asset is already READY, does nothing. Called by the
    Celery task (or inline when workers are off)."""
    topic = help_content.get_topic(topic_id)
    if topic is None:
        return
    content_hash = topic.content_hash()
    voice_id = settings.elevenlabs_default_voice_id
    asset = _find_asset(db, topic_id=topic_id, content_hash=content_hash, voice_id=voice_id)
    if asset is None or asset.status == HelpAudioStatus.READY:
        return

    try:
        result = elevenlabs.synthesize(topic.narration(), voice_id=voice_id)
        key = f"help-audio/{topic_id}/{content_hash}-{voice_id}.mp3"
        url = object_storage.put_object(
            key=key, data=result.audio_bytes, content_type=result.content_type
        )
        asset.url = url
        asset.status = HelpAudioStatus.READY
        asset.error = None
    except Exception as exc:  # noqa: BLE001 — record the failure, don't crash the worker
        log.warning("help.audio.generate_failed", topic_id=topic_id, error=str(exc))
        asset.status = HelpAudioStatus.FAILED
        asset.error = str(exc)[:500]
    db.commit()
