import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import ACCESS_TOKEN_COOKIE, Role
from app.core.database import get_db
from app.users.models import User

logger = logging.getLogger(__name__)

# Supabase signs access tokens with an asymmetric key (ES256 for this project), so the
# backend verifies them with the public key and holds no secret. HS256 is never
# accepted: it would mean trusting a shared secret this backend doesn't have.
ALLOWED_ALGORITHMS = ["ES256", "RS256"]
TOKEN_AUDIENCE = "authenticated"
JWKS_CACHE_SECONDS = 60 * 60

access_cookie = APIKeyCookie(name=ACCESS_TOKEN_COOKIE, auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: Role


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)


@lru_cache
def jwks_client() -> jwt.PyJWKClient:
    """Supabase's public signing keys, fetched once and cached."""
    base = get_settings().supabase_url.rstrip("/")
    return jwt.PyJWKClient(f"{base}/auth/v1/.well-known/jwks.json", lifespan=JWKS_CACHE_SECONDS)


def verify_access_token(token: str) -> dict[str, Any]:
    """Check the token's signature, expiry, audience and issuer, and return its claims."""
    try:
        signing_key = jwks_client().get_signing_key_from_jwt(token)
    except jwt.PyJWKClientConnectionError as exc:
        logger.warning("Could not fetch Supabase signing keys")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sign-in is unavailable right now. Try again in a minute",
        ) from exc
    except (jwt.PyJWKClientError, jwt.InvalidTokenError) as exc:
        raise _unauthorized("Invalid session") from exc

    issuer = f"{get_settings().supabase_url.rstrip('/')}/auth/v1"
    try:
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=TOKEN_AUDIENCE,
            issuer=issuer,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        # The frontend calls /auth/refresh when it sees this.
        raise _unauthorized("Session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid session") from exc


def get_current_user(
    request: Request,
    token: Annotated[str | None, Depends(access_cookie)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUser:
    """The signed-in user, from the access_token cookie. The role comes from our users table."""
    if not token:
        raise _unauthorized("Not logged in")

    claims = verify_access_token(token)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise _unauthorized("Invalid session") from exc

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("Account not set up. Log in again")

    # Rate limits key on the user from here on (see rate_limit_key).
    request.state.user_id = str(user.id)
    return CurrentUser(id=str(user.id), role=user.role)


def require_role(role: Role) -> Callable[..., CurrentUser]:
    """Dependency factory: `Depends(require_role(Role.PROFESSOR))`."""

    def checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker
