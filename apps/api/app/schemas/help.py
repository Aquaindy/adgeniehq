from pydantic import BaseModel


class HelpTopicSummary(BaseModel):
    id: str
    category: str
    title: str
    summary: str
    order: int


class HelpTopicDetail(HelpTopicSummary):
    body_markdown: str
    # Whether platform ElevenLabs narration is configured (drives the Audio tab).
    audio_supported: bool


class HelpAudioStatusResponse(BaseModel):
    # none | generating | ready | failed | unavailable
    status: str
    url: str | None = None
