# Raport — błędne przesunięcie wierszy w kontroli ilości Hydraulika (verification_image.py)

Zgłoszenie od użytkownika: na dokumencie Hydraulika 8 pozycji przeszło przez "Dodatkową kontrolę
ilości" i skończyło jako "Bez wyniku" — żaden z 6 modeli w łańcuchu (4× Gemini darmowy, Gemini
płatny, OpenAI) nie znalazł ilości dla: Blat kuchenny 825x600, Bojler 50 L, Kolanko
kanalizacyjne fi 32/40/50 45°, Końcówka srebrna, Kratka wentylacyjna 140x140 biała/grafit.

Po otrzymaniu od użytkownika oryginalnej papierowej wydawki (PDF) okazało się, że wszystkie te
8 pozycji są na papierze faktycznie **puste** — ale zamiast zostać poprawnie pominięte, trafiły
do kontroli ilości, bo lokalny detektor niebieskich zaznaczeń (`discover_hydraulika_quantity_marks`)
błędnie odczytywał **sąsiednie** wiersze zamiast właściwych.

## Przyczyna (dwie niezależne, obie w `ocr/verification_image.py`)

1. **`_find_row_lines` mogło wybrać fałszywego kandydata na linię tabeli.** Tuż pod pogrubionym
   nagłówkiem kolumn ("Nazwa / Ilość wydana / Ilość zużyta / Jednostka") wykrywacz linii złapał
   dwie słabe, przypadkowe "linie" (siła ~380 przy prawdziwych liniach tabeli ~1221 — najpewniej
   fragment tekstu nagłówka, nie prawdziwa linia siatki). Weszły one do wybranej siatki wierszy
   i przesunęły indeksowanie wszystkich kolejnych wierszy strony o 2 pozycje — wycinek podpisany
   jako "Blat kuchenny 825x600" pokazywał w rzeczywistości "Blat kuchenny 1200x600" i jego
   zaznaczenie.
2. **`_HYDRAULIKA_PAGES` (twardo zakodowany układ fizycznych wierszy do cropowania) miał błąd
   na granicy stron.** "Nakrętka M12" było błędnie ostatnią pozycją **1. strony** zamiast
   pierwszą pozycją **2. strony**, a prawdziwy, drukowany wiersz "Blat kuchenny 1650x600"
   (potwierdzony w katalogu Optima — `baza_hydraulika.json`) w ogóle nie występował na liście.
   Efekt: liczba wierszy zgadzała się przypadkiem (1 błędnie obecny za dużo na końcu, 1 błędnie
   nieobecny w środku), ale każdy wiersz od "Blat kuchenny 1650x600" w dół pokazywał zawartość
   sąsiedniego, złego wiersza.

Diagnoza potwierdzona bezpośrednio na przesłanym przez użytkownika PDF-ie (nie zgadywana) —
wycięto i zwizualizowano konkretne wiersze, porównano z oryginałem piksel po pikselu.

## Co zostało zrobione

- `ocr/verification_image.py`:
  - `_drop_weak_candidates()` (nowa) — odrzuca kandydatów na linię, których siła jest poniżej
    60% najsilniejszej linii na stronie (względny próg, nie stała — działa tak samo na
    wyraźnym i bladym skanie).
  - `_trim_isolated_edges()` (nowa) — odcina odosobnione kandydatów na krańcach listy (np.
    artefakt górnej krawędzi renderu strony), których odległość do sąsiada rażąco odbiega od
    typowego rozstawu wierszy.
  - `_find_row_lines()` stosuje oba filtry (najpierw słabe kandydatury, potem izolowane
    krańce — kolejność ważna, patrz komentarz w kodzie) przed wyborem siatki wierszy.
  - `_HYDRAULIKA_PAGES`: dodano "Blat kuchenny 1650x600" na 1. stronie (między "1250x600" a
    "825x600"), przeniesiono "Nakrętka M12" z końca 1. strony na początek 2. strony.

## Testy

- `tests/test_ocr_verification_image_row_lines.py` (nowy, 5 testów):
  - 2 testy layoutu (pozycja "Blat kuchenny 1650x600", "Nakrętka M12" na właściwej stronie).
  - 3 testy na syntetycznych obrazach odtwarzających realne artefakty (słaba linia, izolowana
    linia, oba naraz) — potwierdzają, że `_find_row_lines` zawsze zwraca prawdziwą, regularną
    siatkę.
- **Pełna suita: 336 → 341 testów backendu, zero regresji.**
- Ręczna weryfikacja na oryginalnym PDF-ie od użytkownika: `discover_hydraulika_quantity_marks`
  teraz zgadza się 1:1 z ręcznie odczytanym papierem dla całej 1. strony (wszystkie zaznaczone
  i wszystkie puste pozycje poprawne).

## Co zostało świadomie odłożone

| Temat | Uwaga | Plan |
|---|---|---|
| `discover_hydraulika_quantity_marks`/`prepare_verification_files` zakładają, że strony 1 i 2 formularza to kolejno `pages[0]`/`pages[1]` z renderu PDF | Przesłany przez użytkownika PDF miał **puste strony przeplecione** między stronami z treścią (skan dwustronny), więc `pages[1]` to czasem pusta strona, nie 2. strona formularza — `_find_row_lines` wtedy zwraca `None` i lokalny detektor cicho pomija całą 2. stronę. Główny odczyt AI (pełnoobrazowy) nie ma tego problemu, bo czyta cały PDF na raz, nie po indeksie strony — to dotyczy WYŁĄCZNIE lokalnego zapasowego detektora | Do zbadania, jeśli okaże się, że taki PDF trafia do produkcji regularnie — np. wykrywanie i pomijanie pustych stron przed indeksowaniem |
| "Blat kuchenny 1650x600" w `form_rows_hydraulika.py` jest w `ADDITIONAL_ROWS` (baza dodatkowa), nie w `FORM_ROWS` (stały szablon 145 pozycji) | Mimo że fizycznie jest wydrukowany na formularzu — niespójność z dokumentacją modułu ("145 pozycji = stały szablon"). Nie dotyczy dzisiejszego zgłoszenia (ten mechanizm to dopasowanie nazw z OCR, nie cropowanie obrazu) | Do rozważenia osobno — przeniesienie do `FORM_ROWS` wymaga ponownego przeliczenia progów dopasowania, nie robić bez wyraźnej potrzeby |
| Możliwe inne luki w `_HYDRAULIKA_PAGES`/`FORM_ROWS` (ten sam wzorzec co `docs/RAPORT_OCR_NIEZAWODNOSC_2.md`) | Nie da się wyczerpująco zweryfikować bez pustego oryginalnego szablonu | Jak poprzednio — kolejne zgłoszenie błędnego dopasowania/braku wyniku = ten sam schemat diagnozy |

## Jak zweryfikować

```bash
cd backend
pytest tests/test_ocr_verification_image_row_lines.py -v
pytest tests/ -q   # 341 testow, 1 pominiety
```
