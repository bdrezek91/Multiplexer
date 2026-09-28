"""add Jev decision duration

Revision ID: f4a8b9c2d1e0
Revises: 9c1f0d7b42aa
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a8b9c2d1e0"
down_revision = "9c1f0d7b42aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jev_shadow_result",
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("jev_shadow_result", "duration_ms")
