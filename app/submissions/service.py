"""Business logic for submissions. Routes call these functions and stay thin.

The server enforces the step order: attempt, then feedback and evaluate,
then revise, then explain. Answers can only change in their own step, so
the attempt is frozen once the AI has seen it.
"""

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.assignments.models import Assignment, Course, Enrollment
from app.core.constants import Step, SubmissionStatus
from app.core.security import CurrentUser
from app.submissions.models import StepEntry, Submission
from app.submissions.schemas import (
    AnswerMap,
    AttemptFinish,
    EvaluationSave,
    ExplanationSave,
    StudentAssignmentOut,
    SubmissionOut,
)

logger = logging.getLogger(__name__)

ASSIGNMENT_NOT_FOUND = "Assignment not found"
SUBMISSION_NOT_FOUND = "Submission not found"
ALREADY_SUBMITTED = "This submission is already submitted"
UNKNOWN_QUESTION = "An answer is for a question that isn't in this assignment"
UNANSWERED = "Answer every question before moving on"
# A literal, because Starlette is renaming its 422 constant.
HTTP_UNPROCESSABLE = 422


def start_submission(
    db: Session, student: CurrentUser, assignment_id: uuid.UUID
) -> tuple[SubmissionOut, bool]:
    """Start this student's submission, or return the one they already have.

    Returns the submission and whether it was just created.
    """
    assignment = db.scalar(
        select(Assignment).where(
            Assignment.id == assignment_id, Assignment.published_at.is_not(None)
        )
    )
    if assignment is None:
        # Drafts are hidden from students, so they get the same 404 as a wrong id.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=ASSIGNMENT_NOT_FOUND)

    student_id = _user_uuid(student)
    existing = _find_submission(db, assignment.id, student_id)
    if existing is not None:
        return SubmissionOut.model_validate(existing), False

    submission = Submission(assignment_id=assignment.id, student_id=student_id)
    db.add(submission)
    try:
        db.commit()
    except IntegrityError:
        # Two requests raced to start it, such as two open tabs. Use the winner's.
        db.rollback()
        existing = _find_submission(db, assignment.id, student_id)
        if existing is None:
            raise
        return SubmissionOut.model_validate(existing), False
    db.refresh(submission)
    logger.info("Submission started submission_id=%s", submission.id)
    return SubmissionOut.model_validate(submission), True


def get_submission(db: Session, student: CurrentUser, submission_id: uuid.UUID) -> SubmissionOut:
    return SubmissionOut.model_validate(_get_owned(db, student, submission_id))


def save_answers(
    db: Session,
    student: CurrentUser,
    submission_id: uuid.UUID,
    step: Step,
    answers: AnswerMap,
) -> SubmissionOut:
    """Save draft answers for the attempt or the revision. Only the sent questions change."""
    submission = _get_owned(db, student, submission_id)
    _require_step(submission, step)
    _check_question_ids(submission, answers.keys())
    _upsert_answers(submission, step, answers)
    db.commit()
    db.refresh(submission)
    return SubmissionOut.model_validate(submission)


def finish_attempt(
    db: Session, student: CurrentUser, submission_id: uuid.UUID, body: AttemptFinish
) -> SubmissionOut:
    """Hand in the attempt with the confidence rating and approach note. This unlocks the AI."""
    submission = _get_owned(db, student, submission_id)
    _require_step(submission, Step.ATTEMPT)
    _require_every_question_answered(submission, Step.ATTEMPT)
    submission.confidence = body.confidence
    submission.approach_note = body.approach_note
    submission.attempt_submitted_at = datetime.now(UTC)
    submission.current_step = Step.FEEDBACK
    db.commit()
    db.refresh(submission)
    logger.info("Attempt submitted submission_id=%s", submission.id)
    return SubmissionOut.model_validate(submission)


def save_evaluation(
    db: Session, student: CurrentUser, submission_id: uuid.UUID, body: EvaluationSave
) -> SubmissionOut:
    """Save the student's judgement of the AI feedback and move on to the revision."""
    submission = _get_owned(db, student, submission_id)
    _require_step(submission, Step.FEEDBACK, Step.EVALUATE)
    submission.evaluation_verdict = body.verdict
    submission.evaluation_test_case = body.test_case
    # The revision starts as a copy of the attempt. The attempt itself stays as it was.
    _upsert_answers(submission, Step.REVISE, submission.answers_for(Step.ATTEMPT))
    submission.current_step = Step.REVISE
    db.commit()
    db.refresh(submission)
    return SubmissionOut.model_validate(submission)


