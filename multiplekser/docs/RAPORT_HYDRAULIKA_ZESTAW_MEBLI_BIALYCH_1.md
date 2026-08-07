# Raport — reguła łączenia w ZESTAW MEBLI BIAŁYCH (Hydraulika)

Zgłoszenie od użytkownika: 5 pozycji na wydawce Hydraulika ("Szafka stojąca 40/80 cm biała",
"Szafka wisząca 40/80 cm biała", "Szafka okapowa 60 cm biała") zawsze kończy jako "Do
weryfikacji" ("nazwa spoza formularza i bazy dodatkowej"), mimo że w praktyce składają się na
jeden produkt magazynowy — "ZESTAW MEBLI BIAŁYCH", który ma już kod w Optimie i w katalogu.

## Przyczyna

Te 5 nazw jest poprawnie odczytywanych przez OCR (są drukowane na formularzu), ale **nie
istnieją jako osobne produkty w katalogu** (`baza_hydraulika.json`) — sprzedawane są wyłącznie
w komplecie. Matcher słusznie nie znajduje dla nich dopasowania (bo go nie ma) — problem jest
strukturalny, nie błąd dopasowania.

## Ustalona z użytkownikiem reguła (pytania zadane przed implementacją — logika biznesowa)

- **Próg**: min. 3 z 5 pozycji na dokumencie (dowolne 3, w dowolnej kolejności) — mniej niż 3 to
  za mało, zostają nierozpoznane jak dotąd. Pracownik czasem nie dopisuje np. okapowej, mimo że
  fizycznie wchodzi w skład zestawu.
- **Ilość wynikowa: zawsze 1**, niezależnie od tego, ile i które z 5 wystąpiły i jakie miały
  ilości na wydawce — zestaw to zawsze jeden komplet mebli do jednej łazienki/kuchni.
- Wszystkie faktycznie obecne z tych 5 pozycji **znikają** z wyniku, zastąpione jednym wierszem
  "ZESTAW MEBLI BIAŁYCH".

## Co zostało zrobione

- `generator/core_hydraulika.py`: nowa funkcja `_merge_zestaw_mebli_bialych()`, wywoływana jako
  pre-pass na początku `generate_output_hydraulika()` — przed właściwym dopasowywaniem pozycja
  po pozycji. Dopasowuje po znormalizowanej nazwie (bez polskich znaków, bez wielkości liter —
  ten sam wzorzec co `parser/shared.strip_diacritics` używany gdzie indziej w projekcie), więc
  drobne różnice wielkości liter/diakrytyków w odczycie OCR nie psują dopasowania.
  - Zestaw wstawiany jest w miejscu **pierwszego** połączonego elementu — zachowuje zasadę 1)
    z docstringu modułu (kolejność wyniku = kolejność w dokumencie źródłowym).
  - Wstrzyknięty wiersz ma `match_quality="ok"` i `match_kod="ZESTAW MEBLI BIAŁYCH"`, więc
    przechodzi dalej przez ISTNIEJĄCĄ ścieżkę "ręczna korekta ma pierwszeństwo" w głównej
    pętli — zero zmian w reszcie funkcji, w tym w scalaniu duplikatów (jeśli ktoś ręcznie
    dopisze też "ZESTAW MEBLI BIAŁYCH" jako osobną pozycję, ilości się zsumują jak każdy inny
    duplikat kodu).
  - Reguła NIE dotyka Matchera ani widoku weryfikacji dokumentu w UI (te 5 pozycji nadal
    pokazuje się tam osobno, "Do weryfikacji") — łączenie następuje dopiero przy generowaniu
    pliku wyjściowego Optima. Świadomy wybór: użytkownik nadal widzi w tabeli weryfikacji,
    które konkretnie elementy zestawu faktycznie odnotowano na wydawce.

## Testy

- `tests/test_generator_hydraulika.py` (+5 testów): 5/5 elementów łączy się, 3/5 też łączy się
  (z różnymi ilościami — wynik zawsze 1), 2/5 NIE łączy się (zostają osobno jako "BRAK
  DOPASOWANIA"), zachowanie kolejności wyniku, scalanie z ręcznie dopisanym tym samym kodem.
- **Pełna suita: 341 → 346 testów backendu, zero regresji.**

## Co zostało świadomie odłożone

| Temat | Uwaga | Plan |
|---|---|---|
| Wariant "dąb sonoma" (te same 5 typów szafek, inny kolor) | Widoczny na wydawce użytkownika, ale katalog nie ma oczywistego odpowiednika kodu (nie ma "ZESTAW MEBLI DĄB SONOMA") — nie zgadywano | Do ustalenia z użytkownikiem, jeśli/gdy się pojawi na realnym dokumencie |
| Łączenie tylko w Generatorze, nie w widoku weryfikacji dokumentu (UI) | Świadomy wybór — użytkownik nie prosił o zmianę UI, tylko o poprawny wynik eksportu | Rozważyć, jeśli w praktyce myli to podczas weryfikacji przed wygenerowaniem |

## Jak zweryfikować

```bash
cd backend
pytest tests/test_generator_hydraulika.py -v
pytest tests/ -q   # 346 testow, 1 pominiety
```
