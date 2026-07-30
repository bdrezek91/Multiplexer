"""Etap "quick winy": indeks na document.status

Kolumna filtrowana w praktyce zawsze przy pollingu statusu z frontendu (GET /documents,
GET /documents/{id} - odswiezane co 2s dopoki dokument jest w stanie queued/processing, patrz
DocumentsPage.tsx) i przy kazdym przejsciu run_ocr_task (mark_processing/mark_done/mark_error).
Bez indeksu Postgres skanuje cala tabele przy kazdym takim zapytaniu - niewidoczne przy garstce
dokumentow, ale rosnie liniowo z historia dokumentow firmy.

Revision ID: 8d6d6a7313c9
Revises: ad6f2b7b814a
Create Date: 2026-07-30 19:09:26.300656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d6d6a7313c9'
down_revision: Union[str, None] = 'ad6f2b7b814a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_document_status'), 'document', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_document_status'), table_name='document')
