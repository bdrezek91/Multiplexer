"""
Modul Produkty - model domenowy katalogu (odpowiednik OPTIMA_DB/OPTIMA_PARSED w JS).

W Etapie 1 katalog trzymany jest w pamieci (z JSON) - w Etapie 2 zostanie zastapiony
zapytaniami SQLAlchemy do PostgreSQL (patrz docs/ETAP_0_analiza_architektury.md, ERD).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.modules.parser import core_and_attrs, bigrams


def plain_norm(s: str) -> str:
    from app.modules.parser.core import strip_diacritics
    import re
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", strip_diacritics((s or "").lower()))).strip()


def plain_tokens(s: str) -> list[str]:
    """NAPRAWA (bug wykryty 2026-07-27): liczby jednocyfrowe NIE sa odsiewane, tylko litery -
    inaczej "Koncowka tulejkowa 4-12" gubi "4" i alias fałszywie łapie wszystko z '.../12'."""
    return [w for w in plain_norm(s).split(" ") if len(w) >= 2 or w.isdigit()]


@dataclass
class Alias:
    text: str
    tokens: list[str] = field(default_factory=list)

    @classmethod
    def from_text(cls, text: str) -> "Alias":
        return cls(text=text, tokens=plain_tokens(text))


@dataclass
class Product:
    kod: str
    nazwa: str
    jm: str
    grupa: str
    atrybuty: dict
    kolor_domniemany: bool = False
    aliasy: list[Alias] = field(default_factory=list)
    warianty_magazynowe: Optional[dict] = None
    status: str = "generyczny"

    # Pola wyliczone przy budowie katalogu (odpowiednik cand.core/coreBigrams w JS)
    core: str = ""
    core_bigrams: list[str] = field(default_factory=list)
    phase: Optional[str] = None

    def __post_init__(self):
        if not self.core:
            parsed = core_and_attrs(self.nazwa)
            self.core = parsed.core
            self.core_bigrams = bigrams(parsed.core)
            self.phase = parsed.phase


class Catalog:
    """Katalog produktow generycznych (bez archiwalnych) + indeksy pomocnicze."""

    def __init__(self, products: list[Product]):
        self.products: list[Product] = [p for p in products if p.status == "generyczny"]
        self.by_kod: dict[str, Product] = {p.kod: p for p in self.products}
        self.first_word_group: dict[str, str] = self._build_first_word_group()

    def _build_first_word_group(self) -> dict[str, str]:
        tally: dict[str, dict[str, int]] = {}
        for p in self.products:
            w = p.core.split(" ")[0] if p.core else ""
            if not w:
                continue
            tally.setdefault(w, {})
            tally[w][p.grupa] = tally[w].get(p.grupa, 0) + 1
        out = {}
        for w, groups in tally.items():
            out[w] = max(groups.items(), key=lambda kv: kv[1])[0]
        return out

    def find_by_kod(self, kod: str) -> Optional[Product]:
        if not kod:
            return None
        hit = self.by_kod.get(kod)
        if hit:
            return hit
        kod_trim = kod.strip()
        for p in self.products:
            if p.kod.strip() == kod_trim:
                return p
        return None

    @classmethod
    def from_json_dict(cls, db: dict) -> "Catalog":
        products = []
        for section, status in (("generyczne", "generyczny"), ("archiwalne", "archiwalny")):
            for kod, rec in db.get(section, {}).items():
                products.append(Product(
                    kod=rec.get("kod", kod),
                    nazwa=rec["nazwa"],
                    jm=rec.get("jm", "SZT"),
                    grupa=rec.get("grupa", ""),
                    atrybuty=rec.get("atrybuty", {}) or {},
                    kolor_domniemany=bool(rec.get("kolor_domniemany", False)),
                    aliasy=[Alias.from_text(a) for a in (rec.get("aliasy") or [])],
                    warianty_magazynowe=rec.get("warianty_magazynowe"),
                    status=status,
                ))
        return cls(products)

    @classmethod
    def from_db(cls, session: Session) -> "Catalog":
        from .models import ProductModel

        rows = session.query(ProductModel).options(
            selectinload(ProductModel.aliasy),
            selectinload(ProductModel.warianty_magazynowe),
        ).all()
        products = [
            Product(
                kod=row.kod,
                nazwa=row.nazwa,
                jm=row.jm,
                grupa=row.grupa,
                atrybuty=row.atrybuty or {},
                kolor_domniemany=row.kolor_domniemany,
                aliasy=[Alias.from_text(a.alias_text) for a in row.aliasy],
                warianty_magazynowe={w.magazyn: w.kod_docelowy for w in row.warianty_magazynowe} or None,
                status=row.status,
            )
            for row in rows
        ]
        return cls(products)
