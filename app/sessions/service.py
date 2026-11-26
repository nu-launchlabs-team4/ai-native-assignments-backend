"""Business logic for sessions. Routes call these functions and stay thin."""

import logging
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import Assignment, Course
from app.core.constants import SESSION_IDLE_MINUTES, ActivityEventType, Step, SubmissionStatus
from app.core.security import CurrentUser
from app.sessions.models import ActivityEvent, WorkSession
from app.sessions.schemas import (
    ActivityEventOut,
    ActivityEventsIn,
    StepSegmentOut,
    SubmissionSessionsOut,
    WorkSessionDetailOut,
    WorkSessionOut,
)
from app.submissions.models import Submission
from app.users.models import User

logger = logging.getLogger(__name__)

SUBMISSION_NOT_FOUND = "Submission not found"
SESSION_NOT_FOUND = "Session not found"
SESSION_ENDED = "This session has ended. Start a new one"
ALREADY_SUBMITTED = "This submission is already submitted"
IDLE_GAP = timedelta(minutes=SESSION_IDLE_MINUTES)


def start_session(db: Session, student: CurrentUser, submission_id: uuid.UUID) -> WorkSessionOut:
    """Start a work session, ending any the student left open (another tab, a closed laptop)."""
    submission = _get_owned_submission(db, student, submission_id)
    if submission.status == SubmissionStatus.SUBMITTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=ALREADY_SUBMITTED)
    for open_session in _open_sessions(db, submission.id):
        _end(open_session)
    session = WorkSession(submission_id=submission.id, started_at=_now())
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info("Work session started session_id=%s", session.id)
    return WorkSessionOut.model_validate(session)


def add_events(
    db: Session, student: CurrentUser, session_id: uuid.UUID, body: ActivityEventsIn
) -> None:
    """Record a batch of browser events (pastes, leaving and returning to the tab)."""
    session = _get_owned_session(db, student, session_id)
    if session.ended_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=SESSION_ENDED)
    for event in body.events:
        session.events.append(
            ActivityEvent(
                type=event.type,
                step=event.step,
                question_id=event.question_id,
                occurred_at=event.occurred_at,
                detail=event.detail.model_dump() if event.detail else None,
            )
        )
    db.commit()


def end_session(db: Session, student: CurrentUser, session_id: uuid.UUID) -> None:
    """End a work session. Ending it again changes nothing."""
    session = _get_owned_session(db, student, session_id)
    if session.ended_at is None:
        session.ended_at = _now()
        db.commit()


def record_snapshot(
    db: Session, submission: Submission, step: Step, answers: Mapping[uuid.UUID, str]
) -> None:
    """Keep a copy of the answers just saved, in the open work session.

    Called by the submissions service on every answer save, so snapshots can't be faked
    from the browser. With no open session (or one idle too long) it starts one. The
    caller commits.
    """
    now = _now()
    session = next(iter(_open_sessions(db, submission.id)), None)
    if session is not None and now - _last_activity(session) > IDLE_GAP:
        _end(session)
        session = None
    if session is None:
        session = WorkSession(submission_id=submission.id, started_at=now)
        db.add(session)
    session.events.append(
        ActivityEvent(
            type=ActivityEventType.SNAPSHOT,
            step=step,
            occurred_at=now,
            detail={"answers": {str(question_id): text for question_id, text in answers.items()}},
        )
    )


def get_submission_sessions(
    db: Session, professor: CurrentUser, submission_id: uuid.UUID
) -> SubmissionSessionsOut:
    """A submission's work sessions for its professor: step segments and events, oldest first."""
    row = db.execute(
        select(Submission, Assignment.title)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Course, Course.id == Assignment.course_id)
        .where(Submission.id == submission_id, Course.professor_id == _user_uuid(professor))
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SUBMISSION_NOT_FOUND)
    submission, assignment_title = row
    student = db.get(User, submission.student_id)
    sessions = db.scalars(
        select(WorkSession)
        .where(WorkSession.submission_id == submission.id)
        .order_by(WorkSession.started_at, WorkSession.id)
    )
    return SubmissionSessionsOut(
        submission_id=submission.id,
        assignment_title=assignment_title,
        student_name=student.email if student else "Student",
        sessions=[_session_detail(session) for session in sessions],
    )


def _session_detail(session: WorkSession) -> WorkSessionDetailOut:
    return WorkSessionDetailOut(
        id=session.id,
        started_at=session.started_at,
        ended_at=session.ended_at,
        segments=_segments(session),
        events=[_event_out(event) for event in session.events],
    )


def _segments(session: WorkSession) -> list[StepSegmentOut]:
    """Stretches of the session spent on one step, from the steps the events were in."""
    segments: list[StepSegmentOut] = []
    start = session.started_at
    for event in session.events:
        if segments and segments[-1].step == event.step:
            continue
        if segments:
            segments[-1].ended_at = event.occurred_at
            start = event.occurred_at
        segments.append(StepSegmentOut(step=event.step, started_at=start, ended_at=start))
    if segments:
        segments[-1].ended_at = session.ended_at or _last_activity(session)
    return segments


def _event_out(event: ActivityEvent) -> ActivityEventOut:
    detail = event.detail
    if event.type == ActivityEventType.SNAPSHOT and detail is not None:
        # The timeline needs which answers changed, not their text (the trail shows that).
        detail = {"question_ids": list(detail.get("answers", {}))}
    return ActivityEventOut(
        id=event.id,
        type=event.type,
        step=event.step,
        question_id=event.question_id,
        created_at=event.occurred_at,
        detail=detail,
    )


def _open_sessions(db: Session, submission_id: uuid.UUID) -> list[WorkSession]:
    return list(
        db.scalars(
            select(WorkSession)
            .where(WorkSession.submission_id == submission_id, WorkSession.ended_at.is_(None))
            .order_by(WorkSession.started_at.desc())
        )
    )


def _last_activity(session: WorkSession) -> datetime:
    times = [_aware(session.started_at)] + [_aware(event.occurred_at) for event in session.events]
    return max(times)


def _end(session: WorkSession) -> None:
    # A session left open ends at its last activity, not now, so idle time isn't counted.
    session.ended_at = _last_activity(session)


def _get_owned_submission(
    db: Session, student: CurrentUser, submission_id: uuid.UUID
) -> Submission:
    submission = db.scalar(
        select(Submission).where(
            Submission.id == submission_id, Submission.student_id == _user_uuid(student)
        )
    )
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SUBMISSION_NOT_FOUND)
    return submission


def _get_owned_session(db: Session, student: CurrentUser, session_id: uuid.UUID) -> WorkSession:
    session = db.scalar(
        select(WorkSession)
        .join(Submission, Submission.id == WorkSession.submission_id)
        .where(WorkSession.id == session_id, Submission.student_id == _user_uuid(student))
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=SESSION_NOT_FOUND)
    return session


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(moment: datetime) -> datetime:
    # SQLite (the tests' database) drops the time zone; Postgres keeps it.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _user_uuid(user: CurrentUser) -> uuid.UUID:
    return uuid.UUID(user.id)
