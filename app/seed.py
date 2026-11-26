"""Seed demo data: one professor, three students enrolled in one course, and one published
assignment.

Run it with:

    docker compose run --rm api python -m app.seed

Safe to rerun. Accounts are found by email, and the course and assignment by
title, so a second run creates nothing new. It never deletes anything.

Each account is a Supabase Auth user, created with the Auth admin API, plus a
row in our users table with the same id. The role lives in that row, as the
auth code (app/users/service.py) expects. Writing the row here means the demo
professor is a professor without being on the PROFESSOR_EMAILS allowlist, and
the first login just finds the row.

Needs SUPABASE_SECRET_KEY and SEED_PASSWORD in .env.
"""

import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import Assignment, Course, Enrollment, Question
from app.assignments.service import unused_join_code
from app.core.config import get_settings
from app.core.constants import AIPolicy, AnswerType, FinalCheck, HelpLevel, Role
from app.core.database import SessionLocal
from app.users.models import User

logger = logging.getLogger(__name__)

ADMIN_USERS_PATH = "/auth/v1/admin/users"
USERS_PER_PAGE = 1000


@dataclass(frozen=True)
class DemoUser:
    email: str
    name: str
    role: Role


PROFESSOR = DemoUser("demo-professor@example.com", "Demo Professor", Role.PROFESSOR)
STUDENTS = (
    DemoUser("demo-student-1@example.com", "Demo Student 1", Role.STUDENT),
    DemoUser("demo-student-2@example.com", "Demo Student 2", Role.STUDENT),
    DemoUser("demo-student-3@example.com", "Demo Student 3", Role.STUDENT),
)

COURSE_TITLE = "Intro to Programming (Demo)"
ASSIGNMENT_TITLE = "Week 3: Counting and loops"

# Matches the frontend's mock assignment, so the workspace looks the same on real data.
ASSIGNMENT_INSTRUCTIONS = (
    "This assignment has three questions: one in code, one written and one in math.\n\n"
    "Before you ask the AI tutor for help, answer each question yourself, rate your "
    "confidence and describe your approach."
)
QUESTIONS: tuple[dict[str, Any], ...] = (
    {
        "answer_type": AnswerType.CODE,
        "language": "python",
        "prompt": (
            "Write a function count_vowels(text) that returns how many vowels "
            "(a, e, i, o, u) are in a string.\n\n"
            "Uppercase and lowercase letters both count. Letters like y do not count.\n\n"
            'For example, count_vowels("Hello World") returns 3, and count_vowels("") returns 0.'
        ),
        "starter_code": (
            "def count_vowels(text):\n"
            "    # Your code here\n"
            "    pass\n"
            "\n"
            "\n"
            'print(count_vowels("Hello World"))\n'
        ),
    },
    {
        "answer_type": AnswerType.TEXT,
        "prompt": (
            "In a few sentences, explain how your count_vowels function works.\n\n"
            "Why did you choose a loop, a comprehension or another approach?"
        ),
    },
    {
        "answer_type": AnswerType.MATH,
        "prompt": (
            "Your function checks each character once. For a string of length n, "
            "the work is T(n) = 3n + 2n + 5.\n\n"
            "Simplify T(n), showing each step on its own line."
        ),
    },
)


class AuthAdmin(Protocol):
    def ensure_user(self, user: DemoUser, password: str) -> uuid.UUID:
        """Create the Supabase account, or update it if the email exists. Returns its id."""
        ...


@dataclass(frozen=True)
class SeedResult:
    professor_id: uuid.UUID
    student_ids: tuple[uuid.UUID, ...]
    course_id: uuid.UUID
    join_code: str
    assignment_id: uuid.UUID


class SupabaseAuthAdmin:
    """Creates and updates Supabase Auth users with the admin API."""

    def __init__(self, client: httpx.Client) -> None:
        # The client carries the base URL and the secret key headers.
        self._client = client

    def ensure_user(self, user: DemoUser, password: str) -> uuid.UUID:
        attributes = {
            "password": password,
            "email_confirm": True,
            "user_metadata": {"name": user.name},
        }
        existing_id = self._find_by_email(user.email)
        if existing_id is None:
            response = self._client.post(ADMIN_USERS_PATH, json={"email": user.email, **attributes})
            response.raise_for_status()
            return uuid.UUID(response.json()["id"])
        # Rerunning puts the password back, in case someone changed it.
        response = self._client.put(f"{ADMIN_USERS_PATH}/{existing_id}", json=attributes)
        response.raise_for_status()
        return existing_id

    def _find_by_email(self, email: str) -> uuid.UUID | None:
        page = 1
        while True:
            response = self._client.get(
                ADMIN_USERS_PATH, params={"page": page, "per_page": USERS_PER_PAGE}
            )
            response.raise_for_status()
            users = response.json().get("users", [])
            for account in users:
                if (account.get("email") or "").lower() == email.lower():
                    return uuid.UUID(account["id"])
            if len(users) < USERS_PER_PAGE:
                return None
            page += 1


