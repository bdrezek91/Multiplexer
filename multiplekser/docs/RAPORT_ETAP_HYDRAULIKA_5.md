# Raport — Krok Hydraulika-5: Generator dla Hydrauliki (odblokowanie `/generate`)

Ostatni brakujący kawałek pełnego przepływu Hydrauliki: upload → klasyfikacja (Krok 3) →
dopasowanie (Krok 1) → **generowanie do Optima**. W Kroku 2 sprawdzono, że Generator Elektryki
nie jest neutralny działowo, i zablokowano `/generate` dla Hydrauliki jawnym 409. Ten krok
zdejmuje tę blokadę - portując rzeczywisty `generateOutput()` z
`Multipekser_Hydraulika.html`, znaleziony przy bezpośrednim sprawdzeniu monolitu (był, mimo że
nie było to wcześniej pewne).

## Co znaleziono w źródle (sprawdzone, nie zakładane)

Hydraulika **ma** `generateOutput()`, ale jest istotnie prostszy niż wersja Elektryki -
komentarz nad funkcją w monolicie wprost to wyjaśnia:

> "KOLEJNOŚĆ WYNIKU = kolejność pozycji w dokumencie źródłowym (PDF/skan/Excel); duplikaty
> scalane w miejscu 1. wystąpienia. **Brak jakiegokolwiek "always-include"** - hydraulika nie
> ma pozycji dopisywanych domyślnie do każdej receptury."

Konkretne różnice względem Elektryki, wszystkie zweryfikowane bezpośrednio w kodzie źródłowym:

| Cecha | Elektryka | Hydraulika |
|---|---|---|
| Kolejność wyniku | Fizyczny układ formularza (`physical_order_for`) | Kolejność w dokumencie źródłowym (bez sortowania) |
| "Pierwsza wydawka" (always-include) | Tak (`ALWAYS_INCLUDE_BASE` + koryta/wkręty wg koloru) | **Nie istnieje** - funkcja nie przyjmuje takiego parametru |
| Dominujący kolor/kraj | Tak, liczony dla całego dokumentu | Nie dotyczy - matcher Hydrauliki i tak nie ma tego pojęcia |
| Konsolidacja specyficzna (koryta, szynoprzewody, wkręty OSB) | Tak | Nie istnieje |
| Traktowanie `quality=warn`/`bad` | Linia `### BRAK DOPASOWANIA`, z progiem podobieństwa (`_VERY_LOW_RATIO`) decydującym o treści podpowiedzi | Ta sama zasada (tylko `ok` trafia do wyniku), ale **bez** progu - podpowiedź to zawsze `kod` gdy istnieje, inaczej "brak" |
| Nazwa pliku, kodowanie CP1250 | `get_filename()`, `encode_cp1250()` | **Identyczne** - reużyte wprost, bez portowania |

## Co zostało zrobione

- **`generator/core_hydraulika.py`** (nowy): `generate_output_hydraulika()` - port 1:1,
  reużywa `format_qty`/`match_against_catalog_hydraulika`, dzieli dolną warstwę
  (`get_filename`/`encode_cp1250`) z Elektryką bez duplikacji (te funkcje są już
  dział-agnostyczne).
- **Naprawiony błąd znaleziony przy tej okazji**: kolejność pozycji w `Document.items`
  (relacja `order_by=DocumentItemModel.id`) sortowała po **losowym UUID**, nie po kolejności
  odczytu OCR. Dla Elektryki było to niewidoczne (wynik i tak zawsze przesortowany przez
  `physical_order_for`), ale Hydraulika **wymaga** zachowania kolejności źródłowej - bez
  naprawy generator dostawałby pozycje w przypadkowej kolejności. Dodano kolumnę
  `DocumentItemModel.sequence` (migracja `ad6f2b7b814a`), ustawianą wprost z indeksu listy w
  `repository.mark_done()`, i zmieniono `order_by` na nią. Zero wpływu na Elektrykę (i tak
  resortowana), ale realnie poprawia semantykę dla obu działów na przyszłość.
