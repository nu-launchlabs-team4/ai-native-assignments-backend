import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.assignments.schemas import (
    MAX_INSTRUCTIONS_CHARS,
    MAX_PROMPT_CHARS,
    MAX_STARTER_CODE_CHARS,
)
from app.assignments.service import ALREADY_PUBLISHED
from app.core.constants import Role
from app.core.database import Base, get_db
from app.core.security import CurrentUser, get_current_user
from app.main import app

LoginAs = Callable[[Role, str], None]

PROFESSOR_ID = str(uuid.uuid4())
OTHER_PROFESSOR_ID = str(uuid.uuid4())
STUDENT_ID = str(uuid.uuid4())


@pytest.fixture
def db_session() -> Iterator[Session]:
    # In-memory SQLite stands in for Supabase so the service queries really run.
    # StaticPool keeps one connection, so every request sees the same database.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def api(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def login_as() -> LoginAs:
    # Supabase JWT checks aren't built yet (#4), so tests replace the signed-in user.
    def log_in(role: Role, user_id: str) -> None:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id, role=role)

    return log_in


def assignment_body(course_id: str) -> dict[str, object]:
    return {
        "course_id": course_id,
        "title": "Week 3: Counting and loops",
        "instructions": "Answer each question yourself first.",
        "ai_policy": "permitted",
        "help_level": "hints",
        "final_check": "ai_interview",
        "questions": [
            {
                "prompt": "Write count_vowels(text).",
                "answer_type": "code",
                "language": "python",
                "starter_code": "def count_vowels(text):\n    pass\n",
            },
            {"prompt": "Explain how your function works.", "answer_type": "text"},
            {"prompt": "Simplify T(n) = 3n + 2n + 5.", "answer_type": "math"},
        ],
    }


