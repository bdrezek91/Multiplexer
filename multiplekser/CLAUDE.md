# CLAUDE.md — instrukcje projektowe dla Claude Code

## Kontekst

To repozytorium to migracja **Multipleksera Elektryka** — istniejącej aplikacji HTML/JavaScript
(monolit w jednym pliku, silnik OCR + parser + matcher produktów Optima + generator receptur)
do architektury webowej klasy Enterprise, dla wielu użytkowników, z docelową rozbudową o kolejne
działy (hydraulika, stolarka, konstrukcje, wentylacja).

**Oryginalny plik monolitu** (`Multiplekser_Elektryka.html`) reprezentuje **działającą, wielokrotnie
przetestowaną logikę biznesową** wypracowaną iteracyjnie na realnych błędach (patrz
`docs/ETAP_0_analiza_architektury.md`, sekcja 2 — lista reguł, które MUSZĄ zostać zachowane 1:1).
Jeśli plik monolitu jest w tym repo (lub go dostarczę) — traktuj go jako źródło prawdy dla
logiki biznesowej, nie zgaduj jej na nowo.

## Rola Claude Code w tym projekcie

Jesteś Senior Software Architect / Tech Lead / Principal Full Stack Developer prowadzącym tę
migrację **razem ze mną, krok po kroku**. Nie realizuj całego planu naraz — po każdym etapie
**zatrzymaj się i poczekaj na moje potwierdzenie**, zanim przejdziesz do kolejnego.

## Docelowy stack technologiczny

- **Frontend**: React + TypeScript + Vite + TanStack Query + React Router + Material UI
- **Backend**: Python FastAPI + SQLAlchemy + Alembic
- **Baza danych**: PostgreSQL
- **Cache i kolejki**: Redis + Celery
- **Przechowywanie plików**: MinIO (z możliwością zamiany na Azure Blob / AWS S3)
- **Konteneryzacja**: Docker + Docker Compose
- **Reverse Proxy**: Nginx
- **Uwierzytelnianie**: JWT z odświeżaniem tokenów + Role-Based Access Control

## Twarde zasady migracji

1. **Nie przepisuj logiki biznesowej od zera.** Najpierw przeanalizuj istniejący kod (monolit
   i/lub kod już przeniesiony w `backend/app/modules/`), zidentyfikuj moduły, algorytmy,
   zależności i przepływy danych, zanim zaczniesz cokolwiek zmieniać.
2. Zachowaj całą logikę OCR, parsera, matchera, reguł biznesowych i eksportu do Comarch Optima —
   nie zmieniaj działania algorytmów bez wyraźnej potrzeby i bez opisania wpływu zmiany.
3. Kod podzielony na niezależne moduły: **OCR, Parser, Matcher, Generator, Integracje, Produkty,
   Użytkownicy** (struktura już założona w `backend/app/modules/`).
4. Baza danych w pełnej normalizacji, z migracjami Alembic — nie ręcznymi `CREATE TABLE`.
5. Adaptery AI wg wzorca **Strategy** (Gemini, OpenAI, Claude, OpenRouter, Azure, lokalny OCR) —
   dodanie nowego dostawcy = nowa klasa implementująca wspólny interfejs, zero zmian gdzie indziej.
6. Operacje długotrwałe (OCR, AI, eksport) — asynchronicznie przez Celery, nigdy blokująco w
   żądaniu HTTP.
7. **Każdy etap w małych, działających krokach.** Po zakończeniu etapu: projekt musi się
   kompilować, uruchamiać (`docker compose up` lub lokalnie) i przechodzić testy (`pytest`,
   docelowo też testy frontendu).
8. Nie usuwaj istniejących funkcji bez uzasadnienia. Każda proponowana zmiana = krótki opis
   wpływu na działanie systemu, zanim ją wdrożysz.
