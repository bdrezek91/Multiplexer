# Raport — brakujący wiersz formularza "Rura fi 32 100 cm"

Zgłoszenie od użytkownika: na wydawce dopasowany kod wyszedł jako `RURA FI 32 50 CM`, mimo że na
oryginalnym dokumencie było napisane "rura 32 100". To **inny** mechanizm niż poprzednia poprawka
(`docs/RAPORT_ETAP_HYDRAULIKA_6.md` - dodanie kodu `RURA FI 32 100 CM` do katalogu produktów) -
tamta poprawka dotyczyła **dopasowania do kodu Optima**, ta dotyczy **wcześniejszego** kroku:
normalizacji odczytanego tekstu do znanego wiersza formularza (`ocr/form_rows_hydraulika.py`,
`FORM_ROWS` - lista 144 pozycji, osobna od katalogu produktów w bazie).

## Przyczyna

`FORM_ROWS` miało dla średnicy fi32 tylko dwie długości: `'Rura fi 32 30 cm'` i
`'Rura fi 32 50 cm'` - **brakowało `'Rura fi 32 100 cm'`**, mimo że fi30 miało swój wiersz
100 cm (`'Rura fi 30 100 cm'`). Dopasowanie działa przez podobieństwo tekstu (współczynnik
Dice'a na bigramach) do najbliższego znanego wiersza z listy - skoro dokładnego wiersza
"fi 32 100 cm" nie było na liście, odczytany tekst dopasowywał się do najbliższego dostępnego
(`'Rura fi 32 50 cm'` - ta sama średnica, zła długość), z wynikiem podobieństwa wystarczającym
by przejść próg "fixed" (>=0.70) i po cichu podmienić nazwę.

Plik jest oznaczony jako port 1:1 z monolitu (`Multipekser_Hydraulika.html`, którego nie ma już
w repo - usunięty po migracji, patrz `CLAUDE.md`), więc **nie zgadywano** tej zmiany - oparto się
na bezpośrednim potwierdzeniu właściciela, że to prawdziwy, drukowany wiersz formularza (ten sam
materiał, dla którego wcześniej potwierdzono i dodano kod `RURA FI 32 100 CM` do katalogu Optima)
- najpewniej pominięty przy pierwotnym przepisywaniu listy, nie świadomie wykluczony.

## Co zostało zrobione

- `ocr/form_rows_hydraulika.py`: dopisano `'Rura fi 32 100 cm'` do `FORM_ROWS` (145 pozycji,
  było 144), zaraz po istniejących wpisach dla tej średnicy.
- Zaktualizowano dokumentację w nagłówku pliku.

## Testy

- `test_form_rows_ma_145_pozycji` (zaktualizowany z 144).
- `test_snap_rura_fi_32_100_cm_nie_myli_sie_z_50_cm` (nowy) - potwierdza, że "Rura fi 32 100 cm"
  dopasowuje się teraz dokładnie do siebie (`status="exact"`), nie fuzzy-matchuje do "50 cm".
- **Pełna suita: 256 → 257 testów, zero regresji.**

## Ryzyko do świadomości (nie do natychmiastowej akcji)

Skoro ten jeden wiersz został pominięty przy pierwotnym porcie, **statystycznie możliwe, że są
inne podobne luki** w 144-pozycyjnej liście `FORM_ROWS` (np. inne kombinacje średnica+długość
rur/wężów). Nie da się tego wyczerpująco zweryfikować bez dostępu do oryginalnego, pustego
szablonu papierowego formularza - jedyna wiarygodna metoda wykrywania to to, co się właśnie
wydarzyło: użytkownik zauważa złe dopasowanie na realnej wydawce i zgłasza. Każde kolejne takie
zgłoszenie - to samo rozwiązanie (sprawdzić czy istnieje odpowiedni kod w katalogu Optima, jeśli
tak, sprawdzić czy jest w `FORM_ROWS`, dopisać brakujące).

## Jak zweryfikować

```bash
cd backend
pytest tests/test_ocr_form_rows_hydraulika.py -v
pytest tests/ -q   # 257 testow, 1 pominiety
```
