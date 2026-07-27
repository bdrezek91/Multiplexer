# Multiplekser Elektryka — migracja do architektury Enterprise SaaS

Zobacz `docs/ETAP_0_analiza_architektury.md` (analiza + plan + diagramy Mermaid) i najnowszy
`docs/RAPORT_ETAP_N.md` (co zrobione, co odłożone, jak uruchomić, plan kolejnego etapu).

Szybki start:
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head                    # utworz tabele w Postgresie (DATABASE_URL w .env lub domyslny localhost)
python -m scripts.import_catalog        # zaimportuj katalog z tests/fixtures/baza_elektryka.json
python -m scripts.import_special_rules  # zaimportuj reguly specjalne (R3/R6/OCR overrides/wykluczenia)
python -m scripts.create_admin --email admin@przyklad.pl --password wybierz-mocne-haslo
pytest tests/ -v                        # wymaga tez bazy testowej, patrz TEST_DATABASE_URL w tests/conftest.py
uvicorn app.main:app --reload
```

API: `/auth/token` (logowanie, od Etapu 5), `/match` (dopasowanie, wymaga zalogowania), pelny CRUD
`/products` (od Etapu 4, zapis tylko rola admin), dokumentacja interaktywna z przyciskiem
"Authorize" na `/docs`.

**Produkcja**: ustaw zmienna srodowiskowa `JWT_SECRET_KEY` na losowy, dlugi sekret - wartosc
domyslna w kodzie jest tylko do dewelopmentu lokalnego (patrz `docs/RAPORT_ETAP_5.md`, ryzyka).
