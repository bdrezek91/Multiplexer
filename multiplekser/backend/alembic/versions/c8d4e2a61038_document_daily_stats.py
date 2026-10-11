"""Persist daily completion counters beyond document retention.

Revision ID: c8d4e2a61038
Revises: a7c9e1d2f4b6
"""
from alembic import op
import sqlalchemy as sa

revision = "c8d4e2a61038"
down_revision = "a7c9e1d2f4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_daily_stats",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("documents", sa.Integer(), nullable=False),
    )
    # Historical snapshot covers completions through 2026-10-08. All 18 later
    # completions are still present at rollout (7 + 11, verified against counters).
    op.execute("""
        INSERT INTO document_daily_stats (user_id, day, documents)
        SELECT user_id, (created_at AT TIME ZONE 'Europe/Warsaw')::date, count(*)
        FROM document
        WHERE status = 'done'
          AND created_at >= TIMESTAMPTZ '2026-10-09 00:00:00 Europe/Warsaw'
        GROUP BY user_id, (created_at AT TIME ZONE 'Europe/Warsaw')::date
    """)


def downgrade() -> None:
    op.drop_table("document_daily_stats")
