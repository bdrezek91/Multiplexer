# Multiplekser 1.0.49 — korekta błędu Gemini-only

## Dlaczego

Wydawka `20260925114638972.pdf` otrzymała status `error` (2026-10-14 06:27 UTC), mimo że model Gemini 3.1 Flash-Lite poprawnie sklasyfikował dział elektryka. FREE1 i FREE2 3.5 Lite timeoutowały po 4 s i zablokowały **także** możliwość późniejszego pełnego OCR, FREE2 3.6 dostał 429, a full 3.1 Lite FREE1 zużył 9 s. Globalny budżet 26 s wyczerpał się w trakcie próby full 3.1 Lite FREE2. Wynik końcowy: bez odczytanych pozycji, dokument `error`.

## Naprawa bez zmian reguł biznesowych

1. **Timeout oddzielony per etap**: krótkotrwałe timeouty dla `classification` mają własny klucz Redis i nie eliminują tego samego modelu z `full_ocr_hydraulika` czy `full_ocr_elektryka`. Dotychczasowy 429/503 nadal blokuje model we wszystkich etapach (jeden projekt, wspólny limit).
2. **Ograniczone automatyczne ponawianie**: Gemini-only oraz nieudane z powodu limitu/timeoutu API zadania OCR są wznawiane na tym samym UUID po 180 s, następnie po 900 s. Maksymalnie trzy podejścia. **Żadnego Claude, płatnego Gemini ani wysyłania danych do innych usług.**
3. Jeśli żaden model nie odpowie po trzech podejściach, dokument otrzymuje czytelny `error`. Niedostępność Google nie oznacza generowania wirtualnych pozycji ani obchodzenia walidacji. Błędy niejednoznacznej klasyfikacji nie przechodzą przez automatyczny retry.
4. Redis/Celery `ocr` bez dodatkowych workerów. `mark_retry_queued` zachowuje logi pierwszej próby i oryginalny plik, bez utworzenia drugiego dokumentu i bez inkrementacji liczników zakończonych analiz. W razie błędu brokera dokument otrzymuje `error`, nie zawisa w `queued`.
5. Moduły promptów, Hydra/Electrics matcher, JEV, przepisy magazynowe, OCR quantity consensus i PDF image pipeline pozostają **nietknięte**.

## Testy

- `test_gemini_retry_safety_1049.py`: odrębny timeout klasyfikacji, fallback full, opóźnienia 180/900, dokładnie trzy próby, awaria brokera, niejednoznaczny dział, zachowanie wcześniejszych zdarzeń, stan samego UUID.
- `test_gemini_only_uploads.py`: dostosowanie istniejącego testu do automatycznego retry, bez Claude.
- Regresja OCR, oba projekty FREE, weryfikacja ilości, JEV i matcher w izolowanej sieci.
- Obrazy poprzednich kontenerów należy zachować do rollbacku; nie modyfikować Caddyfile, SQL schema ani innych aplikacji na VPS.

## Uwaga operacyjna

Przy wyczerpaniu limitów projektów Google niemożliwe jest zagwarantowanie natychmiastowego odczytu. Ta poprawka sprawia, że nieudana próba nie wymaga od użytkownika ponownego uploadu. Status `queued` oznacza także oczekiwanie na automatyczne ponowienie; etap `gemini_retry` w dzienniku AI podaje planowany czas.
