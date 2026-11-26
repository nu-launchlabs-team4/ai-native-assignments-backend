import json
import uuid

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assignments.models import Assignment, Course, Enrollment, Question
from app.core.constants import AnswerType, Role
from app.seed import (
    PROFESSOR,
    STUDENTS,
    DemoUser,
    SupabaseAuthAdmin,
    seed,
    supabase_headers,
)
from app.users.models import User

PASSWORD = "demo-password"


class FakeAuthAdmin:
    """Stands in for Supabase Auth: one account id per email."""

    def __init__(self) -> None:
        self.ids: dict[str, uuid.UUID] = {}

    def ensure_user(self, user: DemoUser, password: str) -> uuid.UUID:
        return self.ids.setdefault(user.email, uuid.uuid4())


def roles(db: Session) -> dict[str, Role]:
    return {user.email: user.role for user in db.scalars(select(User))}


def count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_seed_creates_the_demo_data(db_session: Session) -> None:
    auth = FakeAuthAdmin()

    result = seed(db_session, auth, PASSWORD)

    assert roles(db_session) == {
        PROFESSOR.email: Role.PROFESSOR,
        **{student.email: Role.STUDENT for student in STUDENTS},
    }
    assert db_session.get(User, result.professor_id) is not None
    course = db_session.get(Course, result.course_id)
    assert course is not None
    assert course.professor_id == result.professor_id
    assert course.join_code == result.join_code
    enrolled = db_session.scalars(
        select(Enrollment.student_id).where(Enrollment.course_id == course.id)
    )
    assert set(enrolled) == set(result.student_ids)
    assignment = db_session.get(Assignment, result.assignment_id)
    assert assignment is not None
    assert assignment.published_at is not None
    assert [question.answer_type for question in assignment.questions] == [
        AnswerType.CODE,
        AnswerType.TEXT,
        AnswerType.MATH,
    ]
    assert assignment.questions[0].language == "python"


def test_seed_is_safe_to_rerun(db_session: Session) -> None:
    auth = FakeAuthAdmin()
    first = seed(db_session, auth, PASSWORD)

    second = seed(db_session, auth, PASSWORD)

    assert second == first
    assert count(db_session, User) == 4
    assert count(db_session, Course) == 1
    assert count(db_session, Enrollment) == 3
    assert count(db_session, Assignment) == 1
    assert count(db_session, Question) == 3


def test_rerun_publishes_an_unpublished_demo_assignment(db_session: Session) -> None:
    auth = FakeAuthAdmin()
    result = seed(db_session, auth, PASSWORD)
    assignment = db_session.get(Assignment, result.assignment_id)
    assert assignment is not None
    assignment.published_at = None
    db_session.commit()

    seed(db_session, auth, PASSWORD)

    db_session.refresh(assignment)
    assert assignment.published_at is not None


def test_rerun_restores_the_demo_roles(db_session: Session) -> None:
    auth = FakeAuthAdmin()
    result = seed(db_session, auth, PASSWORD)
    student = db_session.get(User, result.student_ids[0])
    assert student is not None
    student.role = Role.PROFESSOR
    db_session.commit()

    seed(db_session, auth, PASSWORD)

    db_session.refresh(student)
    assert student.role == Role.STUDENT


def test_recreated_supabase_account_moves_the_users_row(db_session: Session) -> None:
    auth = FakeAuthAdmin()
    seed(db_session, auth, PASSWORD)
    # The professor's Supabase account was deleted and created again with a new id.
    auth.ids[PROFESSOR.email] = uuid.uuid4()

    result = seed(db_session, auth, PASSWORD)

    assert count(db_session, User) == 4
    professor = db_session.get(User, result.professor_id)
    assert professor is not None
    assert professor.email == PROFESSOR.email


def fake_supabase(existing: list[dict[str, str]], calls: list[httpx.Request]) -> httpx.Client:
    """An httpx client whose requests go to a fake Auth admin API, not the network."""

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"users": existing})
        if request.method == "POST":
            return httpx.Response(200, json={"id": str(uuid.uuid4())})
        return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[-1]})

    return httpx.Client(base_url="https://demo.supabase.co", transport=httpx.MockTransport(handle))


def test_supabase_admin_creates_a_missing_user_with_its_role() -> None:
    calls: list[httpx.Request] = []
    with fake_supabase([], calls) as client:
        SupabaseAuthAdmin(client).ensure_user(PROFESSOR, PASSWORD)

    create = calls[-1]
    assert create.method == "POST"
    body = json.loads(create.content)
    assert body["email"] == PROFESSOR.email
    assert body["email_confirm"] is True
    # The role lives in our users table, never in metadata users can edit.
    assert "app_metadata" not in body


def test_supabase_admin_updates_an_existing_user() -> None:
    existing_id = uuid.uuid4()
    calls: list[httpx.Request] = []
    accounts = [{"id": str(existing_id), "email": PROFESSOR.email.upper()}]
    with fake_supabase(accounts, calls) as client:
        user_id = SupabaseAuthAdmin(client).ensure_user(PROFESSOR, PASSWORD)

    assert user_id == existing_id
    assert calls[-1].method == "PUT"
    assert calls[-1].url.path.endswith(str(existing_id))
    assert not any(call.method == "POST" for call in calls)


def test_secret_key_headers() -> None:
    assert supabase_headers("sb_secret_abc") == {"apikey": "sb_secret_abc"}
    assert supabase_headers("eyJlegacy")["Authorization"] == "Bearer eyJlegacy"
