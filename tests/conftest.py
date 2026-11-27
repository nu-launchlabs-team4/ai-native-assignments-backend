import os
import uuid
from collections.abc import Callable, Iterator
from unittest.mock import MagicMock

import pytest

# Settings are required at import time. Placeholders are enough because the database is mocked.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "test-key")
# Tests never shell out to Claude Code or call the API: the AI uses canned replies.
os.environ["AI_PROVIDER"] = "fake"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.assignments.models import Enrollment  # noqa: E402
from app.core.constants import Role  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import CurrentUser, get_current_user  # noqa: E402
from app.main import app  # noqa: E402

LoginAs = Callable[[Role, str], None]


@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:
    # Every test client shares one IP, so without a reset the whole suite
    # shares one 60/minute budget and fails once it grows past that.
    limiter.reset()


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(db: MagicMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
    # Feature tests skip the cookie and token check (tests/test_auth.py covers it)
    # and replace the signed-in user directly.
    def log_in(role: Role, user_id: str) -> None:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id, role=role)

    return log_in


def enroll(db_session: Session, course_id: str, *student_ids: str) -> None:
    """Put students in a course, as joining with its code does."""
    for student_id in student_ids:
        db_session.add(Enrollment(course_id=uuid.UUID(course_id), student_id=uuid.UUID(student_id)))
    db_session.commit()
