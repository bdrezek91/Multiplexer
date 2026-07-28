# Raport — Etap 6: Moduł OCR (Strategy, synchronicznie) — Gemini

Zakres uzgodniony z użytkownikiem przed startem: **najpierw sama logika OCR, synchronicznie**
(Celery/Redis/MinIO/async — osobny, kolejny etap), **tylko Gemini** jako działający dostawca
(NVIDIA/OpenRouter zostają jako możliwe do dodania przez interfejs `OCRProvider`, nie portowane
teraz), testy na zamockowanym HTTP + opcjonalny test na prawdziwym kluczu.

## Zastrzeżenie bezpieczeństwa (zgłoszone przed startem prac)

W `index.html` (linie 1116-1119, stała `DEFAULT_KEYS`) są **wpisane na stałe dwa klucze API
Gemini** w postaci plaintext, w pliku będącym częścią historii tego repozytorium git. **Żaden z
tych kluczy nie został nigdzie skopiowany w nowym kodzie** — backend czyta klucze wyłącznie ze
zmiennych środowiskowych (`GEMINI_API_KEY_FREE`/`GEMINI_API_KEY_PAID`, patrz
`app/core/config.py`). Rekomendacja: **zrotować/unieważnić te klucze w Google AI Studio**,
niezależnie od dalszych prac nad migracją.

## Co zostało zrobione

Nowy moduł `app/modules/ocr/`:

1. **`prompt.py`** — `AI_OCR_PROMPT`, wyciągnięty **programowo** (regex na źródle `index.html`,
   nie ręcznie przepisany) — zero ryzyka błędu transkrypcji w tekście, który bezpośrednio steruje
   jakością odczytu AI.
2. **`parsing.py`** — `extract_json()` (port `extractJSON()`: zdejmowanie markdown-fence, próba
   parsowania całości, fallback do wycięcia fragmentu między pierwszym `{`/`[` a ostatnim
   `}`/`]`), `validate_item()` (port `validAIItem()`, w tym własny odpowiednik `parseFloat` JS —
   celowo tak samo "tolerancyjny" na śmieci po liczbie, np. `"5 szt"` → `5.0`, zamiast rzucać
   wyjątkiem jak Pythonowy `float()`).
3. **`form_rows.py`** — `FORM_ROWS` (153 pozycje, wyciągnięte programowo z `index.html`, jak
   prompt), `snap_to_form_row()` (port `snapToFormRow()`, reużywa `dice_coeff`/`bigrams`/
   `strip_diacritics` już istniejące w module Parser), `reconcile_form_row()` — port bug-fixów z
   `runAI()` (linie ~1426-1490 monolitu): auto-korekta literówek OCR (status `fixed`, ratio
   0.70-0.95) **nie może** po cichu skasować realnej różnicy (montaż podtynkowy/natynkowy, inne
   cyfry) — zweryfikowane testem (`Gniazdo ... natynkowe` nie zostaje cicho zamienione na wiersz
   formularza z "podtynkowe").
4. **`providers.py`** — `OCRProvider` (interfejs Strategy, zgodny z diagramem klas z
   `docs/ETAP_0_analiza_architektury.md`), `GeminiProvider` (port `geminiRecognize()`: PDF wysyłany
   natywnie jako `inline_data`, `temperature=0`, `thinkingLevel: low`, timeout, mapowanie błędów
   HTTP/timeout na `OCRProviderError`).
