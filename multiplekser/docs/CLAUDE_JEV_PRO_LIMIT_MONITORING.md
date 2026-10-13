# Multiplekser — Claude Pro + JEV na VPS, pomiar limitów

Stan: 2026-10-13. Tryb Claude + JEV (Pro, test limitów) działa w panelu Dokumenty, dostępny administratorowi. Gemini pozostaje domyślny dla pozostałych dokumentów.

## Proces

1. Administrator wybiera Claude + JEV, dział Elektryka/Hydraulika i przesyła PDF lub JPG.
2. API zapisuje pliki i dokument w kolejce Claude.
3. Oddzielny Celery worker-claude (concurrency=1) przetwarza dokumenty jeden po drugim. Oddzielna kolejka Gemini (ocr) nadal obsługuje normalny OCR.
4. PDF jest rasteryzowany na JPG. Proces hostowy systemd multiplekser-claude-bridge przekazuje obrazy do oficjalnego Claude Code CLI zalogowanego do subskrypcji Pro.
5. Claude Sonnet Low oddaje tylko nazwy pozycji i dwie kolumny ilości. Matcher i aktywny JEV TypeSafe dobierają kody w katalogu Optimy, stosując reguły elektryki lub hydrauliki.
6. Wynik trafia na standardową kartę dokumentu. Brak odpowiedzi JEV oznacza konieczność ręcznej weryfikacji kodu. Zmiana ilości przez JEV jest wykrywana i cofana.
7. Nie ma automatycznego wysłania ani księgowania TXT w Optimie. Użytkownik musi skontrolować ilości i kody.

## Monitoring Claude Pro

Administrator na stronie Dokumenty widzi status usługi, liczbę poprawnie zakończonych dokumentów z bazy, błędów, czekających wydawek, liczbę żądań i stron w ostatnich 24 godzinach oraz tygodniu, a także średni czas samego OCR.

Endpoint: GET /api/documents/claude-usage (tylko admin).

Usługa hostowa rejestruje anonimizowane statystyki w /var/lib/multiplekser-claude-bridge/usage_history.jsonl. API czyta tylko usage.json i heartbeat.json z montowania tylko do odczytu. Nie zapisujemy kodów OCR, numerów projektów, skanów ani tokenów konta do statystyk.

Monitoring startuje od wdrożenia; starsze zakończone wydawki są doliczone do sumy z bazy dokumentów, ale nie do nowego licznika wywołań hostowych.

Nie przedstawiamy procentu pozostałego limitu, bo Claude CLI nie udostępnia oficjalnego licznika do takiej integracji. Dokładny limit pięciogodzinny i tygodniowy można sprawdzić w Claude: Settings → Usage.

Jeśli Claude zgłosi limit, host blokuje kolejne próby na 10 minut; dokument dostaje komunikat o błędzie. Nie ma ukrytego fallbacku do Gemini ani do płatnego API. Po odnowieniu limitów można przesłać dokument ponownie. Dla stałego abonamentu Pro należy wyłączyć dodatkowe płatne Usage Credits w ustawieniach Claude, jeśli są włączone; OAuth sam w sobie nie jest gwarancją wyłączenia funkcji rozliczeń dodatkowych.

## Prywatność i bezpieczeństwo

- Claude OAuth pozostaje tylko na hoście VPS, nie jest montowany do kontenerów.
- Oficjalne Claude Code CLI uruchamiane jest z ograniczonym zestawem narzędzi (brak narzędzi wykonujących polecenia).
- Dane w prywatnym filesystem IPC z katalogiem głównym root:app 0750; podkatalog jobs app:app 0700. Host nie podąża za symlinkami stron.
- Liczniki dostępne są tylko administratorowi, a pliki w panelu są kontrolowane tokenem użytkownika.
- Połączenie nie wykorzystuje klucza ANTHROPIC_API_KEY.
- Kod JEV jest niezależny od Claude. Utrata limitu Claude nie blokuje kolejki standardowego OCR.

## Serwisowanie na VPS

Status usługi Claude: systemctl status multiplekser-claude-bridge
Logi: journalctl -u multiplekser-claude-bridge -n 40 --no-pager
Statusy kontenerów: docker compose -f docker-compose.prod.yml ps backend worker worker-claude web
Logi oddzielnej kolejki: docker compose -f docker-compose.prod.yml logs --tail 50 worker-claude
Status OAuth: claude auth status

Przy utracie sesji Pro zalogować się na hoście (nie w kontenerze): claude auth login --claudeai.

## Ograniczenia

- 1–6 stron jednego dokumentu (po rasteryzacji do JPG). Do 3 stron na raz podczas odczytu.
- Czas zależy od wydawki, limitów Pro i kolejki. Wcześniejsze wyniki 17–20 sekund pochodziły z określonej próbki, nie są gwarancją SLA.
- OCR ręcznych ilości wymaga weryfikacji z oryginałem, zanim pozycje zostaną zaimportowane do Optimy.
- Status limitu na koncie (dokładna pozostała ilość) nie jest programowo dostępny.
- Brak automatycznych opłat API po stronie Multipleksera, ale płatne credits/extra usage włączone w samym koncie Claude muszą być skontrolowane przez użytkownika.
