# Multiplekser 1.0.50 — poprawka kolejności Gemini

## Regresja 2026-10-14

Na dokumencie `20261014141551152.pdf` (identyfikator pierwotnego zgłoszenia `e64f2f70…`) router poprawnie sklasyfikował elektrykę przez Gemini 3.5 Flash-Lite w 1.25 s, lecz pełny OCR skierował najpierw na Gemini 3.6 Flash FREE1. Ten model zwrócił 503 dopiero po 12.326 s, po czym system zaczął analogiczną próbę FREE2 i wyczerpał wspólny budżet 26 s; dokument `queued` do ponowienia za 3 minuty. Ten **sam PDF, identyczny SHA-256**, użytkownik ponownie przesłał jako `64940fc7…`; w drugim podejściu Gemini 3.5 Flash-Lite wykonał pełny OCR w 3.93 s, 16 pozycji, cały dokument 16.02 s. Na 12 zakończonych w ostatnich godzinach dokumentach elektryki 3.5 Flash-Lite wykonał pełny OCR w 3.93–8.10 s.

## Poprawka

- **Główna zmiana tylko w routerze AUTO**: pełny OCR priorytetyzuje Gemini 3.5 Flash-Lite (FREE1 i FREE2), a 3.6 Flash i 3.1 Flash-Lite zostają awaryjnymi rodzinami modeli. Niezależne cooldowny i wyłanianie szybszego konta wewnątrz tej samej rodziny pozostają zachowane.
- Klasyfikacja nadal używa historycznego łańcucha 3.5 → 3.6 → 3.1. Pozostawiono timeouty, ogólny limit 26 s i mechanizm opóźnionego retry (jako awarię całego Gemini, nie zamiennik właściwej kolejności).
- **Bez zmian**: prompty OCR, walidacja schematów, pełna kontrola ilości, JEV/TypeSafe, zasady matchera, aliasy, magazyny, wykluczenia, PDF, uwierzytelnianie i frontend.
- Dodano regresję jednostkową symulującą 503 dla 3.6 oraz sukces 3.5 (FREE1); drugą, gdy FREE1 ma 429, FREE2 musi zostać wybrany bez uruchamiania 3.6 lub paid.

## Kontrola jakości

To zmiana polityki routingu i nie gwarantuje zgodności nowych OCR z niezależnym GOLD ani pełnego czasu <20 s dla wszystkich PDF. Nie przeprowadzaj równoległych niekontrolowanych testów API na wyczerpanych kluczach. Rollback: worker/backend z wydania 1.0.49 są zachowane jako obrazy Docker.
