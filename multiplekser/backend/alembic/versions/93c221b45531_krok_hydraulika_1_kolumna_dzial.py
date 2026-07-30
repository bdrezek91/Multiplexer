"""Krok Hydraulika-1: kolumna dzial na product + kod unikalny per-dzial

Separacja LOGICZNA dzialow (elektryka/hydraulika/...) w jednej tabeli `product`,
zamiast osobnych baz danych - patrz docs/MIGRATION_PLAN_HYDRAULIKA.md, sekcja 4.3.
`server_default` zapewnia, ze istniejace wiersze (wszystkie dzisiejsze produkty sa
Elektryka) dostaja poprawna wartosc bez recznego backfillu.

Kod produktu przestaje byc unikalny GLOBALNIE (byl: `ix_product_kod` UNIQUE) - dwa
niezaleznie budowane katalogi moga miec ten sam kod (np. oba maja "GRZEJNIK 1000W",
wykryte przy pierwszym imporcie baza_hydraulika.json obok baza_elektryka.json).
Unikalnosc przenosi sie na parę (kod, dzial).

Revision ID: 93c221b45531
Revises: 9de150ab780e
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '93c221b45531'
down_revision: Union[str, None] = '9de150ab780e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'product',
        sa.Column('dzial', sa.String(), nullable=False, server_default='elektryka'),
    )
    op.create_index(op.f('ix_product_dzial'), 'product', ['dzial'], unique=False)

    op.drop_index('ix_product_kod', table_name='product')
    op.create_index(op.f('ix_product_kod'), 'product', ['kod'], unique=False)
    op.create_unique_constraint('uq_product_kod_dzial', 'product', ['kod', 'dzial'])


def downgrade() -> None:
    op.drop_constraint('uq_product_kod_dzial', 'product', type_='unique')
    op.drop_index(op.f('ix_product_kod'), table_name='product')
    op.create_index('ix_product_kod', 'product', ['kod'], unique=True)

    op.drop_index(op.f('ix_product_dzial'), table_name='product')
    op.drop_column('product', 'dzial')
