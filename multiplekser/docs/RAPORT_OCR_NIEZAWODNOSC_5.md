# Raport — usunięcie wycinania wierszy po współrzędnych (verification_image.py)

## Kontekst

Po wyłączeniu pikselowego detektora zaznaczeń dla Hydrauliki (`RAPORT_OCR_NIEZAWODNOSC_4.md`)
sprawdzono, czy analogiczny problem dotyczy Elektryki. Porównanie `_ELEKTRYKA_PAGES`
(zakodowany na sztywno układ fizycznych wierszy używany do wycinania obrazu na potrzeby
"Dodatkowej kontroli ilości") z aktualnym, żywym szablonem formularza (`FORM_ROWS`, używanym
do dopasowywania nazw) wykazało: **153 pozycje w `FORM_ROWS` vs tylko 69 w `_ELEKTRYKA_PAGES`**
— **84 pozycje** (m.in. gniazdka, wyłączniki nadprądowe, różnicówki, rozdzielnice SRN, korytka
kablowe, końcówki tulejkowe) nie mają w ogóle zdefiniowanego miejsca do wycięcia.

Mechanizm miał wbudowany bezpieczny fallback (brak lokalizacji dla którejkolwiek żądanej
pozycji → cały, niezmieniony obraz zamiast błędnego wycinka), więc nie groziło to cichym
błędem jak w Hydraulice — tylko utratą precyzji "zoomowania" dla ~55% katalogu Elektryki.

Rozstrzygający argument od użytkownika: **papierowa wydawka różni się za każdym razem**
(różne wersje/rewizje formularza w obiegu, rosnące z czasem — stąd rozjazd 69 vs 153). Żaden
sztywny układ współrzędnych wierszy nie może tego trwale obsłużyć, niezależnie jak dokładnie
zostałby dziś zmapowany — kolejna zmiana wydawki i tak by go zdezaktualizowała. To nie jest
przypadek do punktowej naprawy (jak wcześniej dwie łaty dla Hydrauliki), tylko błędne założenie
architektoniczne u podstaw całego mechanizmu.

## Decyzja

Za zgodą użytkownika: **całkowicie usunięty mechanizm wycinania konkretnych wierszy po
współrzędnych, dla obu działów jednocześnie.** "Dodatkowa kontrola ilości" działa teraz zawsze
na pełnym, niezmienionym obrazie dokumentu — dokładnie tak, jak już bezpiecznie działała w
przypadku braku mapowania.

## Co zostało zrobione

- **Usunięty cały plik `ocr/verification_image.py`** (478 linii) — `_ELEKTRYKA_PAGES`,
  `_HYDRAULIKA_PAGES`, `_FORM_LAYOUTS`, `_FORM_LOCATIONS`, `_norm`, `_render_pages`,
  `_horizontal_line_centers`, `_drop_weak_candidates`, `_trim_isolated_edges`,
  `_find_row_lines`, `_interpolate_faint_table_lines`, `_row_crop`, `_compose_crops`,
  `prepare_verification_files` — cała ta infrastruktura istniała wyłącznie na potrzeby
  wycinania wierszy po współrzędnych.
- `ocr/verify.py: verify_ambiguous_quantities()` — usunięte wywołanie
  `prepare_verification_files()`; `verification_files, cropped` ustawiane wprost na
  `files, False` (zawsze pełny dokument). Parametr `dzial` zostaje w sygnaturze (już nieużywany
  wewnątrz) — usunięcie go z API czterech miejsc wywołania to osobna, niezwiązana zmiana,
  świadomie odłożona.
- `ocr/chain.py` — zaktualizowany komentarz w `quantity_verification_chain()`, który błędnie
  sugerował że `dzial` nadal wybiera układ wycinka.

## Testy

- Usunięty `tests/test_ocr_verification_image_row_lines.py` (5 testów specyficznych dla
  usuniętego mechanizmu wykrywania linii siatki).
- `tests/test_ocr_verify.py` — usunięte 2 testy wycinania obrazu
  (`test_formularz_elektryczny_jest_zamieniany_na_jeden_obraz_z_wycinkiem`,
  `test_hydraulika_wycina_tylko_docelowy_wiersz`), usunięty import `prepare_verification_files`
  i 3 zbędne monkeypatche. Test `test_jedno_zapytanie_obsluguje_wiele_pozycji` zaktualizowany:
  asercja teraz potwierdza, że do modelu trafia oryginalny, niezmieniony dokument (nie wycinek).
- **Pełna suita: 340 testów przechodzi** (3 niepowiązane błędy w `test_catalog_db.py` - efekt
  uboczny testowej bazy w tym środowisku, diff nie dotyka modułu `products`/`catalog`).

## Świadomie zaakceptowany kompromis

Na bardzo zagęszczonych, wielowierszowych kartkach "Dodatkowa kontrola ilości" może być odrobinę
mniej precyzyjna (model widzi cały dokument zamiast jednego wskazanego wiersza) — zaakceptowane
jako rozsądny koszt w zamian za zero ryzyka błędnego dopasowania wiersza i zero konserwacji przy
każdej zmianie fizycznego układu papierowej wydawki.

## Jak zweryfikować

```bash
cd backend
pytest tests/test_ocr_verify.py tests/test_ocr_pipeline_hydraulika.py -v
pytest tests/ -q
```
