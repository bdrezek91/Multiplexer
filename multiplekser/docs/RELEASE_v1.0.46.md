# Multiplekser 1.0.46 — darmowe Gemini, potem Claude

Zmiana dla AUTO z dnia 13.10.2026.

**Kolejność:** Gemini 3.5 Flash Lite (darmowy) → Gemini 3.1 Flash Lite (darmowy) → Gemini 3.6 Flash (darmowy) → Claude Sonnet (awaryjny). Kody produktów nadal wybiera matcher i JEV.

- Wywołania Gemini są sekwencyjne, bez równoległego obciążania darmowego klucza i bez płatnego API.
- Po pierwszej poprawnej klasyfikacji działu pełny OCR preferuje model, który odpowiedział. Jeżeli się nie powiedzie, próbuje pozostałych modeli.
- Timeouty klasyfikacji: 5, 4 i 5 sekund. Wspólny budżet czasu na klasyfikację i pełne OCR Gemini: do 26 sekund.
- Błędy 429, 503 oraz timeouty aktywują dotychczasowe blokady Redis. Próby i wybór modelu są widoczne w przebiegu AI dokumentu.
- Gdy Gemini nie odpowiada poprawnie, Claude Sonnet pozostaje jednorazowym fallbackiem. Automatyczny Opus nie wraca.
- Przyjęcie klasyfikacji wymaga co najmniej 65% pewności.
- Bez zmian reguł bezpiecznego eksportu, hydrauliki, wkrętów i wykluczenia ZAS 127.

Powód: dokument 36c5ac1d-ebab-423b-af08-b495f430df96: jedyny Gemini 3.5 Flash Lite przekroczył 5 s na klasyfikacji i przeszedł do Claude. Kolejne alternatywy ograniczają ryzyko takiego zbędnego przełączenia.
