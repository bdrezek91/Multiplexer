"""Dodaj pracownik/numer_plomby do document (odczyt naglowka formularza przez OCR).

Revision ID: f7a2c9d4e6b1
Revises: e3f9a1c7b2d4
Create Date: 2026-09-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a2c9d4e6b1"
down_revision: Union[str, None] = "e3f9a1c7b2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document", sa.Column("pracownik", sa.String(), nullable=True))
    op.add_column("document", sa.Column("numer_plomby", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("document", "numer_plomby")
    op.drop_column("document", "pracownik")
