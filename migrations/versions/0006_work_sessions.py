"""Create work_sessions and activity_events.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUM_LENGTH = 32
TABLES = ("work_sessions", "activity_events")


def upgrade() -> None:
    op.create_table(
        "work_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "submission_id",
            sa.Uuid(),
            sa.ForeignKey("submissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_work_sessions_submission_id", "work_sessions", ["submission_id"])

    op.create_table(
        "activity_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("work_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column("step", sa.String(ENUM_LENGTH), nullable=False),
        sa.Column(
            "question_id",
            sa.Uuid(),
            sa.ForeignKey("questions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("detail", sa.JSON(), nullable=True),
    )
    op.create_index("ix_activity_events_session_id", "activity_events", ["session_id"])

    # Same as 0001: block Supabase's REST API from these tables.
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