- **`documents/router.py`**: `/generate` dispatchuje wg `document.dzial` zamiast blokować -
  `generate_output_hydraulika()` dla Hydrauliki, bez zmian dla Elektryki.
  `_items_in_physical_order()` (funkcja budująca kolejność do wyświetlenia/generowania) jest
  teraz dział-świadoma: fizyczne sortowanie tylko dla Elektryki, dla Hydrauliki zwraca
  `document.items` wprost (już poprawnie posortowane przez `sequence`).
- **Frontend** (`DocumentDetailPage.tsx`): usunięty komunikat blokujący z Kroku 4 - przycisk
  "Generuj" działa teraz dla obu działów. Checkbox "Pierwsza wydawka" ukryty dla Hydrauliki
  (funkcja nie istnieje w tym dziale, pokazywanie jej byłoby mylące).

## Testy

- **`test_generator_hydraulika.py`** (nowy, 8 testów): dopasowana pozycja w wyniku, kolejność
  wejścia (nie fizyczna), scalanie duplikatów w miejscu pierwszego wystąpienia, komentarz przy
  braku dopasowania, **potwierdzenie że `first_wydawka` nie istnieje w sygnaturze funkcji**
  (test wprost na `inspect.signature`, nie tylko "nie testujemy tego"), tryb "wszystko po 1
  szt", ostrzeżenie o braku magazynu, pusta lista pozycji.
- **`test_documents_generate_api.py`**: zastąpiony test 409 testem na rzeczywiste
  wygenerowanie pliku (200, poprawna treść CP1250) + nowy test na zachowanie kolejności z
  dokumentu źródłowego przez pełny przepływ `run_ocr_task` → `/generate` (dwie pozycje w
  jednej kolejności OCR, weryfikacja że wynik jest w tej samej kolejności).
- **Pełna suita: 228 testów, 1 pominięty, zero regresji** (219 → 228).
- **Migracja zweryfikowana end-to-end** na realnym Postgresie (pełny łańcuch od zera + kolumna
  `sequence` widoczna w `document_item`).
- **W przeglądarce**: dokument Hydrauliki z dopasowaną pozycją - przycisk "Generuj" widoczny
  (bez checkboxa "Pierwsza wydawka"), kliknięcie pobiera plik z poprawną treścią
  (`ZAWÓR KĄTOWY 1/2X3/4;2;;SZT;`), zero błędów konsoli.

## Dodatek — pełna weryfikacja E2E przez prawdziwy stos (bez Dockera)

Na wyraźną prośbę: skoro w tym sandboksie nie da się uruchomić dockerd (`ulimit`/uprawnienia
zablokowane nawet przy próbie `service docker start`), złożono **równoważny prawdziwy stos
ręcznie**, zamiast poprzestać na wcześniejszych testach jednostkowych/integracyjnych:
PostgreSQL + Redis + serwer S3-kompatybilny (`moto.server`, HTTP, współdzielony między
procesami - dokładnie ta sama rola co MinIO) + osobny proces **backendu (uvicorn)** + osobny
proces **workera Celery** + `vite` dev server. Jedyny zamockowany element to samo wywołanie
sieciowe do Gemini (brak realnego klucza API w tym środowisku) - wszystko inne jest prawdziwe:
upload przez prawdziwy multipart HTTP, zapis do S3-kompatybilnego storage, kolejkowanie przez
Redis, odbiór zadania przez osobny proces workera, dwuetapowa klasyfikacja, dopasowanie,
zapis do Postgresa, polling statusu, generowanie i pobranie pliku - w przeglądarce (Playwright),
nie przez wywołania API bezpośrednio.

