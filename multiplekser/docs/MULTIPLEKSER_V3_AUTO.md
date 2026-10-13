# Multiplekser V3 AUTO — 13 października 2026

## Użytkowanie

Panel Dokumenty został uproszczony do jednego przycisku **Rozpoznaj wydawkę**. AUTO jest domyślne. Nie trzeba ręcznie wybierać Gemini/Claude ani Elektryki/Hydrauliki. Dla administratora dostępny jest mały przycisk **Diagnostyka modeli** z ręcznymi opcjami: AUTO, Gemini, Claude + JEV oraz wyborem działu w ręcznym trybie.

Dotychczasowe dokumenty i ich oryginały zachowano. Import TXT do Optimy nadal wymaga kontroli przez człowieka. Podgląd skanu działa wewnątrz panelu.

## Ścieżka AUTO

1. Formularz wysyła `ocr_engine=auto_v3`, zapisany w `DocumentModel.source_type` jako `auto_v3`. Celery kieruje dokument do **oddzielnej kolejki claude** (1 worker); zwykła kolejka Gemini pozostaje niezależna.
2. PDF i zdjęcia są przygotowywane jak wcześniej (strony do JPG). Hostowy Claude Code CLI (OAuth właściciela Claude Pro) wykonuje równoległy OCR Sonnet Low. W trybie AUTO dodatkowo odczytuje nagłówek działu (`d`) i indeksy podejrzanych wierszy (`u`), bez kodów Optimy.
3. `auto_v3.classify_auto_dzial` potwierdza dział przy pomocy słownika nazw materiałów. Sprzeczność nagłówka i materiałów albo brak jednoznacznych wskazówek **powoduje błąd z instrukcją weryfikacji** — system nie zgaduje katalogu.
4. Bazowy matcher z katalogu danej branży i aktywny JEV wybierają kody, magazyn i zasady. JEV nie może zmieniać ilości OCR, niepewne kody są oznaczane do weryfikacji.
5. Jeśli pierwszy OCR sygnalizuje niepewność albo matcher zwraca niedopasowanie, AUTO może wykonać **drugi celowany odczyt nazwy i obu ilości** modelem Opus High dla maksymalnie **trzech pozycji na dwóch stronach**. Jest to zapytanie ukierunkowane na nazwy na skanie, obecnie nie geometryczny crop. Przy sprzecznych ilościach system **nigdy nie nadpisuje pierwszego odczytu w ciemno**; oznacza konflikt do ręcznego potwierdzenia. Jeśli Opus nie odpowie, pozostaje kontrola manualna.
6. Gdy Claude Pro zgłosi wyczerpanie limitu, wyłącznie dla AUTO uruchamia się fallback Gemini z filtrami ściśle `label = darmowy` i `api_key = GEMINI_API_KEY_FREE`. Nie może użyć `GEMINI_API_KEY_PAID` ani `OPENAI_API_KEY`. Cały wynik fallbacku zostaje oznaczony do kontroli. Inne błędy Claude nie wywołują automatycznie płatnego fallbacku.
7. Raport przebiegu modeli w `ai_trace` i wynik dokumentu w tym samym interfejsie co dotychczas.

## Zabezpieczenia, limity i pomiary

- Claude Pro podlega własnym limitom pięciogodzinnym i tygodniowym. Konto powinno mieć wyłączone dodatkowe płatne usage credits/extra usage, jeśli celem jest sztywne $20 bez dopłat.
- Dokładny procent limitu nie jest znany aplikacji. Dashboard admin pokazuje wykonaną pracę i dostępność hosta.
- Nie gwarantujemy 20 sekund dla każdej wydawki. Trudne dokumenty wymagające Opus High albo awaryjnego Gemini będą trwać dłużej.
- Nie ma automatycznego księgowania/eksportu do Optimy i nie wolno usuwać ręcznej korekty.
- W razie niedostępności CLI lub błędnej klasyfikacji dokument przejdzie do statusu error; użytkownik może użyć ręcznego trybu diagnostycznego.
- Claude ma wyłączone narzędzia wykonywania poleceń. OAuth pozostaje na hoście, nie w Dockerze.

## Weryfikacja

Przetestowano na istniejących wydawkach (tylko odczyt, bez modyfikowania ich pozycji):
- Elektryka: **13 rozpoznanych pozycji pierwszej strony, dział wykryty poprawnie, 6,83 s OCR**.
- Hydraulika: **21 rozpoznanych pozycji pierwszej strony, dział wykryty poprawnie, 8,23 s OCR**, 2 pozycje oznaczone jako niepewne.

Ponadto testy jednostkowe kontrolują sprzeczności klasyfikacji, sprawdzanie zgodności dwóch kolumn ilości, zachowanie ilości przed decyzjami JEV i wyłączność darmowych modeli podczas fallbacku. To nie jest jeszcze pełny niezależny GOLD dla 20–50 dokumentów.

Operacje:
- `systemctl status multiplekser-claude-bridge`
- `docker compose -f docker-compose.prod.yml ps backend web worker-claude worker`
- `docker compose -f docker-compose.prod.yml logs -n 50 worker-claude`

Kod: `backend/app/modules/documents/auto_v3.py`, `ops/claude_bridge_host.py`, `backend/app/modules/documents/tasks.py`, `frontend/src/pages/DocumentsPage.tsx`.
