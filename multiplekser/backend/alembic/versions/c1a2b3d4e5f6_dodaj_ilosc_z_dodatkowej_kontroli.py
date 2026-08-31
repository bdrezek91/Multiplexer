"""Dodaj flage ilosc_z_dodatkowej_kontroli do document_item.

Sygnal dla UI/operatora - ta konkretna ilosc pochodzi z drugiej, mniej pewnej probie odczytu
(verify_ambiguous_quantities), nie z glownego modelu OCR. Patrz walidacja architektury
2026-08-31, rekomendacja "widoczny sygnal niepewnosci w UI".

Revision ID: c1a2b3d4e5f6
Revises: b4e7d2a91c30
Create Date: 2026-08-31 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, None] = "b4e7d2a91c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_item",
        sa.Column(
            "ilosc_z_dodatkowej_kontroli",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("document_item", "ilosc_z_dodatkowej_kontroli")