5. **`chain.py`** — `default_ocr_chain()` (5 kroków: 4 warianty modelu na kluczu darmowym + 1 na
   płatnym, **1:1 z `AI_CHAIN`** w monolicie), `run_ocr_chain()` (port pętli prób z `runAI()`: krok
   bez klucza pomijany bez liczenia się jako błąd, błąd kroku przełącza na kolejny, wyczerpanie
   łańcucha rzuca `AllProvidersFailedError` z tą samą treścią co JS: "brak klucza" vs "wszyscy
   zawiedli + ostatni błąd + pominięte").
6. **`image.py`** — `downscale_image()` (port `downscaleImage()`, Pillow zamiast Canvas
   przeglądarki — skaluje tylko w dół, JPEG, domyślnie 1800px/85%).
7. **`pipeline.py`** — `recognize_document()` spina łańcuch → `extract_json` → walidacja →
   `snap_to_form_row`+`reconcile_form_row` → `match_against_catalog` (reużywa Matcher z Etapów
   1-3, **bez** `dominant_country` — dokładnie jak w monolicie, gdzie `bestNameMatch()` podczas
   OCR jest wołane bez tego argumentu, bo dominujący kraj liczy się dopiero z całego dokumentu w
   `generateOutput()`, modułu Generator, wciąż nieprzeniesionego). Port bug-fixu: dla pozycji
   `off_form` (spoza formularza) wynik `quality='ok'` z `ratio < 0.70` jest degradowany do `'bad'`
   — samo podobieństwo tekstu poniżej progu to często przypadkowe nakładanie się słów, nie realne
   dopasowanie. `normalize_project_number()` — port `normalizeProjectNumber()`.
8. **`router.py`** — `POST /ocr/recognize` (multipart: `plik` + opcjonalny `magazyn`), wymaga
   zalogowania, **reużywa tę samą regułę RBAC co `/match`** (`check_magazyn_access` — wydzielone z
   `main.py` do `users/deps.py`, żeby nie duplikować logiki między `/match` a `/ocr/recognize`).
   Błędy dostawcy → 502, nie-JSON → 422, pusty plik → 400.
9. **35 nowych testów** (`test_ocr_parsing.py`, `test_ocr_form_rows.py`, `test_ocr_chain.py`,
   `test_ocr_provider_gemini.py`, `test_ocr_api.py`) — wszystkie na **zamockowanym HTTP** (bez
   sieci, bez kosztów, deterministyczne) + `test_ocr_gemini_live.py` (1 test, **pomijany domyślnie**,
   uruchamiany ręcznie z prawdziwym kluczem: `GEMINI_API_KEY_FREE=... pytest tests/test_ocr_gemini_live.py`).
   **Wszystkie testy: 90 zielonych + 1 pominięty** (53 z Etapów 1-5 + 37 nowych, w tym 1 opcjonalny
   pominięty bez klucza).

## Decyzje projektowe wymagające odnotowania

- **Tylko `GeminiProvider`** — `NvidiaRecognize`/`openrouterRecognize` z monolitu nigdy nie były
  wpięte do `AI_CHAIN` (były gotowym szkieletem "pod przyszłego dostawcę"), więc nie zostały
  przeniesione. Dodanie nowego dostawcy = nowa klasa implementująca `OCRProvider.recognize()`,
  zero zmian w `chain.py`/`pipeline.py`/routerze — zgodnie z wzorcem Strategy z Etapu 0.
- **Rendering PDF→obrazy (`pdfToImages`/pdf.js) NIE został przeniesiony** — Gemini akceptuje PDF
  natywnie (`inline_data` z `mime_type: application/pdf`), więc dla samego Geminiego nie jest
  potrzebny. Będzie potrzebny dopiero przy dodaniu dostawcy bez natywnej obsługi PDF (NVIDIA/
  OpenRouter w monolicie renderowały PDF do JPEG przez `pdf.js`) — do zrobienia wtedy, z biblioteką
  bez zależności systemowych (np. PyMuPDF), nie teraz.
- **`pickQty`/`qtySource` (wybór "która ilość pokazać") NIE zostały przeniesione** — to decyzja
  przy generowaniu wyniku (moduł Generator), nie przy odczycie. Endpoint zwraca obie kolumny
  (`ilosc_wydana`/`ilosc_zuzyta`) osobno, tak jak przeczytał je model — bez łączenia w jedną wartość.
- **Brak trwałości wyniku** (żadna tabela `Document`/`DocumentItem`) — ten etap jest bezstanowy:
  `POST /ocr/recognize` zwraca wynik od razu w odpowiedzi, nic nie zapisuje. ERD z Etapu 0 grupuje
  `DOCUMENT`/`DOCUMENT_ITEM` razem z przepływem OCR — naturalne miejsce na te tabele to kolejny
  etap (async: zadanie w tle *musi* mieć gdzie zapisać stan do odpytania), nie ten.
- **Typy `ilosc_wydana`/`ilosc_zuzyta` jako `str | None` w odpowiedzi API** (nie zawsze `float`) —
  to bezpośrednia kontynuacja zachowania z monolitu (tam też każda wartość trafiała do stringowego
  pola formularza) — celowo nie "ulepszone" bez potrzeby (zasada 8 z `CLAUDE.md`).
- **`check_magazyn_access` wydzielone z `main.py` do `app/modules/users/deps.py`** — mała
  refaktoryzacja (bez zmiany zachowania, zweryfikowana testami z Etapu 5, wciąż zielonymi), żeby
  `/ocr/recognize` mogło reużyć dokładnie tę samą regułę RBAC magazynu co `/match`, bez duplikacji.

## Co zostało świadomie odłożone (i dlaczego)

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| Celery + Redis (async), MinIO (storage plików), upload→zadanie w tle→polling statusu | Świadomie wydzielone z tego etapu (potwierdzone z użytkownikiem) | **Następny etap** |
| Tabele `Document`/`DocumentItem` (trwałość wyniku OCR) | Naturalnie pasuje do etapu async (potrzebne do odpytywania statusu zadania) | Następny etap |
| `NvidiaProvider`/`OpenRouterProvider` | Nigdy nie byly aktywnie uzywane w monolicie | Gdy pojawi się realna potrzeba dodania dostawcy |
| Renderowanie PDF→obrazy (pdf.js→PyMuPDF) | Niepotrzebne dla samego Gemini (natywna obsługa PDF) | Razem z dodaniem dostawcy bez natywnego PDF |
| `pickQty`/`qtySource`, `FORM_PHYSICAL_ORDER`/sortowanie wyniku | Moduł Generator (bez zmian względem wcześniejszych raportów) | Etap Generator |
| Eksport do formatu Optima | `generateOutput()` końcówka | moduł Integracje |

## Ryzyka

1. **Endpoint synchroniczny, do 90s na krok łańcucha** (`ocr_timeout_seconds`) — przy złym
   połączeniu z Gemini/wielu próbach fallbacku pojedyncze żądanie HTTP może trwać długo,
   blokując wątek/worker Uvicorn na czas żądania. Akceptowalne dla obecnej skali (mały zespół),
   ale to dokładnie ten przypadek, o którym mówi zasada 6 z `CLAUDE.md` ("operacje długotrwałe
   asynchronicznie przez Celery, nigdy blokująco w żądaniu HTTP") — do naprawienia w następnym
   etapie (async).
2. **`JWT_SECRET_KEY`/klucze Gemini nadal tylko w zmiennych środowiskowych lokalnego procesu** —
   bez zmian względem ryzyk z Etapu 5, ale warto przypomnieć: **`GEMINI_API_KEY_FREE`/`_PAID` też
   nigdy nie mogą trafić do repo** (patrz zastrzeżenie bezpieczeństwa wyżej).
3. **Brak testu na prawdziwym pliku PDF/zdjęciu z realnym charakterem pisma** — testy jednostkowe
   weryfikują logikę (parsowanie/dopasowanie/RBAC), nie jakość samego OCR. Rzeczywista jakość
   odczytu może być oceniona dopiero z prawdziwym kluczem Gemini i prawdziwym skanem (stąd
   `test_ocr_gemini_live.py` jako narzędzie do ręcznej weryfikacji, nie automatyczny dowód jakości).

## Jak uruchomić

```bash
cd backend
pip install -r requirements.txt   # dochodza Pillow i pytest-asyncio

alembic upgrade head
python -m scripts.import_catalog
python -m scripts.import_special_rules
python -m scripts.create_admin --email admin@przyklad.pl --password wybierz-mocne-haslo

export GEMINI_API_KEY_FREE=twoj_klucz_z_google_ai_studio   # WYMAGANE zeby /ocr/recognize dzialal
pytest tests/ -v          # 90 testow zielonych + 1 pominiety bez klucza

uvicorn app.main:app --reload
```

Przykład (po zalogowaniu, patrz `docs/RAPORT_ETAP_5.md`):
```bash
curl -X POST http://localhost:8000/ocr/recognize \
  -H "Authorization: Bearer <access_token>" \
  -F "plik=@skan.jpg" \
  -F "magazyn=Zabrze"
```

## Plan kolejnego etapu

1. Celery + Redis (worker już w `docker-compose.yml` od Etapu 1, nigdy nie skonfigurowany) —
   `POST /ocr/recognize` staje się `POST /documents` (202 Accepted + `task_id`), zadanie w tle,
   `GET /documents/{id}/status` do odpytywania.
2. MinIO — zapis oryginalnego pliku (dziś endpoint go od razu odrzuca po przetworzeniu).
3. Tabele `Document`/`DocumentItem` (ERD z Etapu 0) — trwałość wyniku, podstawa pod tabelę
   weryfikacji we froncie (Etap 7).
4. Dopiero potem: Frontend React (upload, tabela weryfikacji, generowanie).
