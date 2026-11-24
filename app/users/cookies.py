"""Session cookies. Tokens live only here, never in a response body.

HttpOnly keeps them away from JavaScript, SameSite=Lax stops other sites from
sending them on cross-site POSTs, and Secure is on everywhere except local http.
Path is / because the browser reaches the API through the frontend's /api rewrite.
"""

from fastapi import Response

from app.core.config import get_settings
from app.core.constants import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_COOKIE_MAX_AGE_SECONDS,
    REFRESH_TOKEN_COOKIE,
)
from app.users.supabase_auth import AuthSession


def set_session_cookies(response: Response, session: AuthSession) -> None:
    """Put the session's tokens in httpOnly cookies."""
    secure = get_settings().cookie_secure
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        session.access_token,
        max_age=session.expires_in,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        session.refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE_SECONDS,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )


def clear_session_cookies(response: Response) -> None:
    """Remove both session cookies."""
    secure = get_settings().cookie_secure
    for name in (ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE):
        response.delete_cookie(name, path="/", httponly=True, secure=secure, samesite="lax")
