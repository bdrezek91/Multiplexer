# Multiplekser Elektryka — migracja do architektury Enterprise SaaS

Zobacz `docs/ETAP_0_analiza_architektury.md` (analiza + plan + diagramy Mermaid)
i `docs/RAPORT_ETAP_1.md` (co zrobione, co odłożone, jak uruchomić, plan Etapu 2).

Szybki start:
```bash
cd backend
pip install -r requirements.txt
alembic upgrade head              # utworz tabele w Postgresie (DATABASE_URL w .env lub domyslny localhost)
python -m scripts.import_catalog  # zaimportuj katalog z tests/fixtures/baza_elektryka.json
pytest tests/ -v                  # wymaga tez bazy testowej, patrz TEST_DATABASE_URL w tests/conftest.py
uvicorn app.main:app --reload
```
