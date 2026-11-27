"""Business logic for users and auth. Routes call these functions and stay thin."""

import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import Role
from app.core.security import CurrentUser
from app.users import supabase_auth
from app.users.models import User
from app.users.schemas import (
    ForgotPasswordIn,
    LoginIn,
    ResendConfirmationIn,
    ResetPasswordIn,
    SignupIn,
    SignupOut,
    UserOut,
)
from app.users.supabase_auth import AuthSession

logger = logging.getLogger(__name__)


def signup(db: Session, body: SignupIn) -> tuple[SignupOut, AuthSession | None]:
    """Create an account. Returns a session only when no email confirmation is needed."""
    session = supabase_auth.sign_up(body.email, body.password)
    if session is None:
        return SignupOut(user=None, confirm_email=True), None
    user = _ensure_user(db, session)
    return SignupOut(user=UserOut.model_validate(user), confirm_email=False), session


def login(db: Session, body: LoginIn) -> tuple[UserOut, AuthSession]:
    """Log in, setting up the account on first log-in."""
    session = supabase_auth.sign_in(body.email, body.password)
    return UserOut.model_validate(_ensure_user(db, session)), session


def refresh(db: Session, refresh_token: str | None) -> tuple[UserOut, AuthSession]:
    """Start a new session from the refresh cookie."""
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    session = supabase_auth.refresh(refresh_token)
    return UserOut.model_validate(_ensure_user(db, session)), session


def forgot_password(body: ForgotPasswordIn) -> None:
    """Email a reset link, if the account exists."""
    supabase_auth.request_password_reset(body.email)


def resend_confirmation(body: ResendConfirmationIn) -> None:
    """Email the confirmation link again, if there's an unconfirmed account."""
    supabase_auth.resend_confirmation(body.email)


def reset_password(db: Session, body: ResetPasswordIn) -> tuple[UserOut, AuthSession]:
    """Set a new password from a reset link, and log in."""
    session = supabase_auth.reset_password(body.token_hash, body.password)
    return UserOut.model_validate(_ensure_user(db, session)), session


def logout(access_token: str | None) -> None:
    """Revoke the session at Supabase. The caller clears the cookies either way."""
    if access_token:
        supabase_auth.sign_out(access_token)


def get_user(db: Session, current: CurrentUser) -> UserOut:
    """The signed-in user's account."""
    user = db.get(User, uuid.UUID(current.id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not set up. Log in again")
    return UserOut.model_validate(user)


def _ensure_user(db: Session, session: AuthSession) -> User:
    """Create the users row on first log-in, and promote a newly allowlisted professor.

    Never demotes, so removing an email from the allowlist needs a manual change.
    """
    role = Role.PROFESSOR if session.email in get_settings().professor_emails_set else Role.STUDENT
    user = db.get(User, session.user_id)
    if user is None:
        # An account deleted in Supabase and created again keeps its email but gets a new
        # id. Move the old row to the new id (keeping its role) instead of failing on the
        # unique email.
        user = db.scalars(select(User).where(User.email == session.email)).first()
        if user is not None:
            user.id = session.user_id
            if role == Role.PROFESSOR:
                user.role = Role.PROFESSOR
        else:
            user = User(id=session.user_id, email=session.email, role=role)
            db.add(user)
    elif user.role == Role.STUDENT and role == Role.PROFESSOR:
        user.role = Role.PROFESSOR
    else:
        return user

    try:
        db.commit()
    except IntegrityError:
        # Two first log-ins at once: the other request created the row.
        db.rollback()
        existing = db.get(User, session.user_id)
        if existing is None:
            raise
        return existing
    db.refresh(user)
    logger.info("User saved user_id=%s role=%s", user.id, user.role)
    return user
