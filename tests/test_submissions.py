import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.assignments.models import Assignment
from app.core.constants import Role

LoginAs = Callable[[Role, str], None]
Json = dict[str, Any]

PROFESSOR_ID = str(uuid.uuid4())
STUDENT_ID = str(uuid.uuid4())
OTHER_STUDENT_ID = str(uuid.uuid4())

CODE_ANSWER = "def count_vowels(text):\n    return sum(c in 'aeiou' for c in text)\n"
TEXT_ANSWER = "It checks each character against the vowels."
MATH_ANSWER = "T(n) = 3n + 2n + 5\nT(n) = 5n + 5"


def make_assignment(
    api: TestClient, login_as: LoginAs, db_session: Session, *, published: bool = True
) -> Json:
    """Create an assignment with a code, a text and a math question, as the professor."""
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    course = api.post("/courses", json={"title": "Intro to Programming"}).json()
    response = api.post(
        "/assignments",
        json={
            "course_id": course["id"],
            "title": "Week 3",
            "questions": [
                {"prompt": "Write count_vowels.", "answer_type": "code", "language": "python"},
                {"prompt": "Explain it.", "answer_type": "text"},
                {"prompt": "Simplify T(n).", "answer_type": "math"},
            ],
        },
    )
    assignment = response.json()
    if published:
        # There is no publish endpoint yet, so publish it in the database directly.
        db_session.execute(
            update(Assignment)
            .where(Assignment.id == uuid.UUID(assignment["id"]))
            .values(published_at=datetime.now(UTC))
        )
        db_session.commit()
    return assignment


def question_ids(assignment: Json) -> list[str]:
    return [question["id"] for question in assignment["questions"]]


def all_answers(assignment: Json) -> dict[str, str]:
    code_id, text_id, math_id = question_ids(assignment)
    return {code_id: CODE_ANSWER, text_id: TEXT_ANSWER, math_id: MATH_ANSWER}


def start(api: TestClient, login_as: LoginAs, assignment: Json) -> Json:
    login_as(Role.STUDENT, STUDENT_ID)
    response = api.post("/submissions", json={"assignment_id": assignment["id"]})
    assert response.status_code == 201
    return response.json()


def finish_attempt(api: TestClient, submission_id: str, answers: dict[str, str]) -> None:
    saved = api.put(f"/submissions/{submission_id}/attempt/answers", json={"answers": answers})
    assert saved.status_code == 200
    response = api.post(
        f"/submissions/{submission_id}/attempt",
        json={"confidence": 3, "approach_note": "Loop over the text and count vowels."},
    )
    assert response.status_code == 200


@pytest.fixture
def assignment(api: TestClient, login_as: LoginAs, db_session: Session) -> Json:
    return make_assignment(api, login_as, db_session)


def test_start_returns_the_assignment_and_questions(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)

    assert submission["status"] == "in_progress"
    assert submission["current_step"] == "attempt"
    assert submission["attempt_answers"] == {}
    assert submission["assignment"]["id"] == assignment["id"]
    assert len(submission["assignment"]["questions"]) == 3


