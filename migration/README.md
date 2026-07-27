# Multiplekser Elektryka — migracja do architektury Enterprise SaaS

Zobacz `docs/ETAP_0_analiza_architektury.md` (analiza + plan + diagramy Mermaid)
i `docs/RAPORT_ETAP_1.md` (co zrobione, co odłożone, jak uruchomić, plan Etapu 2).

Szybki start:
```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
uvicorn app.main:app --reload
```
