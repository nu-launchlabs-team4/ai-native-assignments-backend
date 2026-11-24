"""Business logic for AI chat. Routes call these functions and stay thin."""

import uuid
from pathlib import Path

import anthropic
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.models import ChatMessage
from app.assignments.models import Assignment
from app.core.config import get_settings
from app.core.constants import AIPolicy, Step, SubmissionStatus
from app.core.security import CurrentUser
from app.submissions.models import Submission

MODEL = "claude-haiku-4-5-20251001"
PROMPT_DIR = Path(__file__).parent / "prompts"
CHAT_NOT_AVAILABLE = "AI chat is not available for this submission"


def _load_prompt(help_level: str) -> str:
    """Load the tutor instructions for the assignment's help level."""
    prompt_path = PROMPT_DIR / f"{help_level}.txt"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The AI tutor prompt is unavailable",
        ) from exc


def _student_context(submission: Submission) -> str:
    """Build context using only this assignment and this student's saved work."""
    assignment = submission.assignment
    questions = {question.id: question for question in assignment.questions}

    sections = [
        f"Assignment: {assignment.title}",
        f"Instructions: {assignment.instructions}",
        "Assignment questions:",
    ]

    for question in assignment.questions:
        sections.append(
            f"Question {question.position} ({question.answer_type.value}): {question.prompt}"
        )
        if question.starter_code:
            sections.append(f"Starter code: {question.starter_code}")

    for step, label in (
        (Step.ATTEMPT, "Student's original attempt"),
        (Step.REVISE, "Student's revision"),
    ):
        answers = submission.answers_for(step)
        if not answers:
            continue

        sections.append(f"{label}:")
        for question_id, answer in answers.items():
            question = questions.get(question_id)
            if question is not None:
                sections.append(f"Question {question.position} answer:\n{answer}")

    if submission.approach_note:
        sections.append(f"Student's approach note: {submission.approach_note}")

    return "\n\n".join(sections)


def _response_text(response: anthropic.types.Message) -> str:
    """Extract text blocks from an Anthropic response."""
    return "\n".join(block.text for block in response.content if block.type == "text").strip()


def _review_reply(client: anthropic.Anthropic, reply: str, context: str) -> str:
    """Rewrite a reply that contains a complete assignment solution."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=700,
        system=(
            "You are an academic-integrity reviewer for an AI tutor. "
            "Review the tutor reply against the assignment and student context. "
            "If the reply gives a complete solution, finished function, full code, "
            "or final answer, rewrite it as a concise hint that asks the student "
            "to do the key reasoning themselves. Otherwise preserve its helpful "
            "meaning. Never add a solution. Return only the final student-facing reply."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Assignment and student context:\n{context}\n\nTutor reply to review:\n{reply}"
                ),
            }
        ],
    )
    return _response_text(response) or (
        "Which part of your approach would you like to examine next?"
    )


def send_message(
    db: Session,
    student: CurrentUser,
    submission_id: uuid.UUID,
    message: str,
) -> ChatMessage:
    """Validate access, ask the tutor, and persist both sides of the exchange."""
    submission = db.scalar(
        select(Submission)
        .where(
            Submission.id == submission_id,
            Submission.student_id == uuid.UUID(student.id),
        )
        .options(
            selectinload(Submission.assignment).selectinload(Assignment.questions),
            selectinload(Submission.entries),
        )
    )

    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission not found",
        )

    if (
        submission.attempt_submitted_at is None
        or submission.current_step == Step.EXPLAIN
        or submission.status == SubmissionStatus.SUBMITTED
        or submission.assignment.ai_policy == AIPolicy.PROHIBITED
        or submission.current_step not in (Step.FEEDBACK, Step.EVALUATE, Step.REVISE)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=CHAT_NOT_AVAILABLE,
        )

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI chat is not configured",
        )

    prompt = _load_prompt(submission.assignment.help_level.value)
    context = _student_context(submission)

    previous_messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.submission_id == submission.id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    ).all()

    student_message = ChatMessage(
        submission_id=submission.id,
        role="student",
        content=message,
    )
    db.add(student_message)
    db.commit()

    history = [
        {
            "role": "assistant" if item.role == "assistant" else "user",
            "content": item.content,
        }
        for item in previous_messages
    ]
    history.append({"role": "user", "content": message})

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=700,
            system=(
                f"{prompt}\n\n"
                "Use only the assignment and student context supplied below. "
                "Do not reveal a complete solution.\n\n"
                f"{context}"
            ),
            messages=history,
        )
        draft_reply = _response_text(response)

        if not draft_reply:
            raise RuntimeError("The AI tutor returned an empty response")

        reply = _review_reply(client, draft_reply, context)

    except anthropic.APIError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI tutor is temporarily unavailable",
        ) from exc

    assistant_message = ChatMessage(
        submission_id=submission.id,
        role="assistant",
        content=reply,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return assistant_message
