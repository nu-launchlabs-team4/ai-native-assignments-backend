import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.assignments import storage
from app.assignments.service import MAX_PDF_BYTES
from app.core.constants import RATE_LIMIT_PDF_UPLOAD, Role
from tests.conftest import LoginAs
from tests.test_assignments import create_assignment, create_course

PROFESSOR_ID = str(uuid.uuid4())
OTHER_PROFESSOR_ID = str(uuid.uuid4())
STUDENT_ID = str(uuid.uuid4())

PDF_CONTENT = b"%PDF-1.7\nfake but valid enough for the signature check\n%%EOF"
UPLOADS_PER_LIMIT = int(RATE_LIMIT_PDF_UPLOAD.split("/")[0])


@pytest.fixture
def uploaded() -> dict[str, bytes]:
    """Replace Supabase Storage with a dict, so tests can see what was uploaded."""
    return {}


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch: pytest.MonkeyPatch, uploaded: dict[str, bytes]) -> None:
    def upload_pdf(path: str, content: bytes) -> None:
        uploaded[path] = content

    monkeypatch.setattr(storage, "upload_pdf", upload_pdf)


def upload(api: TestClient, assignment_id: str, content: bytes = PDF_CONTENT) -> httpx.Response:
    files = {"file": ("homework.pdf", content, "application/pdf")}
    return api.post(f"/assignments/{assignment_id}/pdf", files=files)


def professors_assignment_id(api: TestClient, login_as: LoginAs) -> str:
    login_as(Role.PROFESSOR, PROFESSOR_ID)
    return str(create_assignment(api, create_course(api))["id"])


def test_professor_uploads_pdf(
    api: TestClient, login_as: LoginAs, uploaded: dict[str, bytes]
) -> None:
    assignment_id = professors_assignment_id(api, login_as)

    response = upload(api, assignment_id)

    assert response.status_code == 200
    source_pdf = response.json()["source_pdf"]
    assert source_pdf.startswith(f"assignments/{assignment_id}/")
    assert source_pdf.endswith(".pdf")
    assert uploaded == {source_pdf: PDF_CONTENT}
    assert api.get(f"/assignments/{assignment_id}").json()["source_pdf"] == source_pdf


def test_pdf_at_the_size_limit_is_accepted(api: TestClient, login_as: LoginAs) -> None:
    assignment_id = professors_assignment_id(api, login_as)
    content = PDF_CONTENT.ljust(MAX_PDF_BYTES, b"0")

    response = upload(api, assignment_id, content)

    assert response.status_code == 200


def test_pdf_over_the_size_limit_is_rejected(
    api: TestClient, login_as: LoginAs, uploaded: dict[str, bytes]
) -> None:
    assignment_id = professors_assignment_id(api, login_as)
    content = PDF_CONTENT.ljust(MAX_PDF_BYTES + 1, b"0")

    response = upload(api, assignment_id, content)

    assert response.status_code == 413
    assert uploaded == {}


def test_file_that_is_not_a_pdf_is_rejected(
    api: TestClient, login_as: LoginAs, uploaded: dict[str, bytes]
) -> None:
    assignment_id = professors_assignment_id(api, login_as)

    # Named and labelled as a PDF, but the bytes say otherwise.
    response = upload(api, assignment_id, b"MZ\x90\x00 not a pdf")

    assert response.status_code == 415
    assert response.json()["error"]["message"] == "File must be a PDF"
    assert uploaded == {}


def test_other_professors_assignment_is_not_found(
    api: TestClient, login_as: LoginAs, uploaded: dict[str, bytes]
) -> None:
    assignment_id = professors_assignment_id(api, login_as)

    login_as(Role.PROFESSOR, OTHER_PROFESSOR_ID)
    response = upload(api, assignment_id)

    assert response.status_code == 404
    assert uploaded == {}


def test_student_cannot_upload_pdf(api: TestClient, login_as: LoginAs) -> None:
    assignment_id = professors_assignment_id(api, login_as)

    login_as(Role.STUDENT, STUDENT_ID)
    response = upload(api, assignment_id)

    assert response.status_code == 403


def test_missing_file_is_invalid(api: TestClient, login_as: LoginAs) -> None:
    assignment_id = professors_assignment_id(api, login_as)

    response = api.post(f"/assignments/{assignment_id}/pdf")

    assert response.status_code == 422


def test_storage_failure_is_bad_gateway(
    api: TestClient, login_as: LoginAs, monkeypatch: pytest.MonkeyPatch
) -> None:
    assignment_id = professors_assignment_id(api, login_as)

    def failing_upload(path: str, content: bytes) -> None:
        raise storage.StorageError("Upload failed: ConnectError")

    monkeypatch.setattr(storage, "upload_pdf", failing_upload)
    response = upload(api, assignment_id)

    assert response.status_code == 502
    assert api.get(f"/assignments/{assignment_id}").json()["source_pdf"] is None


def test_uploads_are_rate_limited(api: TestClient, login_as: LoginAs) -> None:
    assignment_id = professors_assignment_id(api, login_as)
    for _ in range(UPLOADS_PER_LIMIT):
        assert upload(api, assignment_id).status_code == 200

    response = upload(api, assignment_id)

    assert response.status_code == 429


def test_published_assignment_keeps_its_pdf(
    api: TestClient, login_as: LoginAs, uploaded: dict[str, bytes]
) -> None:
    assignment_id = professors_assignment_id(api, login_as)
    assert api.post(f"/assignments/{assignment_id}/publish").status_code == 200

    response = upload(api, assignment_id)

    assert response.status_code == 409
    assert uploaded == {}
