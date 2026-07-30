"""Typy kolumn przenosne miedzy Postgresem a SQLite (Multiplekser Portable).

`Uuid` (z glownego pakietu sqlalchemy, nie sqlalchemy.dialects.postgresql) jest juz
cross-dialect od SQLAlchemy 2.0 - uzywac bezposrednio w modelach, ten modul nie jest do tego
potrzebny.

`PortableJSON` zachowuje JSONB (indeksowalny, wydajniejszy) na Postgresie - dokladnie jak dotad -
a na SQLite/innych bazach spada na zwykly JSON (SQLite ma wbudowane wsparcie JSON1 od dawna).
"""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

PortableJSON = JSON().with_variant(JSONB(), "postgresql")
