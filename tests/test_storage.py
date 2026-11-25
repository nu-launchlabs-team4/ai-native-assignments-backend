from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.assignments import storage
from app.core.config import get_settings

PDF_CONTENT = b"%PDF-1.7\n%%EOF"
SERVICE_KEY = "test-service-role-key"


@pytest.fixture
def service_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "supabase_service_role_key", SERVICE_KEY)


def fake_post(status_code: int, calls: list[dict[str, Any]]) -> Callable[..., httpx.Response]:
    def post(url: str, **kwargs: Any) -> httpx.Response:
        calls.append({"url": url, **kwargs})
        return httpx.Response(status_code, request=httpx.Request("POST", url))

    return post


def test_upload_sends_pdf_to_bucket(service_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(httpx, "post", fake_post(200, calls))

    storage.upload_pdf("assignments/a1/file.pdf", PDF_CONTENT)

    settings = get_settings()
    [call] = calls
    assert call["url"] == (
        f"{settings.supabase_url}/storage/v1/object/"
        f"{settings.supabase_pdf_bucket}/assignments/a1/file.pdf"
    )
    assert call["content"] == PDF_CONTENT
    assert call["headers"]["Authorization"] == f"Bearer {SERVICE_KEY}"
    assert call["headers"]["Content-Type"] == "application/pdf"


def test_storage_error_response_raises(service_key: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", fake_post(500, []))

    with pytest.raises(storage.StorageError):
        storage.upload_pdf("assignments/a1/file.pdf", PDF_CONTENT)


def test_missing_service_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "supabase_service_role_key", None)

    with pytest.raises(storage.StorageError):
        storage.upload_pdf("assignments/a1/file.pdf", PDF_CONTENT)
