import os
from unittest.mock import patch

# create_engine does not connect, so a dummy URL is enough when .env is absent.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_ok():
    with patch("app.main.engine"):
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}


def test_health_db_unreachable():
    with patch("app.main.engine") as engine:
        engine.connect.side_effect = Exception("db down")
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "unreachable"}
