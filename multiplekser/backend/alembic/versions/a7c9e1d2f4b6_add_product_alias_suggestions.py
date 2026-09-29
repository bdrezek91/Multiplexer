"""add product alias suggestions

Revision ID: a7c9e1d2f4b6
Revises: f4a8b9c2d1e0
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c9e1d2f4b6"
down_revision = "f4a8b9c2d1e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_alias_suggestion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dzial", sa.String(), nullable=False),
        sa.Column("target_kod", sa.String(), nullable=False),
        sa.Column("alias_text", sa.String(), nullable=False),
        sa.Column("normalized_alias", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("source_document_id", sa.Uuid(), nullable=True),
        sa.Column("source_item_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dzial", "target_kod", "normalized_alias",
            name="uq_alias_suggestion_dzial_kod_alias",
        ),
    )
    op.create_index(
        "ix_product_alias_suggestion_dzial",
        "product_alias_suggestion", ["dzial"], unique=False,
    )
    op.create_index(
        "ix_product_alias_suggestion_target_kod",
        "product_alias_suggestion", ["target_kod"], unique=False,
    )
    op.create_index(
        "ix_product_alias_suggestion_normalized_alias",
        "product_alias_suggestion", ["normalized_alias"], unique=False,
    )
    op.create_index(
        "ix_product_alias_suggestion_status",
        "product_alias_suggestion", ["status"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_alias_suggestion_status", table_name="product_alias_suggestion")
    op.drop_index("ix_product_alias_suggestion_normalized_alias", table_name="product_alias_suggestion")
    op.drop_index("ix_product_alias_suggestion_target_kod", table_name="product_alias_suggestion")
    op.drop_index("ix_product_alias_suggestion_dzial", table_name="product_alias_suggestion")
    op.drop_table("product_alias_suggestion")
