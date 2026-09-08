"""Dodaj tabele document_report - zgloszenia problemow na dokumentach.

Revision ID: d2e8f4a1b7c3
Revises: c1a2b3d4e5f6
Create Date: 2026-09-08 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e8f4a1b7c3"
down_revision: Union[str, None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_report",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("document_id", sa.Uuid(as_uuid=True), sa.ForeignKey("document.id"), nullable=False),
        sa.Column("reported_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("opis", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_document_report_document_id", "document_report", ["document_id"])
    op.create_index("ix_document_report_status", "document_report", ["status"])


def downgrade() -> None:
    op.drop_index("ix_document_report_status", table_name="document_report")
    op.drop_index("ix_document_report_document_id", table_name="document_report")
    op.drop_table("document_report")
