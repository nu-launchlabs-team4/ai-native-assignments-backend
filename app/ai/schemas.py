"""Request and response schemas for AI chat."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """A student message sent to the AI tutor."""

    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    """The AI tutor reply and its stored message ID."""

    message_id: uuid.UUID
    reply: str


class ChatMessageOut(BaseModel):
    """One saved message: the student's, or the tutor's reply."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["student", "assistant"]
    content: str
    created_at: datetime


class ChatHistoryOut(BaseModel):
    """A submission's conversation with the AI tutor, oldest first."""

    messages: list[ChatMessageOut]
