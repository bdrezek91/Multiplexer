"""Krok Hydraulika-3: kolumny dzial/dzial_confidence na document

Wykryty automatycznie przez klasyfikacje OCR (patrz app/modules/ocr/classify.py) - nullable,
bo dokument moze zostac przerwany bledem PRZED etapem klasyfikacji (queued/processing/error
bez ustalonego dzialu). Bez server_default: istniejace dokumenty (wszystkie sprzed tego kroku,
zawsze Elektryka) po prostu zostaja z dzial=NULL - nie zgadujemy retroaktywnie.

Revision ID: d9f9992aa74a
Revises: 93c221b45531
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd9f9992aa74a'
down_revision: Union[str, None] = '93c221b45531'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('document', sa.Column('dzial', sa.String(), nullable=True))
    op.add_column('document', sa.Column('dzial_confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('document', 'dzial_confidence')
    op.drop_column('document', 'dzial')
