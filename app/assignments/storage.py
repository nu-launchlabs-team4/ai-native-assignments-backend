"""Uploads files to Supabase Storage. Knows nothing about users or assignments."""

import httpx

from app.core.config import get_settings

UPLOAD_TIMEOUT_SECONDS = 30


class StorageError(Exception):
    """The file could not be stored."""


def upload_pdf(path: str, content: bytes) -> None:
    """Upload a PDF to the assignment PDF bucket at the given path."""
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise StorageError("SUPABASE_SERVICE_ROLE_KEY is not set")

    url = f"{settings.supabase_url}/storage/v1/object/{settings.supabase_pdf_bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
        "Content-Type": "application/pdf",
    }
    try:
        response = httpx.post(url, content=content, headers=headers, timeout=UPLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise StorageError(f"Upload failed: {type(error).__name__}") from error
