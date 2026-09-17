"""Dodaj tabele ocr_row_group_flag (log drugiej kontroli AI dla grup podobnych wierszy).

Revision ID: b3e7f1a9c2d5
Revises: f7a2c9d4e6b1
Create Date: 2026-09-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3e7f1a9c2d5"
down_revision: Union[str, None] = "f7a2c9d4e6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ocr_row_group_flag",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("dzial", sa.String(), nullable=False),
        sa.Column("rozpoznana_nazwa", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("main_ilosc_wydana", sa.Float(), nullable=True),
        sa.Column("main_ilosc_zuzyta", sa.Float(), nullable=True),
        sa.Column("second_ilosc_wydana", sa.Float(), nullable=True),
        sa.Column("second_ilosc_zuzyta", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ocr_row_group_flag_document_id", "ocr_row_group_flag", ["document_id"],
    )
    op.create_index(
        "ix_ocr_row_group_flag_rozpoznana_nazwa", "ocr_row_group_flag", ["rozpoznana_nazwa"],
    )


def downgrade() -> None:
    op.drop_index("ix_ocr_row_group_flag_rozpoznana_nazwa", table_name="ocr_row_group_flag")
    op.drop_index("ix_ocr_row_group_flag_document_id", table_name="ocr_row_group_flag")
    op.drop_table("ocr_row_group_flag")
