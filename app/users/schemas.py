"""Pydantic request and response schemas for users and auth."""

import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.constants import Role
from app.users.models import MAX_EMAIL_CHARS

# Supabase checks the address properly; this only rejects obvious mistakes early.
Email = Annotated[
    str,
    Field(min_length=3, max_length=MAX_EMAIL_CHARS, pattern=r"^[^@\s]+@[^@\s]+$"),
    AfterValidator(str.lower),
]
# 72 is bcrypt's limit, which Supabase uses for passwords.
Password = Annotated[str, Field(min_length=8, max_length=72)]


class SignupIn(BaseModel):
    email: Email
    password: Password


class LoginIn(BaseModel):
    email: Email
    # No length rule here: a short password is simply wrong, and should say so.
    password: Annotated[str, Field(min_length=1, max_length=72)]


class ForgotPasswordIn(BaseModel):
    email: Email


class ResetPasswordIn(BaseModel):
    # The one-time code from the reset email's link.
    token_hash: str = Field(min_length=1, max_length=512)
    password: Password


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: Role


class SignupOut(BaseModel):
    # None until the email is confirmed: the account is set up on first log-in.
    user: UserOut | None
    confirm_email: bool
