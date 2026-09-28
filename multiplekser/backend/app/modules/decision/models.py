"""Trwaly log wynikow Jev Shadow do pozniejszej analizy skutecznosci."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class JevShadowResultModel(Base):
    __tablename__ = "jev_shadow_result"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_item.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    rozpoznana_nazwa: Mapped[str] = mapped_column(String, nullable=False)
    matcher_kod: Mapped[str | None] = mapped_column(String, nullable=True)
    jev_kod: Mapped[str | None] = mapped_column(String, nullable=True)
    agrees: Mapped[bool] = mapped_column(Boolean, nullable=False)
    matcher_in_shortlist: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    probabilities: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    query_features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    candidate_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
