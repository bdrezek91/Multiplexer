# Reguła zgodności Multiplekser AUTO z dotychczasowym Gemini

**Nie wolno optymalizować czasu ani ceny kosztem funkcji, które wcześniej działały w produkcji Gemini.**

Minimalny kontrakt każdej kolejnej zmiany silnika OCR (Claude, Opus, Gemini, JEV, AUTO):

1. Automatyczne rozpoznanie właściwej branży: **Elektryka lub Hydraulika**; bez podstaw do pewnej decyzji → jawna kontrola, nie zgadywanie katalogu.
2. Odczyt **numeru projektu** z nagłówka i zachowanie rzeczywistych formatów, również skróconych (np. `127/07`). Dla pełnego numeru `625/05/26` normalizacja do `625/05/2026` zgodnie z `normalize_project_number`; **nie wolno dodawać roku, którego nie ma na skanie**.
3. Odczyt **pracownika, który zrobił wydawkę** (pole Pracownik). Nie utożsamiać z odbiorcą materiałów ani użytkownikiem, który przesłał plik.
4. Odczyt **numeru plomby-rozdzielni**, jeśli występuje. Pole puste na hydraulice jest dopuszczalne, nie domyślać się numeru.
5. OCR każdej strony dokumentu i dodatkowych dopisków. Żadnych strat w rozpoznawaniu podziału na strony i pozycji.
6. Osobny odczyt kolumn **ilość wydana** i **ilość zużyta**, bez kopiowania i zgadywania. Matcher/JEV nie ma prawa zmieniać ilości; należy zachować reguły magazynowe oraz PL/DE, 1P/3P, średnic itd.
7. Wynik w tych samych polach i formatach **DocumentModel/DocumentOut** co Gemini, aby wyszukiwanie, karta dokumentu, ręczna korekta, raporty i generator TXT działały bez zmian.
8. Jeśli którejś wartości z nagłówka nie można odczytać lub strony wskazują sprzeczne wartości, **zapisz null i sygnalizuj konieczność weryfikacji na karcie**, nigdy nie fałszuj danych.
9. Każdą istotną modyfikację testować zarówno na Elektryce, jak i Hydraulice oraz w testach regresyjnych. Priorytet: jakość i kompletność, dopiero potem szybkość.

## Wdrożenie przywracające odczyt nagłówka (2026-10-13)

Przy tworzeniu V3 AUTO przypadkowo ustawiono `numer_projektu=None`, `pracownik=None` i `numer_plomby=None` w gałęzi Claude, chociaż starsza ścieżka Gemini te pola odczytywała. To regresja.

Naprawa:
- `ops/claude_bridge_host.py`: Sonnet Low zwraca w pojedynczym OCR pozycje (`p`), dział (`d` w AUTO), znaczniki niepewnych odczytów (`u`) oraz dane nagłówka (`h`). Dotyczy obu trybów Claude, nie tylko AUTO.
- `backend/app/modules/documents/claude_bridge.py`: walidacja i normalizacja metadanych, odczyt nagłówków z kolejnych stron, wykrywanie sprzeczności, kompatybilność funkcji `run_claude_host_bridge` z wcześniejszymi wywołaniami.
- `backend/app/modules/documents/tasks.py`: zapis trzech pól do `repository.mark_done` przez istniejący `result`, rejestracja braków w `ai_trace` bez zapisywania danych osobowych do metryk.
- `frontend/src/pages/DocumentDetailPage.tsx`: wyraźne ostrzeżenie o braku projektu lub pracownika w zakończonym dokumencie Claude/AUTO.
- `backend/tests/test_claude_bridge.py`: regresje dla trzech pól, krótkich i pełnych numerów projektów, wielostronicowości, niezgodności numerów, starego interfejsu oraz trybu AUTO.

## Przeprowadzone testy OCR (odczyt archiwalnych dokumentów, bez modyfikacji bazy)

- Elektryka, oryginalny skan z dokumentu wcześniej przetworzonego przez Gemini: Claude odczytał numer projektu, pracownika, plombę i dział.
- Hydraulika, oryginalny skan z dokumentu wcześniej przetworzonego przez Gemini: Claude odczytał numer projektu i pracownika, pole plomby pozostało puste tak jak poprzednio. Dział mógł wymagać dodatkowej identyfikacji AUTO po nazwach materiałów.
- Na innej hydraulice Claude odczytał rzeczywisty skrócony numer projektu `127/07`; parser go zachowuje zamiast odrzucać.
- Bez pełnej niezależnej kontroli GOLD wszystkich pozycji materiałowych — nie przedstawiać tych testów jako 100% dokładności OCR.

**Każdy nowy silnik musi spełnić ten kontrakt PRZED zmianą domyślnego trybu użytkowników.**
