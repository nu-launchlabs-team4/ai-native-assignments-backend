"""SQLAlchemy models for sessions.

A work session is a stretch of a student's work on one submission. Its activity
events (pastes, leaving and returning to the tab, and answer snapshots) give the
professor context when reviewing. They are never used as flags or scores.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.assignments.models import enum_column
from app.core.constants import ActivityEventType, Step
from app.core.database import Base


class WorkSession(Base):
    __tablename__ = "work_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # None while the session is open.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list["ActivityEvent"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ActivityEvent.occurred_at",
    )


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("work_sessions.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[ActivityEventType] = mapped_column(enum_column(ActivityEventType))
    step: Mapped[Step] = mapped_column(enum_column(Step))
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL")
    )
    # When it happened in the browser (or, for snapshots, on the server).
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # paste: {"characters": n}. snapshot: {"answers": {question_id: text}}. Never pasted text.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    session: Mapped[WorkSession] = relationship(back_populates="events")
