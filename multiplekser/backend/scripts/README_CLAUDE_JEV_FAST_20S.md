# Multiplekser — Claude + JEV: wariant szybki (~20 sekund)

## Wynik testów 2026-10-13

**Potwierdzony działający prototyp SHADOW** na jednej 3-stronicowej wydawce hydraulicznej (43 zaznaczone pozycje).

| Wariant | OCR 3 stron + JEV, rzeczywisty wall-clock | Odpowiedzi JEV | Dokładność względem częściowo ręcznie poprawionej referencji |
|---|---:|---:|---:|
| Sonnet 5 Low + streaming JEV, test pierwszy | **17,158 s** | 43/43 | 42/43 |
| Sonnet 5 Low + streaming JEV, test powtórny | **19,204 s** | 43/43 | 43/43 |
| Opus High str. 1 + Opus Medium str. 2 + Sonnet Low str. 3 | 31,839 s | 44/44 | nieprzyjęte: model dodał 1 wiersz |

Wyniki jakości: 43 pozycje produkcyjnego OCR z **6 ręcznie zweryfikowanymi korektami** na oryginalnym obrazie:
- Kolanko ścienne GW: 1/1 (Gemini 4/4);
- Kompakt WC: 1/1 (Gemini 4/4);
- Listwa boczna aluminiowa: 1/1 (Gemini 4/4);
- Trójnik kanalizacyjny fi 40 45 st, nie pusty wiersz 90 st;
- Rura fi 32 30 cm: 2/1 (Gemini 2/2);
- Trójnik PP 20: 4/5 (Gemini 4/4).

**37 pozostałych pozycji nie zostało niezależnie ręcznie zweryfikowanych.** 43/43 to zgodność z **częściowo ręcznie poprawioną referencją**, NIE pełnym GOLD.

### Jak działa przyspieszenie

1. Użytkownik autoryzował oficjalny Claude Code CLI do Claude Pro; nie używamy płatnego API.
2. Zamiast narzędzia `Read`, JPEG jest osadzany jako obraz w wiadomości `--input-format stream-json`. Narzędzia Claude wyłączone (`--tools ""`, `--restricted`, `--strict-mcp-config`).
3. Trzy procesy Claude Sonnet Low pracują równolegle, każdy czyta jedną stronę.
4. Claude zwraca minimalny JSON: `{"p":[["nazwa",wydana,zuzyta],...]}` (bez kodu/magazynu).
5. Proces JEV w istniejącym kontenerze worker jest **prewarmed przed startem zegara**: katalog z bazy wczytany, gotowy kanał stdin/stdout. Każda ukończona strona natychmiast trafia do osobnego wątku JEV, jeszcze gdy kolejne strony są przetwarzane przez Claude.
6. JEV/TypeSafe wybiera kody, a działające w Multiplekserze reguły zabezpieczają aktualnie poprawne dopasowania i atrybuty hydrauliki.
7. Asercja broni wszystkich ilości przed zmianą przez JEV. Test SHADOW tylko raportuje — nie generuje/wysyła TXT i nie dotyka DB.

### Ograniczenia (WAŻNE)

- Czasy **17,158 i 19,204 s mierzone od gotowości już uruchomionego procesu JEV i gotowych JPG**, nie od uploadu surowego PDF. Nie obejmują pobierania załączników ani rasteryzacji PDF, zapisu danych, renderowania UI, generowania TXT.
- To tylko **dwie próby na jednym dokumencie**; czas Claude na zewnętrznym serwisie ma zmienną latencję. Nie gwarantujemy p95/p99 <= 20 s i nie włączamy limitu jako stałego SLA.
- W jednym odczycie Sonnet miał 1 nieprawidłową parę ilości; nie wolno automatycznie eksportować bez dalszej walidacji.
- Claude Pro ma limity współdzielone z Claude Code; przy ~150 wydawkach/mies. potrzebne monitorowanie quota.
- Związanie wersji ze stałym projektem/obrazami testowymi służy wyłącznie benchmarkowi, **nie jest gotową funkcją do przyjmowania nowych dokumentów**.
- Jeżeli brak odpowiedzi JEV lub model wpisze nieczytelne cyfry, system powinien zatrzymać eksport i poprosić o kontrolę, nigdy zgadywać.
- Zabezpieczenia: brak kluczy w repo, obrazy i raporty tylko prywatnie w `/var/tmp/multiplekser_claude_shadow/speed/`.

### Uruchamianie benchmarku

```sh
# Na VPS: w trybie SHADOW; wznowi i wykona NOWE wywołania, zużywa limit Pro
python3 /root/Multiplexer/multiplekser/backend/scripts/benchmark_claude_jev_fast.py fast

# Ocena jakości na częściowo poprawionym wzorcu
python3 /root/Multiplexer/multiplekser/backend/scripts/evaluate_claude_speed.py
```

Wymaga uprzedniego jednorazowego skopiowania do działającego workera pliku
`jev_stream_shadow.py` jako `/tmp/jev_stream_shadow.py`, praw `644` i działającego JEV w trybie `active`.
Wariant `mixed` jest dostępny porównawczo, ale **nie spełnił wymogu 20 s**.

### Następny etap przed użyciem produkcyjnym

- Osobna zawsze gotowa kolejka/worker JEV bez cold-start.
- Ingest PDF na VPS z przygotowaniem obrazów przy uploadzie; zmierzyć pełny upload→TXT.
- Benchmark 20–50 rzeczywistych wydawek (elektryka/hydraulika), ręcznie zatwierdzony GOLD, rozkład p50/p95, limit Pro.
- Mechanizm fail-closed dla niepewnych ilości i błędnych nazw/wierszy.
- Dopiero po zatwierdzeniu wyników produkcyjne przełączanie OCR z Gemini na Claude.
