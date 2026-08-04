"""Zmien role uzytkownika 'elektryk' na 'magazynier' (na zyczenie uzytkownika - rola
'elektryk' zostaje calkowicie usunieta z aplikacji, zastapiona przez 'magazynier';
'admin' bez zmian). Migracja danych dla istniejacych wierszy app_user - kod (models.py,
repository.py, schemas.py) juz uzywa nowej nazwy roli, wiec bez tego istniejacy
uzytkownicy z rola='elektryk' zostaliby z wartoscia spoza dozwolonego zbioru ROLES.

Revision ID: 9a1e4c6f2b3d
Revises: 177e171d0f37
Create Date: 2026-08-04 04:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1e4c6f2b3d'
down_revision: Union[str, None] = '177e171d0f37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE app_user SET rola = 'magazynier' WHERE rola = 'elektryk'")


def downgrade() -> None:
    op.execute("UPDATE app_user SET rola = 'elektryk' WHERE rola = 'magazynier'")
