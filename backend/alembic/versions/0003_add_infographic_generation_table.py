"""Add infographic generation table

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-02 00:00:00.000000

Phase 4: Infographic Generation via Cloudflare Workers AI
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "infographic_generations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("post_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False, server_default="cloudflare"),
        sa.Column("model", sa.String(200), nullable=False, server_default="@cf/black-forest-labs/flux-2-klein-9b"),
        sa.Column("status", sa.String(50), nullable=False, server_default="PENDING"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1536"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="864"),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_infographic_generations_post_id", "infographic_generations", ["post_id"])
    op.create_index("ix_infographic_generations_status", "infographic_generations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_infographic_generations_status", table_name="infographic_generations")
    op.drop_index("ix_infographic_generations_post_id", table_name="infographic_generations")
    op.drop_table("infographic_generations")
