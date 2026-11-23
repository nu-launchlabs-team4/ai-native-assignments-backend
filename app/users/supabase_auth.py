"""Calls to Supabase Auth's REST API. Only the backend talks to Supabase.

Errors become HTTPExceptions with messages people can act on. Tokens and
passwords are never logged.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
UNAVAILABLE = "Sign-in is unavailable right now. Try again in a minute"
SESSION_EXPIRED = "Session expired. Log in again"
WRONG_CREDENTIALS = "That email and password don't match. Check them and try again."

# Supabase error_code -> (our status, our message). None keeps Supabase's message.
_ERRORS: dict[str, tuple[int, str | None]] = {
    "invalid_credentials": (status.HTTP_401_UNAUTHORIZED, WRONG_CREDENTIALS),
    "email_not_confirmed": (status.HTTP_403_FORBIDDEN, "Confirm your email before logging in"),
    "user_already_exists": (
        status.HTTP_409_CONFLICT,
        "An account with this email already exists",
    ),
    "email_exists": (status.HTTP_409_CONFLICT, "An account with this email already exists"),
    "weak_password": (status.HTTP_422_UNPROCESSABLE_CONTENT, None),
    "refresh_token_not_found": (status.HTTP_401_UNAUTHORIZED, SESSION_EXPIRED),
    "refresh_token_already_used": (status.HTTP_401_UNAUTHORIZED, SESSION_EXPIRED),
    "session_not_found": (status.HTTP_401_UNAUTHORIZED, SESSION_EXPIRED),
}


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: uuid.UUID
    email: str


def sign_up(email: str, password: str) -> AuthSession | None:
    """Create an account. Returns None when Supabase wants the email confirmed first."""
    data = _post("/signup", {"email": email, "password": password})
    # With confirmation on, Supabase returns only the user (and, for an email that's
    # already taken, a fake one so accounts can't be discovered). Either way: no session.
    if "access_token" not in data:
        return None
    return _session(data)


def sign_in(email: str, password: str) -> AuthSession:
    """Log in with email and password."""
    return _session(_post("/token?grant_type=password", {"email": email, "password": password}))


def refresh(refresh_token: str) -> AuthSession:
    """Swap a refresh token for a new session. Supabase refresh tokens are single-use."""
    try:
        data = _post("/token?grant_type=refresh_token", {"refresh_token": refresh_token})
    except HTTPException as exc:
        # Any rejected token (Supabase also says "validation_failed" for a malformed one)
        # means the person has to log in again, which the frontend knows from a 401.
        if exc.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_CONTENT):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, SESSION_EXPIRED) from exc
        raise
    return _session(data)


def sign_out(access_token: str) -> None:
    """Revoke the session's refresh tokens. Failures are logged, not raised."""
    try:
        with _client() as client:
            response = client.post(
                "/logout?scope=local", headers={"Authorization": f"Bearer {access_token}"}
            )
        if response.status_code >= 400:
            logger.info("Supabase logout returned status=%s", response.status_code)
    except httpx.HTTPError as exc:
        logger.warning("Supabase logout failed: %s", type(exc).__name__)


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=f"{settings.supabase_url.rstrip('/')}/auth/v1",
        headers={"apikey": settings.supabase_publishable_key},
        timeout=TIMEOUT_SECONDS,
    )


def _post(path: str, body: dict[str, str]) -> dict[str, Any]:
    try:
        with _client() as client:
            response = client.post(path, json=body)
    except httpx.HTTPError as exc:
        logger.warning("Supabase Auth unreachable: %s", type(exc).__name__)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from exc

    if response.status_code < 400:
        return response.json()
    raise _error(response)


def _error(response: httpx.Response) -> HTTPException:
    try:
        payload: dict[str, Any] = response.json()
    except ValueError:
        payload = {}
    code = str(payload.get("error_code") or payload.get("error") or "")
    supabase_message = str(payload.get("msg") or payload.get("error_description") or "")
    logger.info("Supabase Auth error status=%s code=%s", response.status_code, code)

    if code in _ERRORS:
        status_code, message = _ERRORS[code]
        return HTTPException(status_code=status_code, detail=message or supabase_message)
    if code == "invalid_grant":  # older Supabase versions, for a wrong password
        return HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG_CREDENTIALS)
    if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again in a minute"
        )
    if response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_422_UNPROCESSABLE_CONTENT):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            supabase_message or "Check the email and password",
        )
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)


def _session(data: dict[str, Any]) -> AuthSession:
    user = data["user"]
    return AuthSession(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=int(data["expires_in"]),
        user_id=uuid.UUID(user["id"]),
        email=str(user["email"]).lower(),
    )
