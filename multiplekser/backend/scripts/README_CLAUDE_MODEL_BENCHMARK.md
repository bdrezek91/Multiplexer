# Multiplekser — benchmark Claude OCR na wydawce hydraulicznej (2026-10-13)

## Cel i zasady

Porównanie odczytu tego samego dokumentu 3-stronicowego (projekt 127/07), wyłącznie w shadow.
Oryginalny Claude Code CLI 2.1.263, logowanie właściciela do **Claude Pro** (`authMethod=claude.ai`), bez Anthropic API key.
Modele testowane z `--print --restricted --strict-mcp-config --disable-slash-commands --tools Read --no-session-persistence` i `--effort` low/medium/high.
Żadne wywołanie nie modyfikowało receptur, pozycji, bazy, TXT ani dokumentów produkcyjnych.

Raporty każdego modelu i częściowo ręcznie poprawiona referencja są wyłącznie na VPS:
`/var/tmp/multiplekser_claude_shadow/bench/` (uprawnienia 0600/0700). Nie commitować tych raportów ani obrazów.

## Strona 2: różne modele / intensywność

| Wariant | Odpowiedź | Nazwy pasujące do wyniku prod. | Zgodne pary ilości przy pasujących nazwach | Czas |
|---|---:|---:|---:|---:|
| Haiku Low | 21 poz. | 20 | 7 | 122.3 s |
| Sonnet Low (starsza próba) | 21 poz. | 20 | 18 | 21.8 s |
| Sonnet Medium | 21 poz. | 20 | 19 | 56.5 s |
| Sonnet High | 21 poz. | 20 | 17 | 74.4 s |
| Opus Low | 21 poz. | 20 | 19 | 26.8 s |
| **Opus Medium** | **21 poz.** | **20** | **20** | **40.9 s** |

W tej tabeli brakująca nazwa wynika z **błędu produkcyjnego wzorca**: Gemini przypisało ilość do `Trójnik kanalizacyjny fi 40 90 st`, podczas gdy na oryginalnym obrazie zaznaczony jest `fi 40 45 st`. Odczyt Claude dla tego wiersza jest poprawny. Tabela nie jest rankingiem na niezależnym GOLD.

Alias CLI Haiku rozwiązał się do `claude-haiku-4-5-20251001`, Sonnet do `claude-sonnet-5`, Opus do `claude-opus-5`. Wewnętrzny routing CLI może używać także Haiku pomocniczo. Wcześniejszy Sonnet Low nie miał zapisanego rozstrzygniętego model ID.

## Pełna trzystronicowa wydawka, częściowo poprawiona referencja

Referencja = 43 pozycje z wyniku produkcyjnego z czterema ręcznie sprawdzonymi poprawkami:
1. `Kolanko ścienne GW` — odręczny zapis 1/1, nie 4/4.
2. `Kompakt WC` — odręczny zapis 1/1, nie 4/4.
3. `Listwa boczna aluminiowa` — odręczny zapis 1/1, nie 4/4.
4. `Trójnik kanalizacyjny fi 40 45 st` — oznaczony wiersz 45°, nie pusty 90°.

Pozycje te zweryfikowano wizualnie z JPG pierwszej/drugiej strony. Pozostałych pozycji nie zweryfikowano niezależnie jedna po drugiej — **to nie jest pełny GOLD**.

| Wariant | Pozycji | Zgodnych nazw | Zgodne dwie ilości | Czas wszystkich stron |
|---|---:|---:|---:|---:|
| Sonnet Low | 43 | 43/43 | 40/43 | 69.3 s |
| Opus Medium | 43 | 43/43 | 42/43 | 83.7 s |
| **Opus High dla strony 1 + Medium dla stron 2–3** | **43** | **43/43** | **43/43** | **88.3 s** |

`Końcówka beżowa`: Sonnet Low daje 2/3, Opus Medium daje 2/null, Opus High daje prawidłowe 2/2 na obrazie. Nie należy traktować wyższej intensywności jako gwarancji dokładności; Sonnet High na stronie 2 wypadł słabiej niż Medium.

## Ocena i dalsze działania

Najlepszy dotychczas wariant dla tego dokumentu: **Opus High (strona 1) + Opus Medium (strony 2/3)**.
NIE WŁĄCZAĆ PRODUKCYJNIE po jednym dokumencie. Zweryfikować ręcznie kolejne 10–20 wydawek (elektryka + hydraulika), szczególnie wartości ręczne, skreślenia, znaki 1/V/4, i prowadzić niezależny GOLD z oryginalnych obrazów.

Sprawdzić, czy quota Claude Pro (okno 5-godzinne oraz tygodniowe, wspólne z Claude) wystarczy na ok. 150 wydawek miesięcznie. Opus zużywa zwykle więcej limitu niż Sonnet.
Oficjalne zasady: https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan

Uruchamianie testu pojedynczej strony:
`python3 /root/Multiplexer/multiplekser/backend/scripts/benchmark_claude_models.py --model opus --effort medium --page 2`

Skrypt odmawia ponownego wywołania tego samego wariantu, jeżeli raport już istnieje. Porównania:
`python3 /root/Multiplexer/multiplekser/backend/scripts/evaluate_claude_model_bench.py`
`python3 /root/Multiplexer/multiplekser/backend/scripts/evaluate_claude_partially_reviewed.py`

**Wszystkie testy są ręczne**. Nie dodano CRON, automatycznych zadań Celery ani kluczy.
