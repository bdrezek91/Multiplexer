# Claude Pro – ręczny OCR shadow dla Multipleksera

**Stan 2026-10-13:** Claude Code 2.1.263 jest zainstalowany na VPS, OAuth właściciela odnowiony, `claude auth status` potwierdza Claude Pro. Przeprowadzono trzy udane odczyty jednej trzystronicowej wydawki: 11 + 21 + 11 = 43 wiersze. Porównanie do 43 wierszy wyniku produkcyjnego: 42 identyczne nazwy, 36 zgodnych par ilości (przy dopasowanych nazwach), 6 par różnych; jedna nazwa różni się kątem trójnika (45 vs 90 stopni). Nie wpisuj sekretów do repozytorium, pliku `.env` ani czatu.

1. Połącz się z VPS przez `ssh greenfield-vps` i przejdź do użytkownika `root` (np. `sudo -i`, jeśli potrzeba).
2. Uruchom `claude auth login --claudeai`, zaloguj się w przeglądarce do swojego Claude Pro i dokończ autoryzację **w terminalu VPS**.
3. Po autoryzacji przetestuj dowolną przygotowaną stronę: `python3 /root/Multiplexer/multiplekser/backend/scripts/run_claude_pro_shadow.py --page 1` (albo `--page 2` lub `--page 3`). Wyniki stron 2 i 3 zapisują się do `report_page2.json` i `report_page3.json`.

Skrypt uruchamia **oryginalny Claude Code CLI** z `--restricted`, dopuszcza tylko narzędzie `Read`, wyłącza MCP, pisanie plików, polecenia, zapis sesji i klucze API. Model czyta wskazaną jedną stronę JPG z prywatnego katalogu `/var/tmp/multiplekser_claude_shadow/`. Nie zmienia bazy, dokumentów, wydawki ani TXT. Po powodzeniu zapisuje raport dla wybranej strony z uprawnieniami 0600. Zestawienie całej wydawki jest w `comparison_summary.json` w tym samym katalogu.

Eksportowana strona jest kopią jednej prawdziwej wydawki z hydrauliki. Pliki obrazu/promptu/raportu są prywatne i należy usunąć je po audycie.

**WAŻNE:** Jest to *ręczny benchmark właściciela*, nie automatyczny OCR produkcyjny. Oficjalne wsparcie Anthropic (aktualizacja 07.10.2026) potwierdza możliwość korzystania z `claude -p`, Claude Agent SDK i aplikacji zewnętrznych w ramach limitów abonamentowych: https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan . Claude Pro podlega pięciogodzinnemu i tygodniowemu limitowi współdzielonemu z Claude; nie udostępnia nielimitowanego ani osobnego darmowego API. Potrzebna walidacja ilości na niezależnym zestawie GOLD przed przestawieniem OCR.
