"""Add course join codes and enrollments.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-25
"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOIN_CODE_LENGTH = 9
# A copy of app/assignments/join_codes.py, so this migration never changes with the app.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTWXYZ"


def _join_code() -> str:
    chars = "".join(secrets.choice(ALPHABET) for _ in range(8))
    return f"{chars[:4]}-{chars[4:]}"


def upgrade() -> None:
    op.add_column("courses", sa.Column("join_code", sa.String(JOIN_CODE_LENGTH), nullable=True))
    # Existing courses get a code before the column becomes required.
    connection = op.get_bind()
    used: set[str] = set()
    for (course_id,) in connection.execute(sa.text("SELECT id FROM courses")).all():
        code = _join_code()
        while code in used:
            code = _join_code()
        used.add(code)
        connection.execute(
            sa.text("UPDATE courses SET join_code = :code WHERE id = :id"),
            {"code": code, "id": course_id},
        )
    op.alter_column("courses", "join_code", nullable=False)
    op.create_unique_constraint("courses_join_code_key", "courses", ["join_code"])

    op.create_table(
        "enrollments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Uuid(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("course_id", "student_id"),
    )
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"])
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])

    # Same as 0001: block Supabase's REST API from this table.
    op.execute("ALTER TABLE enrollments ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("enrollments")
    op.drop_constraint("courses_join_code_key", "courses", type_="unique")
    op.drop_column("courses", "join_code")
