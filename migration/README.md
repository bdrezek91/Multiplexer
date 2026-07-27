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
pytest tests/ -v                        # wymaga tez bazy testowej, patrz TEST_DATABASE_URL w tests/conftest.py
uvicorn app.main:app --reload
```
