# Raport — wyłączenie pikselowego detektora zaznaczeń dla Hydrauliki

## Zgłoszenie

Na dwóch różnych wydawkach Hydraulika "Dodatkowa kontrola ilości" obejmowała kilkanaście-kilkadziesiąt
pozycji naraz, wielokrotnie kończąc się "Bez wyniku", mimo że duża część tych pozycji na papierze
jest po prostu pusta.

## Diagnoza (trzy kolejne, coraz głębsze poprawki tej samej sesji)

1. **Pierwsza próba**: zawężenie marginesu przy liniach wiersza + podniesienie progu liczby
   pikseli w `discover_hydraulika_quantity_marks()` (`verification_image.py`) — pomogło na
   pierwszym zgłoszonym dokumencie (przeciek atramentu do bezpośrednio sąsiadującego wiersza),
   ale nie rozwiązało problemu ogólnie.
2. **Druga próba**: `_verify_ambiguous_items()` (`documents/tasks.py`) przestał bezkrytycznie
   ufać samej deklaracji `ma_oznaczenie=true` głównego modelu OCR — zaczął wymagać potwierdzenia
   przez detektor pikselowy. Na kolejnym zgłoszonym dokumencie okazało się to nieskuteczne:
   detektor "potwierdzał" niemal każdy pusty wiersz (45 z 45 na jednej stronie), a jednocześnie
   **przegapiał realne zaznaczenia** — ryzyko cichej utraty prawdziwej ilości.
3. **Diagnoza źródłowa** (na żywym kodzie, na przesłanym przez użytkownika PDF-ie): wypróbowano
   hipotezę "złe granice kolumn przez skos zdjęcia telefonem" — potwierdzona częściowo (prawdziwe
   linie kolumn były przesunięte o 64–105px względem sztywnych procentów szerokości strony), ale
   **poprawienie granic kolumn nic nie zmieniło w wynikach**. Prawdziwa przyczyna: na tej
   konkretnej kartce fizycznie **nie istnieje wiersz "Blat kuchenny 1650x600"**, który
   `_HYDRAULIKA_PAGES` (stały, zakodowany na sztywno układ wierszy) zakłada jako obecny — dodany
   wcześniej specjalnie dla INNEGO dokumentu (`RAPORT_OCR_NIEZAWODNOSC_3.md`). W obiegu są więc
   **co najmniej dwie różne wersje papierowej wydawki Hydraulika**. Na kartce bez tego wiersza
   cała reszta strony wychodzi przesunięta o jeden wiersz względem tego, czego kod oczekuje — stąd
   pozornie losowy wzorzec: fałszywe zaznaczenie nad prawdziwym, przegapione zaznaczenie w
   prawdziwym miejscu, fałszywe zaznaczenie pod.

## Decyzja

Twardo zakodowany, jeden fizyczny układ wierszy nie może poprawnie obsłużyć wielu wersji tej
samej kartki krążących jednocześnie w firmie — to fundamentalne założenie mechanizmu, nie
kwestia progu/marginesu do dostrojenia. Za zgodą użytkownika: **cały pikselowy detektor
zaznaczeń dla Hydrauliki został wyłączony**, zamiast kolejnej punktowej łatki.

## Co zostało zrobione

- `ocr/pipeline_hydraulika.py` — usunięty krok wywołujący `discover_hydraulika_quantity_marks()`
  i dopisujący do wyniku pozycje "wykryte lokalnie, pominięte przez AI"; usunięte pole
  `quantity_marks` z `OCRResultHydraulika`.
- `ocr/verification_image.py` — usunięta cała funkcja `discover_hydraulika_quantity_marks()` (i
  pomocnicze `discover_marked_hydraulika_rows()`), łącznie z nieudaną poprawką granic kolumn z
  punktu 3 powyżej. `_find_row_lines()`/`_HYDRAULIKA_PAGES`/`prepare_verification_files()`
  **zostają bez zmian** — to osobny, wciąż działający mechanizm (wycinanie already-zidentyfikowanych
  po nazwie wierszy do dodatkowej kontroli AI), niezwiązany z pikselowym wykrywaniem koloru.
- `documents/tasks.py` — `_verify_ambiguous_items()` wraca do prostej logiki sprzed wszystkich
  trzech poprawek: pozycja z pustymi obiema ilościami eskaluje do kontroli na podstawie samej
  deklaracji głównego modelu, bez dodatkowej weryfikacji pikselami (tak jak zawsze działało to
  dla Elektryki, która nigdy nie miała tego detektora). Parametr `quantity_marks` zostaje w
  sygnaturze dla zgodności z istniejącym mechanizmem `marked_column_missing` (weryfikacja
  brakującej pojedynczej kolumny) i testami — po prostu nikt już go nie wypełnia w produkcji.

## Efekt

- Zniknięcie fałszywych, "widmowych" pozycji w "Dodatkowej kontroli ilości" wynikających z
  niedopasowania fizycznego układu kartki do kodu.
- Koszt: na kartkach z dużą liczbą poprawek/skreśleń "Dodatkowa kontrola ilości" może ponownie
  obejmować więcej pozycji niż faktycznie zaznaczonych (ufamy z powrotem samej deklaracji
  głównego modelu) — zaakceptowane świadomie jako mniejsze zło niż ryzyko cichej utraty
  prawdziwej ilości przez zawodny detektor.

## Testy

- Usunięte testy specyficzne dla wyłączonego mechanizmu (`test_lokalnie_wykryty_trojnik_...` w
  `test_ocr_pipeline_hydraulika.py`, asercje `discover_hydraulika_quantity_marks`/
  `discover_marked_hydraulika_rows` w `test_ocr_verify.py`).
- Nowy test w `test_ocr_verify.py` (`test_obie_puste_ilosci_eskaluja_nawet_bez_quantity_marks`)
  blokuje powrotną regresję do "wymagania potwierdzenia pikselami".
- **Pełna suita: 345 testów przechodzi** (3 niepowiązane błędy w `test_catalog_db.py` to efekt
  uboczny ręcznie postawionej testowej bazy w środowisku deweloperskim tej sesji — diff w ogóle
  nie dotyka modułu `products`/`catalog`).

## Jak zweryfikować

```bash
cd backend
pytest tests/test_ocr_verify.py tests/test_ocr_pipeline_hydraulika.py tests/test_documents_task.py -v
pytest tests/ -q
```
