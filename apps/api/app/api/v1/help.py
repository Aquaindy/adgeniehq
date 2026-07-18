"""Help / Knowledge-Base API.

Content is GLOBAL (platform-level), so these routes require a logged-in user but
are NOT workspace-scoped. Audio narration is generated once per article via the
platform ElevenLabs key and cached for everyone (generate-on-first-play).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.exceptions import AdGenieError
from app.db.session import get_db
from app.integrations import elevenlabs
from app.models.user import User
from app.schemas.help import (
    HelpAudioStatusResponse,
    HelpTopicDetail,
    HelpTopicSummary,
)
from app.security.dependencies import get_current_user
from app.services import help_service

router = APIRouter()


class HelpTopicNotFoundError(AdGenieError):
    status_code = 404
    code = "help_topic_not_found"


@router.get("/help/topics", response_model=list[HelpTopicSummary])
def list_help_topics(
    _user: User = Depends(get_current_user),
) -> list[HelpTopicSummary]:
    return [
        HelpTopicSummary(
            id=t.id, category=t.category, title=t.title, summary=t.summary, order=t.order
        )
        for t in help_service.list_topics()
    ]


@router.get("/help/topics/{topic_id}", response_model=HelpTopicDetail)
def get_help_topic(
    topic_id: str,
    _user: User = Depends(get_current_user),
) -> HelpTopicDetail:
    topic = help_service.get_topic(topic_id)
    if topic is None:
        raise HelpTopicNotFoundError(f"Unknown help topic: {topic_id}.")
    return HelpTopicDetail(
        id=topic.id,
        category=topic.category,
        title=topic.title,
        summary=topic.summary,
        order=topic.order,
        body_markdown=topic.body_markdown,
        audio_supported=elevenlabs.is_configured(),
    )


@router.get("/help/topics/{topic_id}/audio", response_model=HelpAudioStatusResponse)
def get_help_audio(
    topic_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HelpAudioStatusResponse:
    return HelpAudioStatusResponse(**help_service.get_audio_status(db, topic_id=topic_id))


@router.post(
    "/help/topics/{topic_id}/audio",
    response_model=HelpAudioStatusResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_help_audio(
    topic_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HelpAudioStatusResponse:
    return HelpAudioStatusResponse(**help_service.start_audio(db, topic_id=topic_id))
