import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.constants import Role, Step
from app.core.database import get_db
from app.core.security import CurrentUser, require_role
from app.submissions import service
from app.submissions.schemas import (
    AnswersSave,
    AttemptFinish,
    EvaluationSave,
    ExplanationSave,
    StudentAssignmentOut,
    SubmissionOut,
    SubmissionStart,
)

router = APIRouter(prefix="/submissions", tags=["submissions"])
student_router = APIRouter(prefix="/student", tags=["student"])

DbSession = Annotated[Session, Depends(get_db)]
Student = Annotated[CurrentUser, Depends(require_role(Role.STUDENT))]


@router.post(
    "",
    response_model=SubmissionOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "The student already had a submission; it is returned."}},
)
def start_submission(
    body: SubmissionStart, response: Response, db: DbSession, student: Student
) -> SubmissionOut:
    submission, created = service.start_submission(db, student, body.assignment_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return submission


@router.get("/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: uuid.UUID, db: DbSession, student: Student) -> SubmissionOut:
    return service.get_submission(db, student, submission_id)


@router.put("/{submission_id}/attempt/answers", response_model=SubmissionOut)
def save_attempt_answers(
    submission_id: uuid.UUID, body: AnswersSave, db: DbSession, student: Student
) -> SubmissionOut:
    return service.save_answers(db, student, submission_id, Step.ATTEMPT, body.answers)


@router.post("/{submission_id}/attempt", response_model=SubmissionOut)
def finish_attempt(
    submission_id: uuid.UUID, body: AttemptFinish, db: DbSession, student: Student
) -> SubmissionOut:
    return service.finish_attempt(db, student, submission_id, body)


@router.post("/{submission_id}/evaluation", response_model=SubmissionOut)
def save_evaluation(
    submission_id: uuid.UUID, body: EvaluationSave, db: DbSession, student: Student
) -> SubmissionOut:
    return service.save_evaluation(db, student, submission_id, body)


@router.put("/{submission_id}/revision/answers", response_model=SubmissionOut)
def save_revision_answers(
    submission_id: uuid.UUID, body: AnswersSave, db: DbSession, student: Student
) -> SubmissionOut:
    return service.save_answers(db, student, submission_id, Step.REVISE, body.answers)


@router.post("/{submission_id}/revision", response_model=SubmissionOut)
def finish_revision(submission_id: uuid.UUID, db: DbSession, student: Student) -> SubmissionOut:
    return service.finish_revision(db, student, submission_id)


@router.post("/{submission_id}/explanation", response_model=SubmissionOut)
def save_explanation(
    submission_id: uuid.UUID, body: ExplanationSave, db: DbSession, student: Student
) -> SubmissionOut:
    return service.save_explanation(db, student, submission_id, body)


@student_router.get("/assignments", response_model=list[StudentAssignmentOut])
def list_my_assignments(db: DbSession, student: Student) -> list[StudentAssignmentOut]:
    return service.list_student_assignments(db, student)
