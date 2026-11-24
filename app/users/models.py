"""SQLAlchemy models for users.

One row per Supabase Auth user, holding the role the backend trusts. The role
lives here, not in the token, because Supabase lets users edit their own metadata.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.assignments.models import enum_column
from app.core.constants import Role
from app.core.database import Base

MAX_EMAIL_CHARS = 320


class User(Base):
    __tablename__ = "users"

    # The Supabase Auth user id (the JWT "sub"), so it matches professor_id and student_id.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(MAX_EMAIL_CHARS), unique=True)
    role: Mapped[Role] = mapped_column(enum_column(Role))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
