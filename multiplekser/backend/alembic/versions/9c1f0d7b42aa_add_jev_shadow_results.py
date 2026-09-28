"""add jev shadow results

Revision ID: 9c1f0d7b42aa
Revises: 6178221fd25c
Create Date: 2026-09-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "9c1f0d7b42aa"
down_revision: Union[str, None] = "6178221fd25c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jev_shadow_result",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("rozpoznana_nazwa", sa.String(), nullable=False),
        sa.Column("matcher_kod", sa.String(), nullable=True),
        sa.Column("jev_kod", sa.String(), nullable=True),
        sa.Column("agrees", sa.Boolean(), nullable=False),
        sa.Column("matcher_in_shortlist", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("probabilities", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("query_features", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("candidate_codes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["document_item.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id"),
    )
    op.create_index("ix_jev_shadow_result_document_id", "jev_shadow_result", ["document_id"])
    op.create_index("ix_jev_shadow_result_item_id", "jev_shadow_result", ["item_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_jev_shadow_result_item_id", table_name="jev_shadow_result")
    op.drop_index("ix_jev_shadow_result_document_id", table_name="jev_shadow_result")
    op.drop_table("jev_shadow_result")
