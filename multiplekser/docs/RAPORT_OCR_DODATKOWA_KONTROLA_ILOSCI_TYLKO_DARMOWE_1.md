# Raport — dodatkowa kontrola ilości bez płatnych modeli

Zgłoszenie od użytkownika: na dokumencie Hydraulika jedna niejasna pozycja ("Szafka okapowa 60 cm
biała", niewyraźny/wyskrobany znak w kolumnie "Ilość wydana") przeszła przez cały łańcuch modeli
w "Dodatkowej kontroli ilości" (`verify_ambiguous_quantities`, `ocr/verify.py`) — 4 darmowe modele
Gemini odmówiły odczytu, Gemini płatny też, dopiero OpenAI gpt-4o (płatny) coś odczytał. Użytkownik
nie chce, żeby ten konkretny krok (w odróżnieniu od głównego odczytu całego dokumentu) sięgał po
płatne modele — koszt płatnego fallbacku dla jednej niejasnej komórki nie jest tego wart, a
pozycja i tak trafiłaby do ręcznej weryfikacji, jeśli żaden darmowy model jej nie odczyta.

## Co zostało zrobione

- `ocr/chain.py`: nowa funkcja `quantity_verification_chain()` — te same 4 darmowe modele Gemini
  co pierwsze 4 kroki `default_ocr_chain()` (3.6 Flash, 3.5 Flash, 3.5 Flash Lite, 3.1 Flash
  Lite), BEZ Gemini płatnego i OpenAI.
- `ocr/verify.py: verify_ambiguous_quantities()` — używa teraz `quantity_verification_chain()`
  zamiast `default_ocr_chain()`. Reszta mechanizmu bez zmian: pozycja, której żaden z 4 darmowych
  modeli nie odczyta, kończy jako "Bez wyniku" (`_publish_no_result`) — tak jak dotąd dla pozycji,
  gdzie nawet płatny fallback by zawiódł.
- **Wspólne dla Elektryki i Hydrauliki** — `dzial` w `verify_ambiguous_quantities()` wybiera tylko
  układ formularza do wycinania wierszy (`verification_image.py`), nie łańcuch modeli, więc ta
  zmiana obejmuje automatycznie oba działy bez duplikacji.
- Główny odczyt całego dokumentu (`default_ocr_chain()`, pipeline OCR) i klasyfikacja działu
  (`classify_ocr_chain()`) — bez zmian, nadal mają płatny fallback (tam koszt jest proporcjonalny
  do korzyści: cały dokument, nie jedna komórka).

## Testy

- `tests/test_ocr_chain.py` (+1 test): `quantity_verification_chain()` ma dokładnie 4 kroki,
  wszystkie Gemini na kluczu darmowym.
- `tests/test_ocr_verify.py`: 3 istniejące testy przełączone na monkeypatch nowej funkcji
  (`quantity_verification_chain` zamiast `default_ocr_chain`) — zero zmian w asercjach.
- **Pełna suita: 346 → 348 testów backendu, zero regresji.**

## Jak zweryfikować

```bash
cd backend
pytest tests/test_ocr_chain.py tests/test_ocr_verify.py -v
pytest tests/ -q   # 348 testow, 1 pominiety
```
