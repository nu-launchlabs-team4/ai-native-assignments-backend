from fastapi.testclient import TestClient


def test_request_id_is_generated(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Request-ID"]


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_404_uses_error_shape(client: TestClient) -> None:
    response = client.get("/does-not-exist", headers={"X-Request-ID": "req-404"})
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "request_id": "req-404"}
    }
    assert response.headers["X-Request-ID"] == "req-404"
