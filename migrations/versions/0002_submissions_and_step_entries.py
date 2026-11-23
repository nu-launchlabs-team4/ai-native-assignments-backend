"""Create submissions and step_entries.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUM_LENGTH = 32
TABLES = ("submissions", "step_entries")


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Uuid(),
            sa.ForeignKey("assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column("current_step", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column("confidence", sa.SmallInteger(), nullable=True),
        sa.Column("approach_note", sa.Text(), nullable=True),
        sa.Column("attempt_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluation_verdict", sa.String(ENUM_LENGTH), nullable=True),
        sa.Column("evaluation_test_case", sa.Text(), nullable=True),
        sa.Column("interview_answers", sa.JSON(), nullable=True),
        sa.Column("ai_declaration", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("assignment_id", "student_id"),
        sa.CheckConstraint("confidence BETWEEN 1 AND 5", name="ck_submissions_confidence_range"),
    )
    op.create_index("ix_submissions_assignment_id", "submissions", ["assignment_id"])
    op.create_index("ix_submissions_student_id", "submissions", ["student_id"])

    op.create_table(
        "step_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.Uuid(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.UniqueConstraint("submission_id", "step", "question_id"),
    )
    op.create_index("ix_step_entries_submission_id", "step_entries", ["submission_id"])
    op.create_index("ix_step_entries_question_id", "step_entries", ["question_id"])

    # Same as 0001: block Supabase's REST API from these tables.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
