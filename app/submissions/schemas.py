"""Pydantic request and response schemas for submissions."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.assignments.schemas import MAX_QUESTIONS, AssignmentOut
from app.core.constants import EvaluationVerdict, Step, SubmissionStatus

MAX_ANSWER_CHARS = 50_000
MAX_APPROACH_NOTE_CHARS = 1_000
MAX_TEST_CASE_CHARS = 10_000
MAX_INTERVIEW_QUESTION_CHARS = 2_000
MAX_INTERVIEW_ANSWER_CHARS = 10_000
MAX_INTERVIEW_ANSWERS = 10
MAX_AI_DECLARATION_CHARS = 5_000

Answer = Annotated[str, Field(max_length=MAX_ANSWER_CHARS)]
# Answers keyed by question id. Code as written, text as plain text,
# math as LaTeX lines separated by "\n".
AnswerMap = Annotated[dict[uuid.UUID, Answer], Field(max_length=MAX_QUESTIONS)]


class SubmissionStart(BaseModel):
    assignment_id: uuid.UUID


class AnswersSave(BaseModel):
    """A draft save. Only the questions sent are changed, so autosave can send just one."""

    answers: AnswerMap


class AttemptFinish(BaseModel):
    confidence: int = Field(ge=1, le=5)
    approach_note: str = Field(min_length=1, max_length=MAX_APPROACH_NOTE_CHARS)


class EvaluationSave(BaseModel):
    verdict: EvaluationVerdict
    test_case: str = Field(min_length=1, max_length=MAX_TEST_CASE_CHARS)


class InterviewAnswer(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_INTERVIEW_QUESTION_CHARS)
    answer: str = Field(min_length=1, max_length=MAX_INTERVIEW_ANSWER_CHARS)


class ExplanationSave(BaseModel):
    interview_answers: list[InterviewAnswer] = Field(min_length=1, max_length=MAX_INTERVIEW_ANSWERS)
    ai_declaration: str = Field(min_length=1, max_length=MAX_AI_DECLARATION_CHARS)


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assignment_id: uuid.UUID
    status: SubmissionStatus
    current_step: Step
    confidence: int | None
    approach_note: str | None
    attempt_submitted_at: datetime | None
    evaluation_verdict: EvaluationVerdict | None
    evaluation_test_case: str | None
    interview_answers: list[InterviewAnswer] | None
    ai_declaration: str | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    attempt_answers: dict[uuid.UUID, str]
    revision_answers: dict[uuid.UUID, str]
    # The assignment and its questions, so the workspace needs one request.
    assignment: AssignmentOut


class StudentAssignmentOut(BaseModel):
    """A published assignment in one of the student's courses, with their progress on it."""

    id: uuid.UUID
    title: str
    course_id: uuid.UUID
    course_title: str
    published_at: datetime
    # None until the student opens the assignment.
    submission_id: uuid.UUID | None
    status: SubmissionStatus | None
    current_step: Step | None
