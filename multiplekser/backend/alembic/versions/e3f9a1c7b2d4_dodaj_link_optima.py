"""Dodaj optima_share_token_hash/optima_share_created_at do document (link Optima).

Revision ID: e3f9a1c7b2d4
Revises: d2e8f4a1b7c3
Create Date: 2026-09-17 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f9a1c7b2d4"
down_revision: Union[str, None] = "d2e8f4a1b7c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document", sa.Column("optima_share_token_hash", sa.String(), nullable=True))
    op.add_column("document", sa.Column("optima_share_created_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_document_optima_share_token_hash", "document", ["optima_share_token_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_optima_share_token_hash", table_name="document")
    op.drop_column("document", "optima_share_created_at")
    op.drop_column("document", "optima_share_token_hash")
