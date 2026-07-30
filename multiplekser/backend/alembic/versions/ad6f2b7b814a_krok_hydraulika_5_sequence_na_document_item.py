"""Krok Hydraulika-5: kolumna sequence na document_item

`id` (UUID losowy) nigdy nie byl uzytecznym kluczem sortowania pozycji dokumentu - dla
Elektryki bylo to niewidoczne, bo wynik i tak jest zawsze przesortowywany przez
`physical_order_for` przed wyswietleniem/generowaniem. Hydraulika nie ma takiego sortowania w
zrodle (kolejnosc wyniku = kolejnosc w dokumencie zrodlowym), wiec potrzebuje realnego zapisu
kolejnosci odczytu OCR. `server_default='0'`: istniejace wiersze (wszystkie sprzed tego kroku)
dostaja wartosc neutralna, bez proby retroaktywnego odtworzenia ich pierwotnej kolejnosci.

Revision ID: ad6f2b7b814a
Revises: d9f9992aa74a
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ad6f2b7b814a'
down_revision: Union[str, None] = 'd9f9992aa74a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'document_item',
        sa.Column('sequence', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('document_item', 'sequence')
