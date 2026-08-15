"""Initial content plan tables

Revision ID: 0001
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "content_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("main_subject", sa.String(500), nullable=False),
        sa.Column("number_of_days", sa.Integer(), nullable=False),
        sa.Column("audience", sa.String(500), nullable=False),
        sa.Column("difficulty", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "day_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_number", sa.Integer(), nullable=False),
        sa.Column("main_subject", sa.String(500), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(100), nullable=False),
        sa.Column("category", sa.String(200), nullable=False),
        sa.Column("learning_objective", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["content_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_day_topics_plan_id", "day_topics", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_day_topics_plan_id", table_name="day_topics")
    op.drop_table("day_topics")
    op.drop_table("content_plans")