9. Kod zgodny z SOLID / Clean Architecture / DDD tam, gdzie to daje realną korzyść — nie na siłę.
10. Diagramy Mermaid dla nowych modułów/przepływów danych, dopisywane do `docs/`.
11. **Po każdym etapie: raport** (`docs/RAPORT_ETAP_N.md`) — co zrobione, co świadomie odłożone
    (i dlaczego), jakie ryzyka, plan kolejnego kroku. Wzór formatu: `docs/RAPORT_ETAP_1.md`.

## Stan obecny repozytorium

- `docs/ETAP_0_analiza_architektury.md` — pełna analiza monolitu, mapa modułów, diagramy Mermaid
  (architektura, przepływ danych, wzorzec Strategy dla OCR, ERD), plan 8 etapów.
- `docs/RAPORT_ETAP_1.md` — co zrobione w Etapie 1, co odłożone, jak uruchomić, plan Etapu 2.
- `backend/app/modules/parser/core.py` — **gotowy, przetestowany** port `coreAndAttrs()`.
- `backend/app/modules/matcher/core.py` — **gotowy, przetestowany** port `matchAgainstCatalog()`
  (blokada grupy, aliasy ze specyficznością, konflikty atrybutów, tie-break, dominujący kraj).
- `backend/app/modules/products/catalog.py` — model domenowy `Product`/`Alias`/`Catalog`
  (na razie wczytywany z JSON — **do podmiany na SQLAlchemy w Etapie 2**).
- `backend/tests/test_matcher.py` — **11 testów regresyjnych, każdy to realny błąd z produkcji**
  (nie testy syntetyczne) — muszą zawsze przechodzić po każdej zmianie w Matcherze/Parserze.
- `backend/tests/fixtures/baza_elektryka.json` — realny katalog produktowy (379 pozycji) do
  testów i do importu w Etapie 2.
- `docker-compose.yml` + `backend/Dockerfile` + `backend/app/main.py` — minimalne FastAPI z
  endpointem `/match`, zweryfikowane end-to-end.
- **Świadomie jeszcze nieprzeniesione** (patrz `docs/RAPORT_ETAP_1.md`, tabela): reguły
  specyficzne dla konkretnych kodów (R3/R6/wkręt), sortowanie wyniku wg fizycznej kolejności
  formularza, cały moduł OCR, eksport do Optimy, użytkownicy/role.

## Plan etapów (z Etapu 0 — realizuj po kolei, jeden na raz)

| Etap | Zakres |
|---|---|
| 0 ✅ | Analiza, architektura, diagramy |
| 1 ✅ | Szkielet repo, moduł Matcher+Parser w Pythonie z testami, docker-compose |
| **2 ← następny** | Model danych (SQLAlchemy+Alembic), import `baza_elektryka.json` do Postgresa, podmiana `Catalog.from_json_dict()` na wersję z bazy |
| 3 | FastAPI: pełny CRUD produktów + endpoint dopasowania jako serwis, testy integracyjne |
| 4 | OCR jako Strategy + Celery (async), MinIO na pliki |
| 5 | Auth (JWT+RBAC), model użytkowników/magazynów |
| 6 | Frontend React (upload, tabela weryfikacji, generowanie) |
| 7 | Nginx, docker-compose produkcyjny, dokumentacja wdrożeniowa |
| 8+ | Kolejne działy (hydraulika, stolarka...) jako dodatkowe `grupa`/katalogi |

## Stan obecny repozytorium (zaktualizowane po Kroku Hydraulika-1)

Repo jest już **dwudziałowe**, nie "Elektryka + plan na przyszłość":

- **Elektryka**: pełny stos, Etapy 0-11 + poprawki (parser/matcher/OCR/dokumenty/generator/
  auth/frontend/docker prod) — bez zmian w tym kroku.
