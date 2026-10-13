# Claude Pro – ręczny OCR shadow dla Multipleksera

**Stan 2026-10-13:** Claude Code 2.1.263 jest zainstalowany na VPS. Konto Claude Pro zostało rozpoznane, ale logowanie OAuth wygasło; potrzebne jednorazowe ponowne zalogowanie przez oficjalny przepływ Anthropic. Nie wpisuj sekretów do repozytorium, pliku `.env` ani czatu.

1. Połącz się z VPS przez `ssh greenfield-vps` i przejdź do użytkownika `root` (np. `sudo -i`, jeśli potrzeba).
2. Uruchom `claude auth login --claudeai`, zaloguj się w przeglądarce do swojego Claude Pro i dokończ autoryzację **w terminalu VPS**.
3. Po autoryzacji uruchom `python3 /root/Multiplexer/multiplekser/backend/scripts/run_claude_pro_shadow.py`.

Skrypt uruchamia **oryginalny Claude Code CLI** z `--restricted`, dopuszcza tylko narzędzie `Read`, wyłącza MCP, pisanie plików, polecenia, zapis sesji i klucze API. Model czyta jedną przygotowaną stronę JPG ze ściśle wydzielonego prywatnego katalogu `/var/tmp/multiplekser_claude_shadow/`. Nie zmienia bazy, dokumentów, wydawki ani TXT. Po powodzeniu zapisuje raport `report.json` z uprawnieniami 0600.

Eksportowana strona jest kopią jednej prawdziwej wydawki z hydrauliki. Pliki obrazu/promptu/raportu są prywatne i należy usunąć je po audycie.

**WAŻNE:** Jest to *ręczny benchmark właściciela*, nie funkcja automatyczna Multipleksera ani integracja produktu z usługą Claude. Anthropic zaleca klucze API dla aplikacji zewnętrznych i produktowych integracji. Sam abonament Pro nie daje darmowego API ani gwarancji stałej przepustowości. Nie uruchamiaj aplikacyjnego workera na poświadczeniach subskrypcji bez odrębnej podstawy w warunkach Anthropic.
