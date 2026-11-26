"""Tests for the AI tutoring chat endpoint."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai import service
from app.ai.llm import Turn
from app.ai.models import ChatMessage
from app.assignments.models import Assignment
from app.core.constants import HelpLevel, Role
from tests.test_submissions import (
    OTHER_STUDENT_ID,
    STUDENT_ID,
    all_answers,
    finish_attempt,
    make_assignment,
    question_ids,
    start,
)

LoginAs = Callable[[Role, str], None]


@pytest.fixture
def ready_submission(
    api: TestClient,
    login_as: LoginAs,
    db_session: Session,
) -> tuple[dict, dict]:
    """Create an assignment and a student submission with a completed attempt."""
    assignment = make_assignment(api, login_as, db_session)
    submission = start(api, login_as, assignment)
    finish_attempt(api, submission["id"], all_answers(assignment))
    return assignment, submission


@dataclass
class RecordingModel:
    """Stands in for the language model: returns the given replies in order, records each call."""

    replies: list[str]
    calls: list[tuple[str, list[Turn]]] = field(default_factory=list)

    def reply(self, system: str, turns: list[Turn], max_tokens: int) -> str:
        self.calls.append((system, list(turns)))
        return self.replies[len(self.calls) - 1]


def mock_llm(monkeypatch: pytest.MonkeyPatch, replies: list[str]) -> RecordingModel:
    """Make the tutor use a model that returns the supplied replies."""
    model = RecordingModel(replies)
    monkeypatch.setattr(service, "get_llm", lambda: model)
    return model


def test_chat_is_forbidden_before_attempt_is_submitted(
    api: TestClient,
    login_as: LoginAs,
    db_session: Session,
) -> None:
    """A student cannot chat before saving and submitting Step 1."""
    assignment = make_assignment(api, login_as, db_session)
    submission = start(api, login_as, assignment)

    response = api.post(
        f"/ai/submissions/{submission['id']}/chat",
        json={"message": "Can you help me?"},
    )

    assert response.status_code == 403


def test_chat_uses_assignment_help_level_and_logs_both_messages(
    api: TestClient,
    login_as: LoginAs,
    db_session: Session,
    ready_submission: tuple[dict, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configured prompt is used and both sides of the exchange are stored."""
    assignment, submission = ready_submission
    db_session.execute(
        update(Assignment)
        .where(Assignment.id == uuid.UUID(assignment["id"]))
        .values(help_level=HelpLevel.APPROACH)
    )
    db_session.commit()

    llm = mock_llm(
        monkeypatch,
        ["Break the task into smaller steps.", "Break the task into smaller steps."],
    )
    login_as(Role.STUDENT, STUDENT_ID)

    response = api.post(
        f"/ai/submissions/{submission['id']}/chat",
        json={"message": "How should I approach this?"},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Break the task into smaller steps."

    tutor_system_prompt = llm.calls[0][0]
    assert "APPROACH" in tutor_system_prompt

    messages = db_session.scalars(
        select(ChatMessage)
        .where(ChatMessage.submission_id == uuid.UUID(submission["id"]))
        .order_by(ChatMessage.created_at, ChatMessage.id)
    ).all()

    messages_by_role = {message.role: message for message in messages}
    assert set(messages_by_role) == {"student", "assistant"}
    assert messages_by_role["student"].content == "How should I approach this?"
    assert messages_by_role["assistant"].content == response.json()["reply"]


def test_chat_sends_only_the_current_students_work(
    api: TestClient,
    login_as: LoginAs,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model context must not contain another student's answers."""
    assignment = make_assignment(api, login_as, db_session)

    own_submission = start(api, login_as, assignment)
    own_answers = all_answers(assignment)
    first_question_id = question_ids(assignment)[0]
    own_answers[first_question_id] = "PRIVATE_CURRENT_STUDENT_SENTINEL"
    finish_attempt(api, own_submission["id"], own_answers)

    other_submission = start_as_other_student(api, login_as, assignment)
    other_answers = all_answers(assignment)
    other_answers[first_question_id] = "PRIVATE_OTHER_STUDENT_SENTINEL"
    finish_attempt(api, other_submission["id"], other_answers)

    llm = mock_llm(
        monkeypatch,
        ["Which part would you like to examine?", "Which part would you like to examine?"],
    )
    login_as(Role.STUDENT, STUDENT_ID)

    response = api.post(
        f"/ai/submissions/{own_submission['id']}/chat",
        json={"message": "Please review my work."},
    )

    assert response.status_code == 200
    tutor_system_prompt = llm.calls[0][0]
    assert "PRIVATE_CURRENT_STUDENT_SENTINEL" in tutor_system_prompt
    assert "PRIVATE_OTHER_STUDENT_SENTINEL" not in tutor_system_prompt


def start_as_other_student(
    api: TestClient,
    login_as: LoginAs,
    assignment: dict,
) -> dict:
    """Start a submission as a different student."""
    login_as(Role.STUDENT, OTHER_STUDENT_ID)
    response = api.post("/submissions", json={"assignment_id": assignment["id"]})
    assert response.status_code == 201
    return response.json()


def test_complete_solution_is_rewritten_as_a_hint(
    api: TestClient,
    login_as: LoginAs,
    ready_submission: tuple[dict, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete tutor solution is replaced by the review response."""
    _, submission = ready_submission
    mock_llm(
        monkeypatch,
        [
            "Here is the complete function: def solve(): return 42",
            "What steps could you take to build the function yourself?",
        ],
    )
    login_as(Role.STUDENT, STUDENT_ID)

    response = api.post(
        f"/ai/submissions/{submission['id']}/chat",
        json={"message": "Give me the solution."},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == ("What steps could you take to build the function yourself?")
    assert "return 42" not in response.json()["reply"]


def test_chat_is_rate_limited(
    api: TestClient,
    login_as: LoginAs,
    ready_submission: tuple[dict, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The AI endpoint allows at most 20 requests per minute."""
    _, submission = ready_submission
    login_as(Role.STUDENT, STUDENT_ID)

    monkeypatch.setattr(
        service,
        "send_message",
        lambda **kwargs: SimpleNamespace(
            id=uuid.uuid4(),
            content="Try breaking the problem into smaller steps.",
        ),
    )

    responses = [
        api.post(
            f"/ai/submissions/{submission['id']}/chat",
            json={"message": f"Help me with step {number}."},
        )
        for number in range(21)
    ]

    assert all(response.status_code == 200 for response in responses[:20])
    assert responses[20].status_code == 429
