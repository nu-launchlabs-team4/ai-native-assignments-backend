"""SQLAlchemy models for submissions.

A Submission is one student's full trail for one assignment. StepEntry holds
one answer per question for the attempt and the revision, so both versions
are kept. The evaluation, interview answers and AI declaration live on the
submission itself.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.assignments.models import Assignment, enum_column
from app.core.constants import EvaluationVerdict, Step, SubmissionStatus
from app.core.database import Base


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        # One submission per student per assignment.
        UniqueConstraint("assignment_id", "student_id"),
        CheckConstraint("confidence BETWEEN 1 AND 5", name="ck_submissions_confidence_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    # The Supabase Auth user id, the same id get_current_user returns.
    student_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[SubmissionStatus] = mapped_column(
        enum_column(SubmissionStatus), default=SubmissionStatus.IN_PROGRESS
    )
    current_step: Mapped[Step] = mapped_column(enum_column(Step), default=Step.ATTEMPT)

    # Attempt step: asked before the AI unlocks.
    confidence: Mapped[int | None] = mapped_column(SmallInteger)
    approach_note: Mapped[str | None] = mapped_column(Text)
    # Set when the attempt is in. The AI chat stays locked until then.
    attempt_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Evaluate step.
    evaluation_verdict: Mapped[EvaluationVerdict | None] = mapped_column(
        enum_column(EvaluationVerdict)
    )
    evaluation_test_case: Mapped[str | None] = mapped_column(Text)

    # Explain step: a list of {"question": ..., "answer": ...}.
    interview_answers: Mapped[list[dict[str, str]] | None] = mapped_column(JSON)
    ai_declaration: Mapped[str | None] = mapped_column(Text)

    # The AI summary for the professor. Filled in by a later issue.
    summary: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assignment: Mapped[Assignment] = relationship()
    entries: Mapped[list["StepEntry"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def attempt_answers(self) -> dict[uuid.UUID, str]:
        return self.answers_for(Step.ATTEMPT)

    @property
    def revision_answers(self) -> dict[uuid.UUID, str]:
        return self.answers_for(Step.REVISE)

    def answers_for(self, step: Step) -> dict[uuid.UUID, str]:
        """This step's answers keyed by question id."""
        return {entry.question_id: entry.content for entry in self.entries if entry.step == step}


class StepEntry(Base):
    """One answer to one question in one step (attempt or revise).

    Answers are plain text: code as written, written answers as plain text,
    and math as LaTeX lines separated by newlines.
    """

    __tablename__ = "step_entries"
    __table_args__ = (UniqueConstraint("submission_id", "step", "question_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[Step] = mapped_column(enum_column(Step))
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    submission: Mapped[Submission] = relationship(back_populates="entries")