def finish_revision(db: Session, student: CurrentUser, submission_id: uuid.UUID) -> SubmissionOut:
    """Hand in the revision and move on to the explain step."""
    submission = _get_owned(db, student, submission_id)
    _require_step(submission, Step.REVISE)
    _require_every_question_answered(submission, Step.REVISE)
    submission.current_step = Step.EXPLAIN
    db.commit()
    db.refresh(submission)
    return SubmissionOut.model_validate(submission)


def save_explanation(
    db: Session, student: CurrentUser, submission_id: uuid.UUID, body: ExplanationSave
) -> SubmissionOut:
    """Save the interview answers and AI declaration, and submit."""
    submission = _get_owned(db, student, submission_id)
    _require_step(submission, Step.EXPLAIN)
    submission.interview_answers = [answer.model_dump() for answer in body.interview_answers]
    submission.ai_declaration = body.ai_declaration
    submission.status = SubmissionStatus.SUBMITTED
    submission.submitted_at = datetime.now(UTC)
    db.commit()
    db.refresh(submission)
    logger.info("Submission submitted submission_id=%s", submission.id)
    return SubmissionOut.model_validate(submission)


def list_student_assignments(db: Session, student: CurrentUser) -> list[StudentAssignmentOut]:
    """Published assignments in the student's courses, newest first, with their progress."""
    student_id = _user_uuid(student)
    rows = db.execute(
        select(Assignment, Course.title, Submission)
        .join(Course, Course.id == Assignment.course_id)
        .join(
            Enrollment,
            (Enrollment.course_id == Assignment.course_id) & (Enrollment.student_id == student_id),
        )
        .outerjoin(
            Submission,
            (Submission.assignment_id == Assignment.id) & (Submission.student_id == student_id),
        )
        .where(Assignment.published_at.is_not(None))
        .order_by(Assignment.published_at.desc(), Assignment.id)
    )
    return [
        StudentAssignmentOut(
            id=assignment.id,
            title=assignment.title,
            course_id=assignment.course_id,
            course_title=course_title,
            published_at=assignment.published_at,
            submission_id=submission.id if submission else None,
            status=submission.status if submission else None,
            current_step=submission.current_step if submission else None,
        )
        for assignment, course_title, submission in rows
    ]


def _find_submission(
    db: Session, assignment_id: uuid.UUID, student_id: uuid.UUID
) -> Submission | None:
    return db.scalar(
        select(Submission).where(
            Submission.assignment_id == assignment_id, Submission.student_id == student_id
        )
    )


def _get_owned(db: Session, student: CurrentUser, submission_id: uuid.UUID) -> Submission:
    # Another student's submission is a 404, not a 403, so ids can't be probed.
    submission = db.scalar(
        select(Submission).where(
            Submission.id == submission_id, Submission.student_id == _user_uuid(student)
        )
    )
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SUBMISSION_NOT_FOUND)
    return submission


def _require_step(submission: Submission, *steps: Step) -> None:
    if submission.status == SubmissionStatus.SUBMITTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_SUBMITTED)
    if submission.current_step not in steps:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Not allowed in the {submission.current_step} step",
        )


def _check_question_ids(submission: Submission, question_ids: Iterable[uuid.UUID]) -> None:
    known = {question.id for question in submission.assignment.questions}
    if not set(question_ids) <= known:
        raise HTTPException(status_code=HTTP_UNPROCESSABLE, detail=UNKNOWN_QUESTION)


def _require_every_question_answered(submission: Submission, step: Step) -> None:
    answers = submission.answers_for(step)
    for question in submission.assignment.questions:
        if not answers.get(question.id, "").strip():
            raise HTTPException(status_code=HTTP_UNPROCESSABLE, detail=UNANSWERED)


def _upsert_answers(submission: Submission, step: Step, answers: dict[uuid.UUID, str]) -> None:
    existing = {entry.question_id: entry for entry in submission.entries if entry.step == step}
    for question_id, content in answers.items():
        entry = existing.get(question_id)
        if entry is None:
            submission.entries.append(
                StepEntry(step=step, question_id=question_id, content=content)
            )
        else:
            entry.content = content


def _user_uuid(user: CurrentUser) -> uuid.UUID:
    # Supabase Auth user ids are UUIDs; CurrentUser keeps them as strings.
    return uuid.UUID(user.id)
