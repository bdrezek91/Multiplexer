"""dodaj trwaly licznik ukonczonych dokumentow do user

Revision ID: 6178221fd25c
Revises: b3e7f1a9c2d5
Create Date: 2026-09-28 17:01:29.874224

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6178221fd25c'
down_revision: Union[str, None] = 'b3e7f1a9c2d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("dokumenty_ukonczone_licznik", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill: ustaw licznik startowy na aktualna liczbe "done" dokumentow w bazie - to jedyne
    # dane jakie mamy (starsze, juz skasowane przez retention.py dokumenty sa nie do odzyskania),
    # ale od tego momentu licznik juz nigdy nie spadnie, bez wzgledu na to co pozniej skasuje
    # retencja (patrz komentarz w app/modules/users/models.py).
    op.execute(
        """
        UPDATE app_user
        SET dokumenty_ukonczone_licznik = sub.cnt
        FROM (
            SELECT user_id, COUNT(*) AS cnt
            FROM document
            WHERE status = 'done'
            GROUP BY user_id
        ) AS sub
        WHERE app_user.id = sub.user_id
        """
    )


def downgrade() -> None:
    op.drop_column("app_user", "dokumenty_ukonczone_licznik")
