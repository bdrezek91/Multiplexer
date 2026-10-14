# Multiplekser 1.0.47 — Gemini-only OCR + cleanup UI

## Zakres

- **Nowe dokumenty**: wyłącznie `auto_v3` (Gemini FREE1 / FREE2, następnie matcher i JEV). Nie można już rozpocząć ręcznego testu Claude ani `standard` z UI/API. Stare dokumenty zapisane wcześniej pozostają w bazie, bez edycji.
- Usunięto host bridge Claude z runtime, osobną kolejkę Celery `claude`, serwis Docker `worker-claude`, endpoint monitorowania `/documents/claude-usage`, kod pomocniczy bez odwołań, stare testy Claude.
- Rozdzielone etykiety cooldown per konto/model w `auto_v3.py` pozostają jak w wersji 1.0.46; `429`/`503` przełączają FREE1 → FREE2, modele alternatywne są próbami rezerwowymi. Klucz płatny pozostaje skonfigurowany, ale AUTO nigdy go nie wywołuje.
- **Fail-closed**: jeśli wszystkie darmowe Gemini zwrócą błędy, nie ma awaryjnej zmiany dostawcy ani tworzenia fikcyjnych pozycji; dokument jest `error` z czytelnym komunikatem, ponowne przesłanie po odnowieniu limitu.
- Każda zmiana ilości przez matcher/JEV jest cofana do wartości OCR i oznaczona do kontroli; JEV ma dobierać kody, nie liczby.
- UI: tylko upload, magazyn i AUTO; znikają przełączniki diagnostycznych silników, wybór działu Claude i kafel abonamentu/zużycia Claude. Zostają historia AI, podgląd skanów, korekta ilości, JEV i eksport TXT.

## Code review i ryzyka

1. Poprzednio `auto_v3` dokumenty były przesyłane do osobnej kolejki **`claude`**, mimo że podstawowy OCR już wykonywał Gemini. Teraz wszystkie nowe dokumenty są kierowane do głównej kolejki `ocr`.
2. Poprzednio nieudane Gemini wywoływało Claude Sonnet przez host bridge, zależny od dodatkowego procesu i limitu. Cała ścieżka usunięta z produkcji i konfiguracji.
3. Poprzednio ochrona ilości przed nadpisaniem przez JEV była warunkowa (tylko Claude). Obecnie dotyczy także Gemini.
4. Starsze dokumenty mogą zawierać w historii `used_provider`/`ai_trace` z nazwą Claude. To archiwalne dane i nie należy ich kasować ani fałszować. Nie jest to aktywna integracja.
5. Klucze Google mają osobne cooldowny per projekt/model, ale żadna zmiana kodu nie gwarantuje całego OCR poniżej 20 sekund. Istnieją udokumentowane rozbieżności ilości; wymagają dalszego GOLD.
6. CLI `backend/scripts/bridge_claude_jev_shadow.py` (historyczny skrypt diagnostyczny z **niezatwierdzonymi** lokalnymi zmianami) i `Caddyfile` pozostają nietknięte; nie są importowane przez produkcyjny OCR. Nie usuwaj prywatnych historii ani danych użytkownika.

## Wdrożenie i weryfikacja

- Baza/Redis/MinIO i Caddy nie są zmieniane i nie potrzebują migracji.
- Wdrażaj razem `backend`, `worker`, `worker-background` i `web` ze spójnego commita; poprzednie obrazy kontenerów zachowaj pod etykietami rollback.
- Zatrzymaj i usuń **tylko** `multiplekser-worker-claude-1`, bez `docker compose down -v` i bez `--remove-orphans` (na serwerze są także inne aplikacje).
- Sprawdź, że wszystkie kontenery są zdrowe, Celery podłączony do Redisa, obydwa FREE skonfigurowane, API `/documents/claude-usage` zwraca `404`, upload ze starym `claude_jev_test` zwraca `422`.
- Sprawdź nową wersję `VERSION=1.0.47` i brak starych elementów Claude w UI.
- Rollback: przywróć poprzednie obrazy i plik compose z poprzedniego commita, następnie uruchom serwisy; nie ruszaj dokumentów historycznych ani danych bazy.
