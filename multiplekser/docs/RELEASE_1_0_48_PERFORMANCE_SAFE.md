# Multiplekser 1.0.48 — bezpieczna optymalizacja 4 priorytetów

## Nie zmieniono (warunki jakości)

- Żadnych zmian promptów elektryki i hydrauliki ani dekodowania ręcznych cyfr.
- Żadnych zmian reguł JEV/TypeSafe, dopasowania produktów, magazynów, aliasów, 1P/3P, wykluczeń śrub 8 mm i zaślepki 127.
- Tylko Gemini FREE1 i FREE2 w produkcyjnym AUTO, bez Claude i bez automatycznego Gemini PAID.
- Hydraulika nadal wymaga konsensusu 2/2 dla nowych ilości oraz dodatkowej weryfikacji odręcznej jedynki; niepewne wartości pozostają do kontroli.
- Pełny PDF nadal przechodzi obecną korekcję prostowania i obecne 200 DPI. Nie wdrożono zmian pogarszających jakość obrazów.

## P1 — Gemini smart router

- Modelowe priorytety pełnego OCR niezmienione (3.6 Flash, 3.5 Flash-Lite, 3.1 Flash-Lite).
- Per-model / per-Google-project Redis cooldown 429/503/timeout zachowany.
- Nowa lekka telemetria przechowuje wyłącznie czas zwalidowanych OCR (EWMA, 24h TTL, bez prompta/klucza/treści).
- Dopiero **>=3** zwalidowane odpowiedzi z każdego projektu, przy różnicy >=1000 ms, pozwalają odwrócić kolejność FREE1/FREE2 w **tym samym modelu i dziale**. Bez danych historyczny porządek jest zachowany. Nie zmieniamy rodziny modelu na podstawie samej szybkości.

## P2 — weryfikacja ilości

- Do istniejącej listy modeli kontrolnych dodano FREE2 **po tym samym modelu FREE1**, z osobnymi cooldownami; paid i Claude nie są używane.
- Zachowana polityka „pierwsza poprawna odpowiedź zawierająca liczby”; sekwencyjny fallback wywołuje jedno współdzielone połączenie HTTP w obrębie łańcucha.
- Twardy limit 15 s całej kontroli dodatkowej. Po jego przekroczeniu oryginalne wyniki OCR pozostają bez zmian; wszystkie kwalifikujące się do kontroli wiersze dostają `needs_review` i informację o przekroczeniu limitu. To **może zmniejszyć automatyczną kompletność**, dlatego należy śledzić częstość timeoutów i porównać GOLD; nigdy nie uzupełniać brakujących ilości domysłem.

## P3 — PDF (wynik benchmarku)

Przed wdrożeniem porównano oryginalny render PyMuPDF z niezależnym równoległym renderowaniem po jednej stronie na wątek (wszystkie bajty PNG identyczne na 6 dokumentach, w tym po 2 i 4 strony):

| Strony | Oryginalny render | Równoległy |
|---|---:|---:|
| 2 | 0.615 s | 0.650 s |
| 2 | 0.965 s | 1.040 s |
| 4 | 1.800 s | 1.735 s |
| 4 | 1.755 s | 1.860 s |
| 2 | 0.375 s | 0.390 s |
| 2 | 0.370 s | 0.385 s |

Przy 4 vCPU równoległe renderowanie zwykle było wolniejsze. **Świadomie pozostawiono dotychczasowy kod PDF bez zmian**, zamiast wprowadzać nieudowodnione obniżenie DPI / ryzyko błędów OCR. Rekomendacja: dalsze profilowanie detekcji pustych stron i deskew w odizolowanych benchmarkach.

## P4 — infrastruktura i HTTP

- Jedna `httpx.AsyncClient` (pool, keepalive) na **jeden łańcuch fallbacku Gemini**; zawsze zamykana przy sukcesie, awarii lub anulowaniu timeoutem. Payload JSON, model, klucz w nagłówku i prompty bez zmian.
- Zamiast wielokrotnie tworzyć klienta przy każdej próbie dodatkowej kontroli, wszystkie modele sprawdzane są przez jeden `run_ocr_chain` z zachowaniem warunku pierwszej poprawnej częściowej odpowiedzi.
- Katalog `Catalog` użyty przez OCR jest przekazywany wyłącznie w pamięci tego samego zadania do JEV, zamiast ponownie odpytywać bazę. Przy braku katalogu zachowany jest oryginalny `Catalog.from_db`.
- Zapisy historii AI pozostawiono bez zmian — ważniejsza jest widoczność postępu i diagnostyka w UI niż potencjalne drobne oszczędności SQL.

## Testy i ograniczenia

- Izolowane testy (bez sieci), w tym parser, ilości, JEV, reguły magazynowe, dwóch darmowych kluczy i nowe testy EWMA/timeout — 98+ pozytywnych; dodatkowy test potwierdza jeden klient HTTP przy fallbacku (2 requests, identyczne JSON body i osobne klucze).
- Nie potwierdza to zgodności GOLD na wszystkich historycznych wydawkach. Po wdrożeniu: monitorować `timing_classification`, `timing_ocr_matcher`, `timing_ambiguous_verification`, `timing_jev_active`, `timing_to_done`, rate ręcznej weryfikacji i błędów.
- Cel <20 s pozostaje celem, **nie gwarancją**. 15-sekundowy limit weryfikacji dotyczy tylko dodatkowego etapu, nie całego przetwarzania.
- Rollback: poprzedni kod `b40d5f3` i obrazy Dockera `rollback-1047` zachować. Nie czyścić danych, bazy, minio ani historii dokumentów.