**Wynik**: dwa kolejne, niezależne uploady tego samego pliku - jeden zaklasyfikowany
automatycznie jako `hydraulika` (93% pewności), drugi jako `elektryka` (96%) - oba przeszły
cały potok bez błędu, obie pozycje Hydrauliki trafiły do wyniku w kolejności zgodnej z
odczytem OCR (potwierdza to, że naprawa `DocumentItemModel.sequence` z tego kroku faktycznie
działa międzyprocesowo, nie tylko w testach jednostkowych z jedną sesją DB), oba dokumenty
wygenerowały poprawne pliki CP1250 do pobrania, zero błędów w konsoli przeglądarki na żadnym
etapie. Zrzuty ekranu i logi z tej sesji nie są częścią repozytorium (efemeryczna weryfikacja
manualna, jak w `RAPORT_ETAP_9.md`/`RAPORT_ETAP_11.md`).

**Wciąż nieprzetestowane realnie** (niezależnie od Dockera): prawdziwe wywołanie Gemini z
prawdziwym kluczem API na prawdziwym skanie/zdjęciu - to jedyna granica tej weryfikacji,
niemożliwa do przekroczenia bez klucza.

## Co zostało świadomie odłożone

| Nieprzeniesione jeszcze | Uwaga | Plan |
|---|---|---|
| Reguły specjalne Hydrauliki w generowaniu | `MANUAL_OVERRIDES`/`WAREHOUSE_OVERRIDES` w monolicie Hydrauliki są celowo puste (V1) - matcher już to odzwierciedla (`DEFAULT_SPECIAL_RULES_HYDRAULIKA = []`), generator nic dodatkowego nie potrzebuje | Gdy pojawi się pierwszy realny wyjątek |
| `NEEDS_REVIEW`/quality `"review"` (kilka możliwych wariantów kodu) | Puste w źródle (`NEEDS_REVIEW = {}`), matcher Python nie implementuje tej ścieżki (tak jak monolit - nieużywana) | Gdy w bazie pojawią się kolizje bez jednoznacznego kodu |
| Weryfikacja E2E z realnym `docker compose up` i realnym kluczem Gemini | Brak Dockera w tym sandboxie; równoważny stos (Postgres+Redis+S3-kompatybilny serwer+osobne procesy backend/worker) zweryfikowany ręcznie w przeglądarce (patrz dodatek wyżej) - jedyna pozostała luka to realne wywołanie Gemini z prawdziwym kluczem | Przed wdrożeniem produkcyjnym |

## Ryzyka

1. Migracja `ad6f2b7b814a` dodaje kolumnę z `server_default='0'` - bezpieczna na istniejących
   danych, ale nie odtwarza retroaktywnie prawdziwej kolejności OCR dla dokumentów sprzed tego
   kroku (i tak nieistotne dla Elektryki, nieistotne dla Hydrauliki bo ten dział dopiero
   powstał w Kroku 3).
2. Ryzyka z poprzednich kroków (JWT_SECRET_KEY/klucze Gemini, tokeny w `localStorage`, brak CI
   z Postgresem, brak retry Celery, brak TLS) pozostają aktualne, bez zmian.

## Jak zweryfikować

```bash
cd backend
alembic upgrade head
pytest tests/test_generator_hydraulika.py tests/test_documents_generate_api.py -v
pytest tests/ -q   # 228 testow, 1 pominiety

cd ../frontend
npm run build && npm run test -- --run   # 25 testow
```

## Plan kolejnego kroku

Hydraulika jest teraz funkcjonalnie kompletna end-to-end (upload → klasyfikacja → dopasowanie
→ generowanie), na równi z Elektryką. Czekam na sygnał - możliwe kierunki: pełna weryfikacja
E2E przez `docker compose up`, kolejny dział (stolarka/konstrukcje/wentylacja, ten sam wzorzec
co Hydraulika), albo porządki/refaktor jeśli coś w tej migracji wymaga poprawki po dłuższym
użytkowaniu.
