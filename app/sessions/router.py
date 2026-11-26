import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.constants import Role
from app.core.database import get_db
from app.core.security import CurrentUser, require_role
from app.sessions import service
from app.sessions.schemas import ActivityEventsIn, SubmissionSessionsOut, WorkSessionOut

router = APIRouter(prefix="/sessions", tags=["sessions"])
# Starting a session and the professor's timeline hang off the submission they belong to.
submission_sessions_router = APIRouter(prefix="/submissions", tags=["sessions"])

DbSession = Annotated[Session, Depends(get_db)]
Student = Annotated[CurrentUser, Depends(require_role(Role.STUDENT))]
Professor = Annotated[CurrentUser, Depends(require_role(Role.PROFESSOR))]


@submission_sessions_router.post(
    "/{submission_id}/sessions", response_model=WorkSessionOut, status_code=status.HTTP_201_CREATED
)
def start_session(submission_id: uuid.UUID, db: DbSession, student: Student) -> WorkSessionOut:
    return service.start_session(db, student, submission_id)


@submission_sessions_router.get("/{submission_id}/sessions", response_model=SubmissionSessionsOut)
def get_submission_sessions(
    submission_id: uuid.UUID, db: DbSession, professor: Professor
) -> SubmissionSessionsOut:
    return service.get_submission_sessions(db, professor, submission_id)


@router.post("/{session_id}/events", status_code=status.HTTP_204_NO_CONTENT)
def add_events(
    session_id: uuid.UUID, body: ActivityEventsIn, db: DbSession, student: Student
) -> None:
    service.add_events(db, student, session_id, body)


@router.post("/{session_id}/end", status_code=status.HTTP_204_NO_CONTENT)
def end_session(session_id: uuid.UUID, db: DbSession, student: Student) -> None:
    service.end_session(db, student, session_id)
