# Wersjonowanie Multipleksera i wydania

Repozytorium od początku ma już numerację `1.0.x` w pliku `VERSION` i istniejące tagi `v1.0.x`. Kontynuujemy ją zamiast tworzyć drugą serię.

## Zasady

- **Mała poprawka w kodzie:** osobny commit; numer wydania nie musi się zmieniać, dopóki nie wdrożymy poprawki produkcyjnie.
- **Większa zmiana produkcyjna lub pakiet napraw:** kolejny numer w `VERSION`, opis w tym pliku, commit wydania i tag `vX.Y.Z`.
- **Nowy eksperymentalny silnik OCR:** nazwa `V4 Shadow`, bez przełączania produkcji. To nazwa architektury, nie numer wydania całej aplikacji.
- **Wydanie głównej wersji silnika** (np. przejście V3 AUTO → V4): najpierw testy na niezależnych ręcznie zweryfikowanych arkuszach, potem świadoma decyzja o zmianie domyślnego silnika.
- **Możliwość cofnięcia:** tag identyfikuje kod do powrotu. Wydanie z ewentualną migracją DB wymaga także instrukcji bezpiecznego rollbacku.
- **Bez zmiany cudzych plików:** nie obejmujemy wydaniem przypadkowych niepowiązanych plików VPS, kopii czy lokalnych prac innych projektów.

## v1.0.44 — V3 AUTO safety + V4 geometry shadow (2026-10-13)

Naprawy dla hydrauliki:
- kontrola Opus nie tworzy trzeciej pustej grupy stron; żądanie ma maksymalnie 2 strony i 3 pozycje;
- `ZAS 127` i `Zaślepka 127 czerwona` są pomijane w TXT również przy otwieraniu starszych dokumentów;
- wkręty z konkretnym rozmiarem i RAL nie mogą być eksportowane pod ogólnym kodem zestawu; konflikt staje się komentarzem o braku dopasowania i wymaga kontroli;
- JEV raportuje osobno liczbę odpowiedzi i liczbę faktycznie poprawnych kodów, zamiast utożsamiać odpowiedź z zatwierdzeniem;
- porównanie Claude/Gemini używa sprawdzonych nazw drukowanego formularza dla hydrauliki, zachowując osobne wymiary, kąty i numery stron;
- zachowano brak obowiązku odczytu numeru plomby dla hydrauliki.

V4 Shadow (tylko testy, nie zapisuje dokumentów, nie wpływa na TXT):
- detekcja granic kolumn wydana/zużyta na skanach przez analizę pikseli bez stałych współrzędnych;
- wykrywanie linii formularza, wycinanie obszarów komórek dla dalszych testów OCR;
- nie przypisuje jeszcze nazw produktów, ponieważ istnieją różne odmiany drukowanego formularza.

Regresje: testy selekcji Opus, zasad generatora, OCR i JEV. Wersja V4 zostanie produkcyjna dopiero po zestawieniu z co najmniej 50 wydawkami GOLD i sprawdzeniu, że żadne dane z Gemini nie zginęły.

### Poprawka wyświetlania wersji po v1.0.44

Panel, ekran logowania oraz API nie mogą mieć wpisanej na sztywno poprzedniej wersji.
Główny plik `VERSION` jest montowany w produkcyjnym backendzie pod `/app/VERSION`
(plik musi być czytelny dla użytkownika `app`, zalecany tryb `0644`).
Publiczne `/api/version` zwraca bieżącą wersję z nagłówkiem `Cache-Control: no-store`.
Frontend pobiera ją i aktualizuje pasek, ekran logowania oraz tytuł strony.
Dokument HTML w nginx ma ustawiony zakaz cache, aby przeglądarka nie utrzymywała
poprzedniej wersji panelu po deployu. Testy chronią tę funkcję przed regresją.

## v1.0.45 — Gemini-first, Claude awaryjny (2026-10-13)

- Domyślny tryb AUTO: najpierw **Gemini 3.5 Flash Lite z kluczem darmowym**, klasyfikacja działu (do 5 s) i pełny OCR (do 18 s). Wykorzystywany jest dotychczasowy prompt, parser, matcher i pola numeru projektu, pracownika i numeru plomby dla elektryki.
- Jeśli Gemini jest niedostępny, przekroczy timeout albo zwróci bezużyteczny OCR, wtedy **Claude Sonnet jako zapasowe oczy**. Po nim nadal matcher i aktywny JEV. Jeśli oba nie działają — jawny błąd zamiast zgadywania.
- Brak równoległego pełnego odczytu drugiego modelu i brak automatycznej kontroli Opus dla AUTO. Zachowano manualny tryb diagnostyczny Gemini/Claude.
- Nie ma automatycznego przełączenia na klucz płatnego Gemini ani OpenAI. Claude Pro ma własne limity; w ustawieniach Anthropic należy kontrolować dodatkowe płatne kredyty.
- Reguły bezpieczeństwa dotyczące hydrauliki pozostają aktywne: brak plomby, ZAS 127 wyłączone z TXT, wkręty muszą mieć zgodny rozmiar i RAL.
- Klasyfikacja, nagłówek i OCR są mierzone w ai_trace / panelu; przy awarii Gemini wyraźnie widać, że uruchomiono Claude.
- **Istotne ograniczenie jakości:** na jednym archiwalnym skanie 3 stron Gemini Flash Lite odczytał 45–46 pozycji, podczas gdy wynik Claude zawierał 50; część różnic to wykluczenia, ale były też pominięcia rzeczywistych materiałów. Dlatego wyniki nowej ścieżki wymagają kontroli skanu przed importem do Optimy. Nie wolno utożsamiać krótszego OCR z wyższą trafnością.
- Gemini 3.5 Flash (bez Lite) w teście trzech stron nie zmieścił się w 18 s i zwrócił odrzuconą strukturę, więc nie został ustawiony jako główny model.

Ponieważ nazwa silnika AUTO nie jest numerem wydania aplikacji, V3 AUTO zachowuje nazwę, a numer aplikacji rośnie do 1.0.45.
