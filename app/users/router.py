from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.constants import ACCESS_TOKEN_COOKIE, RATE_LIMIT_AUTH, REFRESH_TOKEN_COOKIE
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import CurrentUser, get_current_user
from app.users import service
from app.users.cookies import clear_session_cookies, set_session_cookies
from app.users.schemas import LoginIn, SignupIn, SignupOut, UserOut

router = APIRouter(prefix="/users", tags=["users"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]
AccessCookie = Annotated[str | None, Cookie(alias=ACCESS_TOKEN_COOKIE)]
RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_TOKEN_COOKIE)]


@auth_router.post("/signup", response_model=SignupOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMIT_AUTH)
def signup(request: Request, response: Response, body: SignupIn, db: DbSession) -> SignupOut:
    result, session = service.signup(db, body)
    if session is not None:
        set_session_cookies(response, session)
    return result


@auth_router.post("/login", response_model=UserOut)
@limiter.limit(RATE_LIMIT_AUTH)
def login(request: Request, response: Response, body: LoginIn, db: DbSession) -> UserOut:
    user, session = service.login(db, body)
    set_session_cookies(response, session)
    return user


@auth_router.post("/refresh", response_model=UserOut)
@limiter.limit(RATE_LIMIT_AUTH)
def refresh(
    request: Request, response: Response, db: DbSession, refresh_token: RefreshCookie = None
) -> UserOut:
    user, session = service.refresh(db, refresh_token)
    set_session_cookies(response, session)
    return user


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(RATE_LIMIT_AUTH)
def logout(request: Request, response: Response, access_token: AccessCookie = None) -> None:
    service.logout(access_token)
    clear_session_cookies(response)


@auth_router.get("/me", response_model=UserOut)
def me(db: DbSession, user: Annotated[CurrentUser, Depends(get_current_user)]) -> UserOut:
    return service.get_user(db, user)