def create_course(api: TestClient, title: str = "Intro to Programming") -> str:
    response = api.post("/courses", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


def create_assignment(api: TestClient, course_id: str) -> dict[str, object]:
    response = api.post("/assignments", json=assignment_body(course_id))
    assert response.status_code == 201
    return response.json()


def test_create_and_list_courses(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    course_id = create_course(api)

    response = api.get("/courses")

    assert response.status_code == 200
    assert [course["id"] for course in response.json()] == [course_id]


def test_courses_are_private_to_their_professor(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    create_course(api)

    login_as(Role.PROFESSOR, OTHER_PROFESSOR_ID)
    response = api.get("/courses")

    assert response.json() == []


def test_create_assignment_returns_questions_in_order(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    course_id = create_course(api)

    assignment = create_assignment(api, course_id)

    assert assignment["ai_policy"] == "permitted"
    assert assignment["help_level"] == "hints"
    assert assignment["final_check"] == "ai_interview"
    assert assignment["published_at"] is None
    questions = assignment["questions"]
    assert [question["position"] for question in questions] == [1, 2, 3]
    assert [question["answer_type"] for question in questions] == ["code", "text", "math"]
    assert questions[0]["language"] == "python"
    assert questions[0]["starter_code"].startswith("def count_vowels")
    assert questions[1]["language"] is None


def test_get_assignment(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    created = create_assignment(api, create_course(api))

    response = api.get(f"/assignments/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_list_assignments_in_course(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    course_id = create_course(api)
    created = create_assignment(api, course_id)
    create_assignment(api, create_course(api, "Another course"))

    response = api.get("/assignments", params={"course_id": course_id})

    assert response.status_code == 200
    assert [assignment["id"] for assignment in response.json()] == [created["id"]]


def test_other_professors_assignment_is_not_found(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    created = create_assignment(api, create_course(api))

    login_as(Role.PROFESSOR, OTHER_PROFESSOR_ID)
    response = api.get(f"/assignments/{created['id']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_assignment_in_other_professors_course_is_not_found(
    api: TestClient, login_as: LoginAs
) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    course_id = create_course(api)

    login_as(Role.PROFESSOR, OTHER_PROFESSOR_ID)
    response = api.post("/assignments", json=assignment_body(course_id))

    assert response.status_code == 404


def test_code_question_needs_language(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    body = assignment_body(create_course(api))
    body["questions"] = [{"prompt": "Write a function.", "answer_type": "code"}]

    response = api.post("/assignments", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_text_question_rejects_language(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    body = assignment_body(create_course(api))
    body["questions"] = [{"prompt": "Explain.", "answer_type": "text", "language": "python"}]

    response = api.post("/assignments", json=body)

    assert response.status_code == 422


def test_assignment_needs_a_question(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    body = assignment_body(create_course(api))
    body["questions"] = []

    response = api.post("/assignments", json=body)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "limit"),
    [("prompt", MAX_PROMPT_CHARS), ("starter_code", MAX_STARTER_CODE_CHARS)],
)
def test_question_text_has_a_length_limit(
    api: TestClient, login_as: LoginAs, field: str, limit: int
) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    body = assignment_body(create_course(api))
    question = {"prompt": "Write a function.", "answer_type": "code", "language": "python"}
    question[field] = "x" * (limit + 1)
    body["questions"] = [question]

    response = api.post("/assignments", json=body)

    assert response.status_code == 422


def test_instructions_have_a_length_limit(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    body = assignment_body(create_course(api))
    body["instructions"] = "x" * (MAX_INSTRUCTIONS_CHARS + 1)

    response = api.post("/assignments", json=body)

    assert response.status_code == 422


def test_text_at_the_limit_is_accepted(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    body = assignment_body(create_course(api))
    body["instructions"] = "x" * MAX_INSTRUCTIONS_CHARS

    response = api.post("/assignments", json=body)

    assert response.status_code == 201


def test_student_cannot_create_course(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.STUDENT, STUDENT_ID)

    response = api.post("/courses", json={"title": "Intro to Programming"})

    assert response.status_code == 403


def test_missing_token_is_unauthorized(api: TestClient) -> None:
    response = api.get("/courses")

    assert response.status_code == 401


# Update and publish (#33)


def update_body() -> dict[str, object]:
    body = assignment_body("unused")
    del body["course_id"]
    body["title"] = "Week 3: Loops, revised"
    body["help_level"] = "concepts"
    body["questions"] = [
        {"prompt": "Explain your approach first.", "answer_type": "text"},
        {"prompt": "Write count_vowels(text).", "answer_type": "code", "language": "python"},
    ]
    return body


def test_update_replaces_fields_and_questions_in_order(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    assignment = create_assignment(api, create_course(api))

    response = api.patch(f"/assignments/{assignment['id']}", json=update_body())

    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Week 3: Loops, revised"
    assert updated["help_level"] == "concepts"
    assert [(q["position"], q["prompt"]) for q in updated["questions"]] == [
        (1, "Explain your approach first."),
        (2, "Write count_vowels(text)."),
    ]
    again = api.get(f"/assignments/{assignment['id']}").json()
    assert [q["prompt"] for q in again["questions"]] == [q["prompt"] for q in updated["questions"]]


def test_update_validates_questions_like_create(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    assignment = create_assignment(api, create_course(api))
    body = update_body()
    body["questions"] = [{"prompt": "Write code.", "answer_type": "code"}]

    response = api.patch(f"/assignments/{assignment['id']}", json=body)

    assert response.status_code == 422


def test_publish_sets_published_at_once(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    assignment = create_assignment(api, create_course(api))
    assert assignment["published_at"] is None

    published = api.post(f"/assignments/{assignment['id']}/publish")
    again = api.post(f"/assignments/{assignment['id']}/publish")

    assert published.status_code == 200
    assert published.json()["published_at"] is not None
    assert again.status_code == 409
    assert again.json()["error"]["message"] == ALREADY_PUBLISHED


def test_published_assignment_cannot_be_edited(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    assignment = create_assignment(api, create_course(api))
    api.post(f"/assignments/{assignment['id']}/publish")

    response = api.patch(f"/assignments/{assignment['id']}", json=update_body())

    assert response.status_code == 409


@pytest.mark.parametrize("action", ["update", "publish"])
def test_other_professor_cannot_update_or_publish(
    api: TestClient, login_as: LoginAs, action: str
) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    assignment = create_assignment(api, create_course(api))
    login_as(Role.PROFESSOR, OTHER_PROFESSOR_ID)

    path = f"/assignments/{assignment['id']}"
    response = (
        api.patch(path, json=update_body()) if action == "update" else api.post(f"{path}/publish")
    )

    assert response.status_code == 404


def test_student_cannot_publish(api: TestClient, login_as: LoginAs) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    assignment = create_assignment(api, create_course(api))
    login_as(Role.STUDENT, str(uuid.uuid4()))

    response = api.post(f"/assignments/{assignment['id']}/publish")

    assert response.status_code == 403


def test_published_assignment_can_be_started_by_a_student(
    api: TestClient, login_as: LoginAs
) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    assignment = create_assignment(api, create_course(api))
    login_as(Role.STUDENT, str(uuid.uuid4()))
    assert api.post("/submissions", json={"assignment_id": assignment["id"]}).status_code == 404

    login_as(Role.PROFESSOR, PROFESSOR_ID)
    api.post(f"/assignments/{assignment['id']}/publish")
    login_as(Role.STUDENT, str(uuid.uuid4()))

    assert api.post("/submissions", json={"assignment_id": assignment["id"]}).status_code == 201
