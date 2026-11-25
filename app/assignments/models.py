"""SQLAlchemy models for assignments.

Course, Assignment and Question. An assignment holds the AI settings
(ai_policy, help_level, final_check) and an ordered list of questions.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.assignments.join_codes import JOIN_CODE_LENGTH
from app.core.constants import AIPolicy, AnswerType, FinalCheck, HelpLevel
from app.core.database import Base

ENUM_LENGTH = 32


def enum_column(enum_class: type[StrEnum]) -> Enum:
    """Store an enum as its value in a plain VARCHAR column.

    Not a native Postgres enum, so adding a new value later needs no ALTER TYPE.
    """
    return Enum(
        enum_class,
        native_enum=False,
        length=ENUM_LENGTH,
        values_callable=lambda members: [member.value for member in members],
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    # The Supabase Auth user id (the JWT "sub"), the same id get_current_user returns.
    professor_id: Mapped[uuid.UUID] = mapped_column(index=True)
    # What the professor shares so students can join (see join_codes.py). Only they see it.
    join_code: Mapped[str] = mapped_column(String(JOIN_CODE_LENGTH), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Enrollment(Base):
    """A student in a course. Students see the course's published assignments."""

    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "student_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    # The Supabase Auth user id, like submissions.student_id.
    student_id: Mapped[uuid.UUID] = mapped_column(index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course: Mapped[Course] = relationship()


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text, default="")
    # Storage path of the uploaded PDF. Set by the PDF upload feature.
    source_pdf: Mapped[str | None] = mapped_column(String(500))
    ai_policy: Mapped[AIPolicy] = mapped_column(enum_column(AIPolicy))
    help_level: Mapped[HelpLevel] = mapped_column(enum_column(HelpLevel))
    final_check: Mapped[FinalCheck] = mapped_column(enum_column(FinalCheck))
    # Null while the assignment is a draft that students can't see.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course: Mapped[Course] = relationship(back_populates="assignments")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        order_by="Question.position",
        lazy="selectin",
    )


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("assignment_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    # 1-based order within the assignment.
    position: Mapped[int]
    prompt: Mapped[str] = mapped_column(Text)
    answer_type: Mapped[AnswerType] = mapped_column(enum_column(AnswerType))
    # Only code questions have a language (a Monaco language id such as "python").
    language: Mapped[str | None] = mapped_column(String(32))
    starter_code: Mapped[str | None] = mapped_column(Text)

    assignment: Mapped[Assignment] = relationship(back_populates="questions")
