"""Tworzy uzytkownika (bootstrapping pierwszego konta - Etap 5).

Uzycie:
    python -m scripts.create_admin --email admin@example.com --password tajne-haslo
    python -m scripts.create_admin --email magazynier@example.com --password ... --rola magazynier --magazyn Zabrze --magazyn Czekanów
"""
from __future__ import annotations

import argparse

from app.core.db import SessionLocal
from app.modules.users.repository import DuplicateEmailError, create_user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--rola", default="admin", choices=["admin", "magazynier"])
    parser.add_argument(
        "--magazyn", action="append", default=[],
        help="Powtarzalny - metadane profilu; obecnie nie ograniczaja dostepu zadnej roli",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        user = create_user(
            session, email=args.email, password=args.password,
            rola=args.rola, magazyny_dostepne=args.magazyn,
        )
        print(f"Utworzono uzytkownika {user.email} (rola={user.rola}, id={user.id})")
    except DuplicateEmailError:
        print(f"Uzytkownik {args.email} juz istnieje - nic nie zrobiono.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
