# Raport: nazewnictwo plikow `core.py` -> `core_elektryka.py` / `core_hydraulika.py`

## Kontekst i cel

Od Kroku Hydraulika-1 dzial Hydraulika ma swoje pliki jawnie oznaczone sufiksem
`_hydraulika` (`parser/hydraulika.py`, `matcher/core.py: match_against_catalog_hydraulika()`
w jednym pliku z Elektryka, `generator/core_hydraulika.py`, `ocr/pipeline_hydraulika.py`, ...).
Elektryka natomiast czesto siedziala w plikach o generycznej nazwie `core.py` — asymetria
nazewnicza, mimo ze architektonicznie oba dzialy sa rownorzedne ("osobna funkcja/dataclass per
dzial, wspolna tylko dolna warstwa" — patrz `CLAUDE.md`, sekcja "Decyzja architektoniczna").

Cel tej zmiany: **wylacznie przemianowanie/rozdzielenie plikow**, zero zmian logiki biznesowej.
Kazda przeniesiona funkcja ma identyczne cialo co przed zmiana.

## Co zrobiono

### 1) Proste przemianowania (pliki juz byly elektryka-only)

| Przed | Po |
|---|---|
| `generator/core.py` | `generator/core_elektryka.py` |
| `ocr/form_rows.py` | `ocr/form_rows_elektryka.py` |
| `ocr/pipeline.py` | `ocr/pipeline_elektryka.py` |

Zrobione przez `git mv`, zaktualizowane wszystkie importy (bezposrednie i przez fasady
`__init__.py` pakietow) w: `generator/__init__.py`, `generator/core_hydraulika.py`,
`ocr/__init__.py`, `ocr/pipeline_elektryka.py` (import wewnetrzny `form_rows` ->
`form_rows_elektryka`), `ocr/pipeline_hydraulika.py` (import `OCRUnparsableResponseError`/
`normalize_project_number` z `pipeline` -> `pipeline_elektryka` — ten import zostal pominiety
w pierwszym przebiegu, wychwycony dopiero przy uruchomieniu pelnej suity testow, patrz
sekcja "Bledy i poprawki"), `documents/tasks.py`, `tests/test_ocr_form_rows.py`.

### 2) Rozdzielenie `parser/core.py` (mieszal wspolna dolna warstwe z logika Elektryki)

`parser/core.py` zawieral zarowno rzeczy dzial-agnostyczne (`DIM_RE`, `strip_diacritics`,
`bigrams`, `dice_coeff` — uzywane tez przez `parser/hydraulika.py`), jak i logike specyficzna
dla Elektryki (`core_and_attrs`, `ParsedAttrs`, `detect_phase`, wzorce kraju/koloru/fazy/prądu).
Rozdzielone na:

- **`parser/shared.py`** (nowy) — `DIM_RE`, `strip_diacritics()`, `bigrams()`, `dice_coeff()`.
- **`parser/core_elektryka.py`** (nowy, dawniej `core.py`) — cala reszta: `core_and_attrs()`,
  `ParsedAttrs`, `detect_phase()`, wzorce (`COUNTRY_PATTERNS`, `COLOR_PATTERNS`, `MULT_PATTERNS`,
  `AMP_RE`, `WIRE_RE`, `SREDNICA_RE`, `BIEGUN_RE`, `MODULOW_KEYWORDS_RE`, `ATTR_WORD_RE`,
  `SYNONYMS`, wzorce fazy). Importuje `DIM_RE`/`strip_diacritics` z `.shared`.

`parser/__init__.py` (fasada pakietu) zaktualizowana, wiec zewnetrzny kod importujacy
`from app.modules.parser import core_and_attrs, dice_coeff` (itp.) **nie wymagal zmian**.
Bezposrednie importy submodulu zaktualizowane w: `parser/hydraulika.py`,
`generator/physical_order.py`, `products/catalog.py` (lazy import), `matcher/special_rules.py`,
`ocr/form_rows_elektryka.py`, `ocr/form_rows_hydraulika.py`, `tests/test_parser.py`.

### 3) Rozdzielenie `matcher/core.py` (mieszal logike OBU dzialow w jednym pliku)

`matcher/core.py` byl najbardziej zaskakujacym przypadkiem — mimo istnienia juz osobnych
`core_hydraulika.py`-stylu plikow w innych modulach, matcher trzymal `match_against_catalog()`
(Elektryka) i `match_against_catalog_hydraulika()` (Hydraulika) razem w jednym pliku, plus
wspolne funkcje pomocnicze. To jest najbardziej testowany kod w projekcie (11+ testow
regresyjnych w `test_matcher.py`, kazdy to realny blad z produkcji). Rozdzielone na:

- **`matcher/shared.py`** (nowy) — `magazyn_key()`, `apply_warehouse_variant()`,
  `resolve_by_kod()`, `alias_hits()` (przemianowana z prywatnego `_alias_hits` — jest teraz
  uzywana przez oba dzialy, wiec przestala byc prywatna dla jednego pliku).
- **`matcher/core_elektryka.py`** (nowy) — `COLOR_TO_JSON`, `COUNTRY_TO_JSON`,
  `_eff_color_json()`, `match_against_catalog()` — cialo funkcji bez zmian, jedyna zmiana to
  wywolania `_alias_hits` -> `alias_hits`.
- **`matcher/core_hydraulika.py`** (nowy) — `DEFAULT_SPECIAL_RULES_HYDRAULIKA`,
  `match_against_catalog_hydraulika()` — cialo bez zmian.

`matcher/__init__.py` zaktualizowana (fasada), wiec caly zewnetrzny kod uzywajacy
`from app.modules.matcher import match_against_catalog, match_against_catalog_hydraulika, ...`
**nie wymagal zmian**. Bezposrednie importy submodulu zaktualizowane w: `generator/detection.py`,
`generator/core_elektryka.py`.

## Co swiadomie NIE zostalo ruszone

- Zadna logika dopasowania/parsowania/generowania — kazda funkcja ma identyczne cialo.
- Kolejnosc rozstrzygania w matcherze (special_rules -> aliasy -> blokada grupy -> konflikty ->
  tie-break -> dominujacy kraj -> wariant magazynowy) — bez zmian.
- Struktura testow — pliki testowe zostaly tylko zaktualizowane o nowe sciezki importu, zadna
  logika testu ani asercja nie zostala zmieniona.

## Weryfikacja

- `grep -rln "matcher\.core\b|_alias_hits|from \.core import"` w `app/`, `tests/`, `scripts/`
  — pusty wynik, brak martwych odwolan do starych sciezek/nazw.
- Pelna suita testow backendu: **257 passed, 1 skipped** (bez zmian liczbowych wzgledem stanu
  przed ta zmiana — 256 + 1 nowy test FORM_ROWS z poprzedniego kroku = 257, zero regresji).

## Bledy i poprawki

Podczas pierwszego przebiegu pominietu zostal jeden bezposredni import: `ocr/pipeline_hydraulika.py`
importowal `OCRUnparsableResponseError`/`normalize_project_number` z `.pipeline` (stara nazwa).
Wychwycone dopiero przy uruchomieniu pelnej suity testow (7 bledow kolekcji —
`ModuleNotFoundError: No module named 'app.modules.ocr.pipeline'`), poniewaz zaden z
wczesniejszych targetowanych grepow/testow (`test_parser.py`, `test_parser_hydraulika.py`) nie
importowal `ocr/__init__.py` transitywnie. Naprawione zmiana importu na `.pipeline_elektryka`,
po czym pelna suita przeszla bez bledow.

## Nowa mapa plikow

| Modul | Elektryka | Hydraulika | Wspolne |
|---|---|---|---|
| Parser | `parser/core_elektryka.py` | `parser/hydraulika.py` | `parser/shared.py` |
| Matcher | `matcher/core_elektryka.py` | `matcher/core_hydraulika.py` | `matcher/shared.py`, `matcher/result.py`, `matcher/special_rules.py` |
| Generator | `generator/core_elektryka.py` | `generator/core_hydraulika.py` | `generator/detection.py`, `generator/physical_order.py`, `generator/output_format.py` |
| OCR | `ocr/pipeline_elektryka.py`, `ocr/form_rows_elektryka.py` | `ocr/pipeline_hydraulika.py`, `ocr/form_rows_hydraulika.py` | `ocr/classify.py`, `ocr/providers.py`, `ocr/prompt.py` |

Wszystkie pakiety maja stabilne fasady `__init__.py` — zewnetrzny kod (routery, taski Celery,
inne moduly) importuje z poziomu pakietu (`from app.modules.matcher import ...`), nie z
konkretnego pliku, wiec ta zmiana jest przezroczysta dla reszty kodu poza bezposrednimi
importerami submodulow wymienionymi wyzej.
