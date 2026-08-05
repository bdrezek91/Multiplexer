"""Dodaj trwaly dziennik decyzji modeli AI do dokumentu.

Revision ID: b4e7d2a91c30
Revises: 9a1e4c6f2b3d
Create Date: 2026-08-05 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b4e7d2a91c30"
down_revision: Union[str, None] = "9a1e4c6f2b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column(
            "ai_trace",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("document", "ai_trace")
