import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.assignments.join_codes import normalize_join_code
from app.assignments.models import Assignment
from app.core.constants import Role
from tests.conftest import LoginAs

PROFESSOR_ID = str(uuid.uuid4())
STUDENT_ID = str(uuid.uuid4())
OTHER_STUDENT_ID = str(uuid.uuid4())


def create_course(api: TestClient, login_as: LoginAs, title: str = "Intro to Programming") -> dict:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    response = api.post("/courses", json={"title": title})
    assert response.status_code == 201
    return response.json()


def create_assignment(
    api: TestClient,
    login_as: LoginAs,
    db_session: Session,
    course_id: str,
    title: str,
    published_at: datetime | None,
) -> str:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    body = {
        "course_id": course_id,
        "title": title,
        "questions": [{"prompt": "Explain your loop.", "answer_type": "text"}],
    }
    response = api.post("/assignments", json=body)
    assert response.status_code == 201
    assignment_id = response.json()["id"]
    # Publishing has its own endpoint (#33); here the test sets the date directly.
    db_session.get(Assignment, uuid.UUID(assignment_id)).published_at = published_at
    db_session.commit()
    return assignment_id


def join(api: TestClient, login_as: LoginAs, code: str, student_id: str = STUDENT_ID):
    login_as(Role.STUDENT, student_id)
    return api.post("/courses/join", json={"code": code})


def test_new_course_has_a_join_code_only_its_professor_sees(
    api: TestClient, login_as: LoginAs
) -> None:
    course = create_course(api, login_as)

    assert len(course["join_code"]) == 9
    assert course["join_code"][4] == "-"
    assert course["student_count"] == 0


def test_student_joins_with_the_code_however_it_is_typed(
    api: TestClient, login_as: LoginAs
) -> None:
    course = create_course(api, login_as)
    typed = course["join_code"].replace("-", " ").lower()

    response = join(api, login_as, typed)

    assert response.status_code == 200
    assert response.json()["course_title"] == "Intro to Programming"
    assert "join_code" not in response.json()


def test_joining_twice_returns_the_same_enrollment(api: TestClient, login_as: LoginAs) -> None:
    course = create_course(api, login_as)

    first = join(api, login_as, course["join_code"]).json()
    second = join(api, login_as, course["join_code"])

    assert second.status_code == 200
    assert second.json() == first


def test_unknown_code_is_not_found(api: TestClient, login_as: LoginAs) -> None:
    response = join(api, login_as, "ZZZZ-ZZZZ")

    assert response.status_code == 404
    assert "No course has that code" in response.json()["error"]["message"]


def test_professor_sees_how_many_students_joined(api: TestClient, login_as: LoginAs) -> None:
    course = create_course(api, login_as)
    join(api, login_as, course["join_code"], STUDENT_ID)
    join(api, login_as, course["join_code"], OTHER_STUDENT_ID)

    login_as(Role.PROFESSOR, PROFESSOR_ID)
    courses = api.get("/courses").json()

    assert [c["student_count"] for c in courses] == [2]


def test_student_sees_published_assignments_from_joined_courses_newest_first(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    joined = create_course(api, login_as, "Joined")
    other = create_course(api, login_as, "Not joined")
    now = datetime.now(UTC)
    older = create_assignment(
        api, login_as, db_session, joined["id"], "Week 1", now - timedelta(days=7)
    )
    newer = create_assignment(api, login_as, db_session, joined["id"], "Week 2", now)
    create_assignment(api, login_as, db_session, joined["id"], "Draft", None)
    create_assignment(api, login_as, db_session, other["id"], "Other course", now)
    join(api, login_as, joined["join_code"])

    response = api.get("/student/assignments")

    assert response.status_code == 200
    rows = response.json()
    assert [row["id"] for row in rows] == [newer, older]
    assert rows[0]["course_title"] == "Joined"
    assert rows[0]["submission_id"] is None and rows[0]["current_step"] is None


def test_student_list_shows_their_progress(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    course = create_course(api, login_as)
    assignment_id = create_assignment(
        api, login_as, db_session, course["id"], "Week 1", datetime.now(UTC)
    )
    join(api, login_as, course["join_code"])
    started = api.post("/submissions", json={"assignment_id": assignment_id}).json()

    row = api.get("/student/assignments").json()[0]

    assert row["submission_id"] == started["id"]
    assert row["status"] == "in_progress"
    assert row["current_step"] == "attempt"


def test_another_students_courses_are_not_listed(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    course = create_course(api, login_as)
    create_assignment(api, login_as, db_session, course["id"], "Week 1", datetime.now(UTC))
    join(api, login_as, course["join_code"], OTHER_STUDENT_ID)

    login_as(Role.STUDENT, STUDENT_ID)

    assert api.get("/student/assignments").json() == []


@pytest.mark.parametrize(
    ("method", "path"), [("post", "/courses/join"), ("get", "/student/assignments")]
)
def test_professor_cannot_use_the_student_routes(
    api: TestClient, login_as: LoginAs, method: str, path: str
) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)

    response = getattr(api, method)(
        path, **({"json": {"code": "ABCD-EFGH"}} if method == "post" else {})
    )

    assert response.status_code == 403


def test_normalize_join_code() -> None:
    assert normalize_join_code(" 7k4q m2xp ") == "7K4Q-M2XP"
    assert normalize_join_code("7K4Q-M2XP") == "7K4Q-M2XP"
    assert normalize_join_code("short") == "SHORT"
