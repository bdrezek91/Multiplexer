"""Model SQLAlchemy dla reguł specjalnych Matchera (Etap 3) - patrz special_rules.py."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SpecialRuleModel(Base):
    __tablename__ = "special_rule"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_type: Mapped[str] = mapped_column(String, nullable=False)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    target_kod: Mapped[str | None] = mapped_column(String, nullable=True)
    kod_template: Mapped[str | None] = mapped_column(String, nullable=True)
    value_regex: Mapped[str | None] = mapped_column(String, nullable=True)
    rounding_steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    default_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalize: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
