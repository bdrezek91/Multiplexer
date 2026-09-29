"""Warstwa trwałej wiedzy DAMPOL uczonej z ręcznych korekt.

Propozycje są niezależne od bazowych aliasów importowanych z Optimy, więc ponowny import
katalogu ich nie kasuje. Matcher/Jev widzą wyłącznie propozycje zatwierdzone przez admina.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session, selectinload

from .catalog import plain_norm
from .models import ProductAliasSuggestionModel, ProductModel


class AliasSuggestionNotFoundError(Exception):
    pass


class AliasSuggestionConflictError(Exception):
    pass


def _base_alias_norms(product: ProductModel) -> set[str]:
    return {plain_norm(alias.alias_text) for alias in product.aliasy if plain_norm(alias.alias_text)}


def suggest_alias(
    session: Session,
    *,
    dzial: str,
    target_kod: str,
    alias_text: str,
    source_document_id=None,
    source_item_id=None,
    created_by_id=None,
) -> ProductAliasSuggestionModel | None:
    """Tworzy/odświeża propozycję aliasu po świadomej ręcznej zmianie kodu.

    Zwraca None, gdy propozycja nic nie wnosi: pusty tekst, nazwa produktu 1:1 albo alias
    już istnieje w bazowym katalogu. Funkcja celowo NIE wykonuje commit.
    """
    alias_text = (alias_text or "").strip()
    normalized = plain_norm(alias_text)
    if not normalized or not target_kod:
        return None

    product = (
        session.query(ProductModel)
        .options(selectinload(ProductModel.aliasy))
        .filter(ProductModel.dzial == dzial, ProductModel.kod == target_kod)
        .first()
    )
    if product is None:
        return None

    if normalized == plain_norm(product.nazwa) or normalized in _base_alias_norms(product):
        return None

    existing = (
        session.query(ProductAliasSuggestionModel)
        .filter(
            ProductAliasSuggestionModel.dzial == dzial,
            ProductAliasSuggestionModel.target_kod == target_kod,
            ProductAliasSuggestionModel.normalized_alias == normalized,
        )
        .first()
    )
    if existing is not None:
        # Powtórna świadoma korekta po wcześniejszym odrzuceniu może ponownie zgłosić alias.
        if existing.status == "rejected":
            existing.status = "pending"
            existing.resolved_at = None
            existing.resolved_by_id = None
        existing.alias_text = alias_text
        existing.source_document_id = source_document_id
        existing.source_item_id = source_item_id
        existing.created_by_id = created_by_id
        return existing

    row = ProductAliasSuggestionModel(
        dzial=dzial,
        target_kod=target_kod,
        alias_text=alias_text,
        normalized_alias=normalized,
        status="pending",
        source_document_id=source_document_id,
        source_item_id=source_item_id,
        created_by_id=created_by_id,
    )
    session.add(row)
    return row


def list_suggestions(
    session: Session,
    *,
    status: str = "pending",
    dzial: str | None = None,
    limit: int = 100,
) -> list[ProductAliasSuggestionModel]:
    query = session.query(ProductAliasSuggestionModel)
    if status:
        query = query.filter(ProductAliasSuggestionModel.status == status)
    if dzial:
        query = query.filter(ProductAliasSuggestionModel.dzial == dzial)
    return query.order_by(ProductAliasSuggestionModel.created_at.desc()).limit(limit).all()


def resolve_suggestion(
    session: Session,
    suggestion_id,
    *,
    approve: bool,
    resolved_by_id=None,
) -> ProductAliasSuggestionModel:
    try:
        uid = uuid.UUID(str(suggestion_id))
    except (TypeError, ValueError):
        raise AliasSuggestionNotFoundError(str(suggestion_id))

    row = session.query(ProductAliasSuggestionModel).filter(ProductAliasSuggestionModel.id == uid).first()
    if row is None:
        raise AliasSuggestionNotFoundError(str(suggestion_id))

    if approve:
        target = session.query(ProductModel).filter(
            ProductModel.dzial == row.dzial,
            ProductModel.kod == row.target_kod,
        ).first()
        if target is None:
            raise AliasSuggestionConflictError(
                f"Produkt docelowy {row.target_kod!r} nie istnieje już w katalogu."
            )

        # Jeden papierowy zwrot nie powinien wskazywać dwóch różnych produktów.
        conflicts = (
            session.query(ProductAliasSuggestionModel)
            .filter(
                ProductAliasSuggestionModel.dzial == row.dzial,
                ProductAliasSuggestionModel.normalized_alias == row.normalized_alias,
                ProductAliasSuggestionModel.status == "approved",
                ProductAliasSuggestionModel.target_kod != row.target_kod,
            )
            .all()
        )
        if conflicts:
            raise AliasSuggestionConflictError(
                f"Alias {row.alias_text!r} jest już zatwierdzony dla innego kodu."
            )
        row.status = "approved"
    else:
        row.status = "rejected"

    row.resolved_by_id = resolved_by_id
    row.resolved_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(row)
    return row


def approved_aliases_by_kod(session: Session, *, dzial: str) -> dict[str, list[str]]:
    rows = (
        session.query(ProductAliasSuggestionModel)
        .filter(
            ProductAliasSuggestionModel.dzial == dzial,
            ProductAliasSuggestionModel.status == "approved",
        )
        .all()
    )
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row.target_kod, []).append(row.alias_text)
    return out
