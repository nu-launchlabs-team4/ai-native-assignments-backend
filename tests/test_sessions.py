import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.assignments.models import Assignment
from app.core.constants import Role
from app.sessions import service as sessions_service
from app.sessions.models import WorkSession
from app.users.models import User
from tests.conftest import LoginAs

PROFESSOR_ID = str(uuid.uuid4())
STUDENT_ID = str(uuid.uuid4())
OTHER_STUDENT_ID = str(uuid.uuid4())


def start_submission(api: TestClient, login_as: LoginAs, db_session: Session) -> dict:
    """A published assignment with one question, and the student's submission for it."""
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    course_id = api.post("/courses", json={"title": "Intro"}).json()["id"]
    body = {
        "course_id": course_id,
        "title": "Week 3",
        "questions": [{"prompt": "Explain your loop.", "answer_type": "text"}],
    }
    assignment = api.post("/assignments", json=body).json()
    db_session.get(Assignment, uuid.UUID(assignment["id"])).published_at = datetime.now(UTC)
    db_session.add(User(id=uuid.UUID(STUDENT_ID), email="student@uni.edu", role=Role.STUDENT))
    db_session.commit()
    login_as(Role.STUDENT, STUDENT_ID)
    return api.post("/submissions", json={"assignment_id": assignment["id"]}).json()


def event(type_: str, **extra: object) -> dict:
    return {"type": type_, "step": "attempt", "occurred_at": datetime.now(UTC).isoformat(), **extra}


def test_session_records_browser_events_and_ends(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    submission = start_submission(api, login_as, db_session)
    question_id = submission["assignment"]["questions"][0]["id"]

    session = api.post(f"/submissions/{submission['id']}/sessions")
    assert session.status_code == 201
    session_id = session.json()["id"]
    events = [
        event("tab_leave"),
        event("tab_return"),
        event("paste", question_id=question_id, detail={"characters": 42}),
    ]
    assert api.post(f"/sessions/{session_id}/events", json={"events": events}).status_code == 204
    assert api.post(f"/sessions/{session_id}/end").status_code == 204
    assert api.post(f"/sessions/{session_id}/end").status_code == 204

    ended = api.post(f"/sessions/{session_id}/events", json={"events": [event("tab_leave")]})
    assert ended.status_code == 409


@pytest.mark.parametrize(
    "bad_event",
    [
        event("paste"),
        event("tab_leave", detail={"characters": 1}),
        event("snapshot"),
        event("keystroke"),
    ],
    ids=["paste-without-size", "detail-on-tab-leave", "snapshot-from-browser", "unknown-type"],
)
def test_browser_events_are_checked(
    api: TestClient, login_as: LoginAs, db_session: Session, bad_event: dict
) -> None:
    submission = start_submission(api, login_as, db_session)
    session_id = api.post(f"/submissions/{submission['id']}/sessions").json()["id"]

    response = api.post(f"/sessions/{session_id}/events", json={"events": [bad_event]})

    assert response.status_code == 422


def test_starting_a_session_ends_the_one_left_open(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    submission = start_submission(api, login_as, db_session)
    first = api.post(f"/submissions/{submission['id']}/sessions").json()["id"]

    api.post(f"/submissions/{submission['id']}/sessions")

    assert db_session.get(WorkSession, uuid.UUID(first)).ended_at is not None


def test_saving_answers_records_a_snapshot(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    submission = start_submission(api, login_as, db_session)
    question_id = submission["assignment"]["questions"][0]["id"]

    api.put(
        f"/submissions/{submission['id']}/attempt/answers", json={"answers": {question_id: "Draft"}}
    )

    login_as(Role.PROFESSOR, PROFESSOR_ID)
    timeline = api.get(f"/submissions/{submission['id']}/sessions").json()
    [session] = timeline["sessions"]
    [snapshot] = session["events"]
    assert snapshot["type"] == "snapshot"
    assert snapshot["step"] == "attempt"
    # The timeline says which answers changed; the text stays out of it.
    assert snapshot["detail"] == {"question_ids": [question_id]}


def test_snapshot_after_a_long_break_starts_a_new_session(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    submission = start_submission(api, login_as, db_session)
    question_id = submission["assignment"]["questions"][0]["id"]
    session_id = api.post(f"/submissions/{submission['id']}/sessions").json()["id"]
    stale = db_session.get(WorkSession, uuid.UUID(session_id))
    stale.started_at = datetime.now(UTC) - sessions_service.IDLE_GAP - timedelta(minutes=5)
    db_session.commit()

    api.put(
        f"/submissions/{submission['id']}/attempt/answers", json={"answers": {question_id: "Back"}}
    )

    login_as(Role.PROFESSOR, PROFESSOR_ID)
    sessions = api.get(f"/submissions/{submission['id']}/sessions").json()["sessions"]
    assert len(sessions) == 2
    assert sessions[0]["ended_at"] is not None


def test_professor_timeline_has_step_segments_and_the_student(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    submission = start_submission(api, login_as, db_session)
    session_id = api.post(f"/submissions/{submission['id']}/sessions").json()["id"]
    start = datetime.now(UTC)
    events = [
        {
            "type": "tab_leave",
            "step": "attempt",
            "occurred_at": (start + timedelta(minutes=1)).isoformat(),
        },
        {
            "type": "tab_return",
            "step": "feedback",
            "occurred_at": (start + timedelta(minutes=5)).isoformat(),
        },
    ]
    api.post(f"/sessions/{session_id}/events", json={"events": events})

    login_as(Role.PROFESSOR, PROFESSOR_ID)
    timeline = api.get(f"/submissions/{submission['id']}/sessions")

    assert timeline.status_code == 200
    body = timeline.json()
    assert body["assignment_title"] == "Week 3"
    assert body["student_name"] == "student@uni.edu"
    [session] = body["sessions"]
    assert [segment["step"] for segment in session["segments"]] == ["attempt", "feedback"]
    assert [e["type"] for e in session["events"]] == ["tab_leave", "tab_return"]


def test_sessions_are_private(api: TestClient, login_as: LoginAs, db_session: Session) -> None:
    submission = start_submission(api, login_as, db_session)
    session_id = api.post(f"/submissions/{submission['id']}/sessions").json()["id"]

    login_as(Role.STUDENT, OTHER_STUDENT_ID)
    assert api.post(f"/submissions/{submission['id']}/sessions").status_code == 404
    assert api.post(f"/sessions/{session_id}/end").status_code == 404

    login_as(Role.PROFESSOR, str(uuid.uuid4()))
    assert api.get(f"/submissions/{submission['id']}/sessions").status_code == 404

    login_as(Role.STUDENT, STUDENT_ID)
    assert api.get(f"/submissions/{submission['id']}/sessions").status_code == 403