- **Hydraulika**: fundament danych gotowy — `parser/hydraulika.py` (`core_and_attrs_hydraulika`),
  `matcher/core.py: match_against_catalog_hydraulika()`, kolumna `dzial` na `product`
  (separacja logiczna, `kod` unikalny per-dzial), katalog `baza_hydraulika.json` (247+7 pozycji)
  zaimportowany. Routery `/products` i `/match` przyjmują `dzial` (domyślnie `"elektryka"`,
  422 dla nieznanej wartości) — patrz `docs/RAPORT_ETAP_HYDRAULIKA_2.md`. **OCR w pełni
  wpięty od Kroku 3** (`docs/RAPORT_ETAP_HYDRAULIKA_3.md`): `POST /documents` sam wykrywa dział
  dokumentu (`ocr/classify.py`, dwuetapowe wywołanie Gemini — klasyfikacja, potem pełny odczyt
  promptem/snap/matcherem właściwego działu) — **celowo bez ręcznego przełącznika w UI**,
  użytkownik tego nie chciał. Wynik (`dzial`, `dzial_confidence`) zapisany na `Document`.
  **Generator sprawdzony i NIE jest neutralny działowo** (na stałe importuje reguły
  specyficzne dla Elektryki — koryta kablowe, szynoprzewody, wkręty OSB) —
  `POST /documents/{id}/generate` zwraca 409 dla dokumentów Hydrauliki, dopóki nie powstanie
  własna analiza biznesowa generowania. **Jeszcze nie podłączone**: frontend (nie pokazuje
  wykrytego działu ani komunikatu o zablokowanym generowaniu). Plan pełny:
  `docs/MIGRATION_PLAN_HYDRAULIKA.md`.

**Decyzja architektoniczna (nie kwestionować bez nowego powodu)**: Matcher NIE używa
generycznego silnika `AttributeRule` mimo że taki był zaproponowany w
`docs/MIGRATION_PLAN_HYDRAULIKA.md` (sekcja 4.1, z innej, wcześniejszej sesji). Użytkownik
wybrał jawnie (Krok Hydraulika-1): zachować `special_rules.py` jako mechanizm dla Elektryki,
a Hydraulikę dodać jako **osobną funkcję** (`match_against_catalog_hydraulika`), tym samym
stylem co już istniejący, sprawdzony kod — nie jako współdzielony silnik konfiguracji. Ten sam
wzorzec ("osobna funkcja/dataclass per dział, wspólna tylko dolna warstwa") obowiązuje też w
Parserze (`parser/core.py` vs `parser/hydraulika.py`) i ma się powtórzyć dla 3. działu, jeśli
się pojawi — kopiowanie funkcji, nie rozbudowa wspólnego silnika.

## Jak pracować ze mną w tym repo

1. Na początku każdej sesji przeczytaj `docs/RAPORT_ETAP_N.md`/`docs/RAPORT_ETAP_HYDRAULIKA_*.md`
   o najwyższym numerze — to Twój punkt startowy, mówi dokładnie co już działa i co jest
   następne. Jeśli pracujesz nad Hydrauliką, przeczytaj też `docs/MIGRATION_PLAN_HYDRAULIKA.md`.
2. Przed rozpoczęciem etapu: krótko streść mi co planujesz zrobić i zapytaj o potwierdzenie,
   jeśli zmiana dotyka logiki biznesowej, modelu danych lub czegoś nieodwracalnego.
3. Podczas etapu: rób małe, weryfikowalne kroki (commit po każdym sensownym kawałku).
4. Na końcu etapu: uruchom pełny zestaw testów, upewnij się że `docker compose up` działa,
   napisz `docs/RAPORT_ETAP_N.md`, zatrzymaj się i poczekaj na mój sygnał do kolejnego etapu.
5. Jeśli natrafisz na niejednoznaczność w logice biznesowej (np. czy dana reguła powinna się
   zmienić przy migracji) — zapytaj mnie, nie zgaduj. Ta logika była wypracowywana miesiącami
   na realnych błędach produkcyjnych, więc "wygląda dziwnie" zwykle znaczy "rozwiązuje konkretny
   przypadek", nie "błąd do poprawienia".
