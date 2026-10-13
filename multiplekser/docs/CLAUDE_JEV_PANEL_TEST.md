# Multiplekser: wybór Claude + JEV w panelu (wersja testowa)

## Dla administratora

1. Otwórz **Dokumenty → Wyślij nowy skan**.
2. Wybierz zdjęcia albo PDF, magazyn opcjonalny.
3. W sekcji silnika wybierz **Claude + JEV (test)** zamiast **Standardowy OCR (Gemini)**.
4. Wybierz dział **Elektryka** lub **Hydraulika** — to część testu i eliminuje dodatkową klasyfikację.
5. Kliknij **Zatwierdź i wyślij do rozpoznania**. Status zobaczysz na istniejącej stronie dokumentu.
6. Sprawdź **wszystkie ilości i kody** ze skanem przed pobraniem TXT. Dokument ma ostrzeżenie „Claude + JEV — dokument testowy”.

Tryb działa aktualnie dla **administratora**, aby pracownicy nie zużyli nieświadomie limitu prywatnej subskrypcji Claude Pro. W trybie testowym **nie jest wywoływany Gemini**. Claude Sonnet Low tylko odczytuje nazwy i obie ilości, a istniejący matcher i **aktywny JEV** dobierają materiały. Reguły Elektryki/Hydrauliki pozostały te same.

Standardowa ścieżka Gemini jest **domyślna i niezmieniona**. Nie ma automatycznej wysyłki TXT do Optimy.

## Architektura

* Formularz: `frontend/src/pages/DocumentsPage.tsx`, API `uploadDocument(..., ocrEngine, claudeDzial)`.
* Backend: `POST /documents` przyjmuje `ocr_engine=standard|claude_jev_test`, opcjonalny `claude_dzial=elektryka|hydraulika` (dla Claude wymagany).
* Rozróżnienie bez migracji DB: `document.source_type=claude_jev_test_<dzial>`.
* Celery: `documents.process_ocr` wybiera ścieżkę po `source_type`; zapis i podgląd dokumentu jak dotąd; automatyczne dodatkowe weryfikacje Gemini pomijane w testowym trybie Claude.
* Wewnątrz workera: `backend/app/modules/documents/claude_bridge.py` wysyła przez prywatny filesystem IPC do `/claude-bridge/jobs/<uuid>`.
* Na **hoście VPS**: `ops/claude_bridge_host.py` jako usługa systemd `multiplekser-claude-bridge`. Host ma oryginalny Claude Code CLI zalogowany do Pro. Hasło/OAuth **nie są montowane w Dockerze**. Claude dostaje jedynie JPG i bardzo ograniczony prompt, uruchamiany z `--restricted --tools "" --strict-mcp-config`. Model zwraca tylko minimalną listę [nazwa, wydana, zużyta].
* Zdarzenia/odczyt bazowy → matcher katalogu i istniejący JEV active; typ i dział zapisane w dokumentach.

Tylko worker ma dostęp do bind mount `/var/lib/multiplekser-claude-bridge`; uprawnienia `0700`, właściciel UID/GID aplikacji kontenera (999). Usługa hostowa zapisuje wyniki `0600` z właścicielem katalogu zadania.

## Limity

* Maksymalnie **6 stron JPG** po przetworzeniu pliku, do 8 MB każda. Brak metadanych numeru projektu z Claude — można poprawić ręcznie na stronie dokumentu.
* Timeout 175 s; użycie Claude Pro podlega limitom subskrypcji (brak gwarancji 20 s ani gwarancji dostępności).
* Testowane zostały **hydrauliczne** trzy strony wydawki, 43 pozycje; **nie** ma jeszcze benchmarku jakości elektryki w nowym trybie.
* Żadna wartość OCR nie jest automatycznie uznawana za zatwierdzoną. Jeśli OCR lub most nie działa, dokument dostaje status błędu, bez ukrytego przełączenia na Gemini.

## Operacje na VPS

```sh
systemctl status multiplekser-claude-bridge
systemctl restart multiplekser-claude-bridge
journalctl -u multiplekser-claude-bridge -n 40 --no-pager
```

Po aktualizacji serwera jednostka systemd jest w repo jako `ops/multiplekser-claude-bridge.service`. Instalacja: `install -m 644 .../ops/multiplekser-claude-bridge.service /etc/systemd/system/multiplekser-claude-bridge.service && systemctl daemon-reload && systemctl enable --now multiplekser-claude-bridge`.

## Testy

* 5/5 testów panelu `DocumentsPage`.
* 10/10 testów mostu/formatu OCR.
* Host Claude OCR z jedną rzeczywistą stroną hydrauliki: 11 pozycji, 6.27 s.
* Integracja przez działającego workera na 3 stronach: 43 wiersze Claude, 43 odpowiedzi JEV, zero zmian ilości przez JEV, 17.61 s OCR + JEV **od przygotowanych obrazów**.

Nie zmieniano w produkcji żadnych istniejących dokumentów. Test integracyjny przeprowadzono na izolowanych obrazach, bez zapisu do bazy.
