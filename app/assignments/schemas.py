"""Pydantic request and response schemas for assignments."""

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.constants import AIPolicy, AnswerType, FinalCheck, HelpLevel

MAX_QUESTIONS = 100
# Caps for text the PDF parser fills in automatically, so one huge PDF can't bloat a row.
MAX_PROMPT_CHARS = 10_000
MAX_STARTER_CODE_CHARS = 50_000
MAX_INSTRUCTIONS_CHARS = 20_000


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class CourseOut(BaseModel):
    """A course as its professor sees it, with the code students join with."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    join_code: str
    student_count: int = 0
    created_at: datetime


class JoinCourseIn(BaseModel):
    # Generous: students may type spaces or leave out the dash (see normalize_join_code).
    code: str = Field(min_length=4, max_length=32)


class EnrollmentOut(BaseModel):
    """The course a student joined. It never includes the join code."""

    course_id: uuid.UUID
    course_title: str
    joined_at: datetime


class QuestionCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    answer_type: AnswerType
    language: str | None = Field(default=None, min_length=1, max_length=32)
    starter_code: str | None = Field(default=None, max_length=MAX_STARTER_CODE_CHARS)

    @model_validator(mode="after")
    def check_language(self) -> Self:
        if self.answer_type == AnswerType.CODE and self.language is None:
            raise ValueError("Code questions need a language, such as python")
        if self.answer_type != AnswerType.CODE and self.language is not None:
            raise ValueError("Only code questions have a language")
        return self


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    prompt: str
    answer_type: AnswerType
    language: str | None
    starter_code: str | None


class AssignmentCreate(BaseModel):
    course_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=MAX_INSTRUCTIONS_CHARS)
    ai_policy: AIPolicy = AIPolicy.PERMITTED
    help_level: HelpLevel = HelpLevel.HINTS
    final_check: FinalCheck = FinalCheck.AI_INTERVIEW
    # Questions are saved in the order given here.
    questions: list[QuestionCreate] = Field(min_length=1, max_length=MAX_QUESTIONS)


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    instructions: str
    source_pdf: str | None
    ai_policy: AIPolicy
    help_level: HelpLevel
    final_check: FinalCheck
    published_at: datetime | None
    created_at: datetime
    questions: list[QuestionOut]
