from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.constants import Role

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: str
    role: Role


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # TODO(wmw01): verify the Supabase JWT in credentials.credentials (#4).
    #   - Check signature, expiry and audience against the Supabase project.
    #   - Build CurrentUser from the verified claims (sub -> id, role).
    #   - Set request.state.user_id = user.id so rate limits key on the user.
    # Until then no token is trusted, so a forged token can never reach a protected route.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Token verification is not implemented yet",
    )


def require_role(role: Role) -> Callable[..., CurrentUser]:
    """Dependency factory: `Depends(require_role(Role.PROFESSOR))`."""

    def checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if user.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return checker
