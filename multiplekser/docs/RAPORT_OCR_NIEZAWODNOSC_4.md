# Raport — nadmierna eskalacja do "Dodatkowej kontroli ilości" na kartkach z poprawkami

Zgłoszenie od użytkownika: na jednej wydawce Hydraulika (dużo odręcznych poprawek/skreśleń,
nadpisanych cyfr) "Dodatkowa kontrola ilości" objęła ~19 pozycji naraz i przeszła przez 6 prób/
modeli w ~80 sekund, kończąc się "Bez wyniku" dla 5 z nich.

## Przyczyna

`_verify_ambiguous_items()` (`documents/tasks.py`) eskaluje do kosztownej, wielomodelowej
kontroli każdą pozycję z pustymi obiema ilościami (`ilosc_wydana`/`ilosc_zuzyta` = `null`).
Taka pozycja w ogóle istnieje w wyniku tylko dzięki temu, że główny model OCR sam zgłosił
`ma_oznaczenie: true` (patrz `is_actionable_item()`, `ocr/parsing.py`) — to jedyny sposób, by
wiersz bez odczytanej liczby przeszedł filtr "pomiń puste wiersze szablonu".

System ufał tej samopotwierdzonej deklaracji bez żadnej niezależnej weryfikacji. Na kartkach z
dużą liczbą poprawek/skreśleń model potrafi zgłosić `ma_oznaczenie=true` dla wierszy, które w
rzeczywistości są puste — myli go bałagan w sąsiedztwie, nie realne zaznaczenie w komórce
ilości. Zweryfikowane na przesłanej przez użytkownika wydawce: znaczna część z 19 eskalowanych
pozycji była pusta na papierze.

## Co zostało zrobione

`documents/tasks.py: _verify_ambiguous_items()` — pozycja z obiema pustymi iloścami eskaluje do
kontroli teraz tylko gdy:
- lokalny pikselowy detektor zaznaczeń (`quantity_marks`, Hydraulika,
  `discover_hydraulika_quantity_marks`) **potwierdza** zaznaczenie w którejś kolumnie, **lub**
- detektor nie znalazł nic na całym dokumencie (pusty słownik `quantity_marks`) — zwykle znaczy,
  że nie zdążył przeanalizować strony (znany, wcześniej opisany przypadek: przeplatane puste
  strony skanu, `RAPORT_OCR_NIEZAWODNOSC_3.md`) — wtedy nie ma czym potwierdzać, więc zachowanie
  wraca do zaufania modelowi jak dotąd (bez regresji dla Elektryki, która w ogóle nie ma tego
  detektora, i dla przypadków gdy detektor Hydrauliki zawiedzie).

Sprawdzanie brakującej **pojedynczej** kolumny (`marked_column_missing`) — gdy druga kolumna ma
już odczytaną wartość — jest bez zmian, to osobna, już wcześniej zawężona ścieżka.

## Ryzyko świadomie zaakceptowane

Bardzo blade/małe zaznaczenie, które model AI słusznie wyłapał, ale które nie przekroczy progu
pikselowego detektora, nie trafi już do dodatkowej kontroli (rzadki false negative zamiast
obecnego nadmiaru false positive). Uznane za lepszy kompromis niż płacenie za kontrolę pustych
wierszy przy każdej bardziej zabazgranej kartce.

## Testy

- `tests/test_ocr_verify.py` — 2 nowe testy: potwierdzenie pikseli wymagane gdy detektor coś
  znalazł na dokumencie; zaufanie modelowi zachowane gdy detektor nic nie znalazł (pusty
  słownik). Wszystkie 3 istniejące testy `_verify_ambiguous_items` bez zmian, nadal przechodzą.
- **Pełna suita: 224 → 226 testów backendu (+2), zero regresji** (pozostałe błędy w pełnym
  przebiegu to wyłącznie brak Postgresa w środowisku deweloperskim, niezwiązane ze zmianą).

## Jak zweryfikować

```bash
cd backend
pytest tests/test_ocr_verify.py -v
pytest tests/ -q
```
