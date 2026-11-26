"""Pydantic request and response schemas for sessions."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import MAX_EVENTS_PER_BATCH, ActivityEventType, Step

# The events the browser may send. Snapshots are recorded by the backend itself.
BrowserEventType = Literal[
    ActivityEventType.PASTE, ActivityEventType.TAB_LEAVE, ActivityEventType.TAB_RETURN
]


class PasteDetail(BaseModel):
    # Only the size of a paste is kept, never its text.
    characters: int = Field(ge=0, le=10_000_000)


class ActivityEventIn(BaseModel):
    type: BrowserEventType
    step: Step
    question_id: uuid.UUID | None = None
    occurred_at: datetime
    detail: PasteDetail | None = None

    @model_validator(mode="after")
    def check_detail(self) -> Self:
        if self.type == ActivityEventType.PASTE and self.detail is None:
            raise ValueError("A paste event needs detail.characters")
        if self.type != ActivityEventType.PASTE and self.detail is not None:
            raise ValueError("Only paste events have detail")
        return self


class ActivityEventsIn(BaseModel):
    events: list[ActivityEventIn] = Field(min_length=1, max_length=MAX_EVENTS_PER_BATCH)


class WorkSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None


# The professor's timeline. Field names match the frontend's session-types.ts.


class ActivityEventOut(BaseModel):
    id: uuid.UUID
    type: ActivityEventType
    step: Step
    question_id: uuid.UUID | None
    # When it happened.
    created_at: datetime
    # paste: {"characters": n}. snapshot: {"question_ids": [...]}, the answers that changed.
    detail: dict[str, object] | None


class StepSegmentOut(BaseModel):
    step: Step
    started_at: datetime
    ended_at: datetime


class WorkSessionDetailOut(BaseModel):
    id: uuid.UUID
    started_at: datetime
    ended_at: datetime | None
    segments: list[StepSegmentOut]
    events: list[ActivityEventOut]


class SubmissionSessionsOut(BaseModel):
    submission_id: uuid.UUID
    assignment_title: str
    # The student's email until accounts have names.
    student_name: str
    sessions: list[WorkSessionDetailOut]
