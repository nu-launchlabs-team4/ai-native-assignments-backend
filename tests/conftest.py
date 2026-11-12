import os
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

# Settings are required at import time. Placeholders are enough because the database is mocked.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", "test-key")

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(db: MagicMock) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
