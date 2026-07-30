# Raport — niezawodność OCR: retry na przejściowe błędy + druga próba dla niejednoznacznej ilości

Dwa punkty z listy usprawnień omówionej z użytkownikiem (analiza architektury/szybkości OCR) -
oba dotyczące `run_ocr_task`, wdrożone razem.

## 1. Automatyczny retry na przejściowe błędy sieci/dostępności

Dotąd: jeśli WSZYSCY dostawcy w łańcuchu (`AllProvidersFailedError`) albo pojedyncze wywołanie
(`OCRProviderError` - timeout/5xx/brak sieci) zawiodło, dokument od razu dostawał status
`"error"` - użytkownik musiał ręcznie wgrać go ponownie, nawet jeśli przyczyna była czysto
przejściowa (chwilowy zanik łączności, chwilowy limit RPM).

Teraz: `_classify_and_recognize()` (nowa funkcja, wydzielona z `run_ocr_task`) ponawia
klasyfikację+odczyt do 3 razy (1 pierwsza próba + 2 ponowienia), z rosnącym opóźnieniem
(5s, 15s) - **wyłącznie** dla `(AllProvidersFailedError, OCRProviderError)`, czyli klasy
"żaden dostawca nie odpowiedział poprawnie". Świadomie **nie** obejmuje
`OCRUnparsableResponseError` (model odpowiedział, ale treść była bezużyteczna) - to problem
jakości danych/prompta, nie dostępności, więc ponawianie na ślepo mogłoby tylko zamaskować
realny błąd zamiast go naprawić. Klasyfikacja i pełny odczyt są ponawiane razem (nie osobno) -
w praktyce oba zawodzą z tego samego powodu (brak sieci/limit), więc nie ma sensu ich
rozdzielać.

Funkcja jest częścią `run_ocr_task` (wspólnej, czystej logiki używanej zarówno przez wrapper
Celery jak i wątek w trybie Portable, patrz `docs/RAPORT_PORTABLE_1.md`) - retry działa
identycznie w obu trybach dystrybucji zadania, bez duplikacji logiki.

## 2. Druga, wąska próba dla pozycji z pustą ilością w obu kolumnach

Kontekst: poprawka promptu z poprzedniego kroku (rozróżnienie cyfry "1" od ptaszka
potwierdzenia) zmniejsza problem, ale nie eliminuje go w 100% - to wciąż probabilistyczny
model czytający odręczne pismo.

Nowy moduł `ocr/verify.py`: dla pozycji, które po głównym przebiegu mają **pustą ilość w OBU
kolumnach** (`ilosc_wydana` i `ilosc_zuzyta` = null), a mimo to trafiły do wyniku (sam prompt
już pomija wiersze całkowicie puste - patrz `ZNACZNIKI`/`INTEGRALNOŚĆ WIERSZA` w
`ocr/prompt.py`) - druga, wąska, ukierunkowana próba: osobne zapytanie do AI o **jeden
konkretny wiersz** (po nazwie materiału jako punkcie odniesienia), z tym samym rozróżnieniem
ptaszek-vs-cyfra co w głównym prompcie.

**Ograniczenie, o którym trzeba wiedzieć**: działa na **całym obrazie**, nie na wyciętym
fragmencie komórki - Gemini nie zwraca współrzędnych/bounding-boxów w obecnym schemacie JSON
głównego przebiegu, więc fizyczny crop nie jest możliwy bez zmiany prompta/schematu głównego
przebiegu (świadomie odłożone - użytkownik poprosił "nie ruszaj" dokładnie tej części). Model
i tak radzi sobie z namierzeniem właściwego wiersza po nazwie materiału.

Zabezpieczenia:
- **Best-effort** - każdy błąd pojedynczej próby (sieć, zły JSON, brak klucza) kończy się cicho
  `(None, None)`, nigdy nie przerywa przetwarzania całego dokumentu.
- **Limit `_MAX_VERIFY_ITEMS = 8`** na dokument - pojedynczy, mocno uszkodzony skan (dużo
  pustych wierszy) nie wygeneruje lawiny dodatkowych zapytań do AI.
- **Równolegle** (`asyncio.gather`) dla wszystkich kwalifikujących się pozycji naraz - kilka
  dodatkowych zapytań nie sumuje się czasowo.

## Testy

4 nowe testy w `tests/test_documents_task.py`:
- retry: pierwsza próba pada całkowicie (4 kroki łańcucha z kluczem darmowym zwracają błąd),
  druga się udaje - dokument kończy na `"done"`, sprawdzone też że `time.sleep` wywołane raz z
  opóźnieniem 5s (zamockowane - testy nie czekają realnie).
- retry: wszystkie 3 próby zawodzą tym samym błędem - dokument kończy na `"error"` (bez zmiany
  względem poprzedniego zachowania), `time.sleep` wywołane 2 razy (5s, 15s).
- druga próba: uzupełnia pominiętą ilość, gdy weryfikacja zwróci wartość.
- druga próba: zostawia ilość pustą, gdy weryfikacja też nic nie znajdzie (sam ptaszek).

**Pełna suita: 252 → 256 testów, zero regresji.** Zweryfikowano też ręcznie (przegląd kodu +
grep), że żaden istniejący test nie łamie się przez dodatkowe wywołania `GeminiProvider.recognize`
wprowadzone przez drugą próbę - istniejące testy albo mają pozycje z niepustą ilością (nie
kwalifikują się do drugiej próby), albo używają `AsyncMock(return_value=...)` (obsługuje
dowolną liczbę dodatkowych wywołań bez błędu).

## Co zostało świadomie odłożone

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| Retry na poziomie Celery (`task.retry()`) zamiast blokującego `time.sleep` w współdzielonej funkcji | Prostsze, identyczne zachowanie w obu trybach (Celery/Portable) kosztem zajmowania slotu workera Celery przez czas oczekiwania | Jeśli skala uploadów kiedyś to uzasadni |
| Bounding-boxy z głównego przebiegu (prawdziwy crop komórki zamiast całego obrazu w drugiej próbie) | Wymagałoby zmiany prompta/schematu głównego przebiegu - świadomie odłożone na wyraźną prośbę ("nie ruszaj") | Osobna decyzja, jeśli druga próba na całym obrazie okaże się niewystarczająca |

## Jak zweryfikować

```bash
cd backend
pytest tests/test_documents_task.py -v
pytest tests/ -q   # 256 testow, 1 pominiety
```
