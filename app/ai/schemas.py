"""Request and response schemas for AI chat."""

import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """A student message sent to the AI tutor."""

    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    """The AI tutor reply and its stored message ID."""

    message_id: uuid.UUID
    reply: str
