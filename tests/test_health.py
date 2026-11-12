from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}


def test_health_db_unreachable(client: TestClient, db: MagicMock) -> None:
    db.execute.side_effect = Exception("db down")
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "db": "unreachable"}