def seed(db: Session, auth: AuthAdmin, password: str) -> SeedResult:
    """Create whatever demo data is missing, and leave the rest as it is."""
    professor_id = _ensure_account(db, auth, PROFESSOR, password)
    student_ids = tuple(_ensure_account(db, auth, student, password) for student in STUDENTS)

    course = db.scalar(
        select(Course).where(Course.professor_id == professor_id, Course.title == COURSE_TITLE)
    )
    if course is None:
        course = Course(
            title=COURSE_TITLE, professor_id=professor_id, join_code=unused_join_code(db)
        )
        db.add(course)
        db.flush()
    _enroll(db, course, student_ids)

    assignment = db.scalar(
        select(Assignment).where(
            Assignment.course_id == course.id, Assignment.title == ASSIGNMENT_TITLE
        )
    )
    if assignment is None:
        assignment = Assignment(
            course_id=course.id,
            title=ASSIGNMENT_TITLE,
            instructions=ASSIGNMENT_INSTRUCTIONS,
            ai_policy=AIPolicy.PERMITTED,
            help_level=HelpLevel.HINTS,
            final_check=FinalCheck.AI_INTERVIEW,
            published_at=datetime.now(UTC),
            questions=[
                Question(position=position, **question)
                for position, question in enumerate(QUESTIONS, start=1)
            ],
        )
        db.add(assignment)
    elif assignment.published_at is None:
        # Existing questions are left alone, so students' saved answers stay valid.
        assignment.published_at = datetime.now(UTC)

    db.commit()
    return SeedResult(professor_id, student_ids, course.id, course.join_code, assignment.id)


def _enroll(db: Session, course: Course, student_ids: tuple[uuid.UUID, ...]) -> None:
    """Enroll the demo students, so the assignment shows up in their list."""
    enrolled = set(
        db.scalars(select(Enrollment.student_id).where(Enrollment.course_id == course.id))
    )
    for student_id in student_ids:
        if student_id not in enrolled:
            db.add(Enrollment(course_id=course.id, student_id=student_id))


def _ensure_account(db: Session, auth: AuthAdmin, demo: DemoUser, password: str) -> uuid.UUID:
    """The Supabase account and its users row, with the role set to the demo role."""
    user_id = auth.ensure_user(demo, password)
    user = db.get(User, user_id)
    if user is None:
        # Same as the login code: an account deleted and created again in Supabase
        # gets a new id, so move the old row to it instead of clashing on the email.
        user = db.scalar(select(User).where(User.email == demo.email))
        if user is None:
            user = User(id=user_id, email=demo.email, role=demo.role)
            db.add(user)
        else:
            user.id = user_id
    # Demo accounts always get their demo role back, even a student made professor.
    user.role = demo.role
    db.flush()
    return user_id


def supabase_headers(secret_key: str) -> dict[str, str]:
    headers = {"apikey": secret_key}
    if not secret_key.startswith("sb_"):
        # A legacy service_role key is a JWT and also goes in Authorization.
        # The newer sb_secret_ keys aren't JWTs and only go in apikey.
        headers["Authorization"] = f"Bearer {secret_key}"
    return headers


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    password = os.environ.get("SEED_PASSWORD")
    if not secret_key or not password:
        sys.exit("Set SUPABASE_SECRET_KEY and SEED_PASSWORD in .env first.")

    settings = get_settings()
    if settings.env == "production":
        sys.exit("Refusing to seed demo data when ENV=production.")

    with (
        httpx.Client(
            base_url=settings.supabase_url, headers=supabase_headers(secret_key), timeout=30
        ) as client,
        SessionLocal() as db,
    ):
        result = seed(db, SupabaseAuthAdmin(client), password)

    logger.info("Seeded demo data. Every account uses the SEED_PASSWORD from .env.")
    logger.info("Professor: %s", PROFESSOR.email)
    for student in STUDENTS:
        logger.info("Student:   %s", student.email)
    logger.info("Course:    %s (%s)", COURSE_TITLE, result.course_id)
    logger.info("Join code: %s (the demo students are already enrolled)", result.join_code)
    logger.info("Assignment: %s (%s)", ASSIGNMENT_TITLE, result.assignment_id)


if __name__ == "__main__":
    main()
