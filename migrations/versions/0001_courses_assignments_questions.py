"""Create courses, assignments and questions.

Revision ID: 0001
Revises:
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUM_LENGTH = 32
TABLES = ("courses", "assignments", "questions")


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("professor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_courses_professor_id", "courses", ["professor_id"])

    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "course_id",
            sa.Uuid(),
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("source_pdf", sa.String(500), nullable=True),
        sa.Column("ai_policy", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column("help_level", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column("final_check", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_assignments_course_id", "assignments", ["course_id"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Uuid(),
            sa.ForeignKey("assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer_type", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("starter_code", sa.Text(), nullable=True),
        sa.UniqueConstraint("assignment_id", "position"),
    )
    op.create_index("ix_questions_assignment_id", "questions", ["assignment_id"])

    # Supabase serves the public schema over its REST API. With RLS on and no
    # policies, that API can read nothing, while the backend's own connection
    # (the postgres role) is unaffected.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