def test_starting_again_returns_the_same_submission(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    first = start(api, login_as, assignment)

    response = api.post("/submissions", json={"assignment_id": assignment["id"]})

    assert response.status_code == 200
    assert response.json()["id"] == first["id"]


def test_draft_assignment_is_hidden_from_students(
    api: TestClient, login_as: LoginAs, db_session: Session
) -> None:
    draft = make_assignment(api, login_as, db_session, published=False)
    login_as(Role.STUDENT, STUDENT_ID)

    response = api.post("/submissions", json={"assignment_id": draft["id"]})

    assert response.status_code == 404


def test_attempt_answers_are_saved_per_question(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)
    code_id, _, math_id = question_ids(assignment)
    url = f"/submissions/{submission['id']}/attempt/answers"

    api.put(url, json={"answers": {code_id: "def count_vowels(text):\n    pass\n"}})
    api.put(url, json={"answers": {math_id: MATH_ANSWER}})
    response = api.put(url, json={"answers": {code_id: CODE_ANSWER}})

    assert response.status_code == 200
    # Autosave can send one question at a time; the others are kept as they were.
    assert response.json()["attempt_answers"] == {code_id: CODE_ANSWER, math_id: MATH_ANSWER}


def test_answer_for_another_assignments_question_is_rejected(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)

    response = api.put(
        f"/submissions/{submission['id']}/attempt/answers",
        json={"answers": {str(uuid.uuid4()): "an answer"}},
    )

    assert response.status_code == 422


def test_attempt_needs_every_question_answered(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)
    code_id = question_ids(assignment)[0]
    api.put(
        f"/submissions/{submission['id']}/attempt/answers",
        json={"answers": {code_id: CODE_ANSWER}},
    )

    response = api.post(
        f"/submissions/{submission['id']}/attempt",
        json={"confidence": 4, "approach_note": "Count in a loop."},
    )

    assert response.status_code == 422


def test_finishing_the_attempt_saves_confidence_and_note(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)

    finish_attempt(api, submission["id"], all_answers(assignment))

    saved = api.get(f"/submissions/{submission['id']}").json()
    assert saved["current_step"] == "feedback"
    assert saved["confidence"] == 3
    assert saved["approach_note"] == "Loop over the text and count vowels."
    assert saved["attempt_submitted_at"] is not None


@pytest.mark.parametrize("confidence", [0, 6])
def test_confidence_must_be_1_to_5(
    api: TestClient, login_as: LoginAs, assignment: Json, confidence: int
) -> None:
    submission = start(api, login_as, assignment)

    response = api.post(
        f"/submissions/{submission['id']}/attempt",
        json={"confidence": confidence, "approach_note": "A loop."},
    )

    assert response.status_code == 422


def test_attempt_is_frozen_once_handed_in(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)
    finish_attempt(api, submission["id"], all_answers(assignment))

    response = api.put(
        f"/submissions/{submission['id']}/attempt/answers",
        json={"answers": {question_ids(assignment)[0]: "changed after seeing the AI"}},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_evaluation_before_the_attempt_is_rejected(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)

    response = api.post(
        f"/submissions/{submission['id']}/evaluation",
        json={"verdict": "correct", "test_case": "count_vowels('aei') == 3"},
    )

    assert response.status_code == 409


def test_full_trail_keeps_both_versions(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)
    submission_id = submission["id"]
    code_id = question_ids(assignment)[0]
    finish_attempt(api, submission_id, all_answers(assignment))

    evaluated = api.post(
        f"/submissions/{submission_id}/evaluation",
        json={"verdict": "partly_correct", "test_case": "count_vowels('AEI') == 3"},
    ).json()
    # The revision starts as a copy of the attempt.
    assert evaluated["current_step"] == "revise"
    assert evaluated["revision_answers"] == evaluated["attempt_answers"]

    revised_code = "def count_vowels(text):\n    return sum(c in 'aeiou' for c in text.lower())\n"
    api.put(
        f"/submissions/{submission_id}/revision/answers",
        json={"answers": {code_id: revised_code}},
    )
    assert api.post(f"/submissions/{submission_id}/revision").json()["current_step"] == "explain"

    response = api.post(
        f"/submissions/{submission_id}/explanation",
        json={
            "interview_answers": [
                {"question": "Why lower()?", "answer": "The test case used capitals."}
            ],
            "ai_declaration": "The AI pointed out that capitals weren't counted.",
        },
    )

    assert response.status_code == 200
    final = response.json()
    assert final["status"] == "submitted"
    assert final["submitted_at"] is not None
    assert final["evaluation_verdict"] == "partly_correct"
    assert final["attempt_answers"][code_id] == CODE_ANSWER
    assert final["revision_answers"][code_id] == revised_code
    assert final["interview_answers"][0]["answer"] == "The test case used capitals."


def test_submitted_work_cannot_change(api: TestClient, login_as: LoginAs, assignment: Json) -> None:
    submission = start(api, login_as, assignment)
    submission_id = submission["id"]
    finish_attempt(api, submission_id, all_answers(assignment))
    api.post(
        f"/submissions/{submission_id}/evaluation",
        json={"verdict": "correct", "test_case": "count_vowels('a') == 1"},
    )
    api.post(f"/submissions/{submission_id}/revision")
    explanation = {
        "interview_answers": [{"question": "Why a loop?", "answer": "It is simplest."}],
        "ai_declaration": "None.",
    }
    api.post(f"/submissions/{submission_id}/explanation", json=explanation)

    response = api.post(f"/submissions/{submission_id}/explanation", json=explanation)

    assert response.status_code == 409


def test_students_see_only_their_own_work(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    submission = start(api, login_as, assignment)

    login_as(Role.STUDENT, OTHER_STUDENT_ID)
    get_response = api.get(f"/submissions/{submission['id']}")
    put_response = api.put(
        f"/submissions/{submission['id']}/attempt/answers",
        json={"answers": {question_ids(assignment)[0]: "not mine"}},
    )

    assert get_response.status_code == 404
    assert put_response.status_code == 404


def test_professor_cannot_use_student_routes(
    api: TestClient, login_as: LoginAs, assignment: Json
) -> None:
    login_as(Role.PROFESSOR, PROFESSOR_ID)

    response = api.post("/submissions", json={"assignment_id": assignment["id"]})

    assert response.status_code == 403


def test_missing_token_is_unauthorized(api: TestClient) -> None:
    response = api.get(f"/submissions/{uuid.uuid4()}")

    assert response.status_code == 401
