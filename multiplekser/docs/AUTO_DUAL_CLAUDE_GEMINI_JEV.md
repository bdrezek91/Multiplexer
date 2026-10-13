# Multiplekser AUTO V3 — równoległy Claude, darmowy Gemini i JEV

Wdrożenie: 13 października 2026.

**Wydawka PDF/JPG:** Claude Sonnet Low i darmowy Gemini Flash Lite czytają ten sam skan równolegle w dwóch niezależnych wywołaniach. AUTO porównuje nazwy, numery stron, obie kolumny ilości, dział, numer projektu i pracownika.

- Zgodne dane: żadnych automatycznych zmian.
- Rozbieżne ilości: oznaczenie wiersza do kontroli (obie propozycje w notatce), a dla wybranych pozycji dodatkowy odczyt Opus High.
- Wiersz widoczny tylko u jednego modelu: informacja w przebiegu AI. Wiersze Claude bez potwierdzenia Gemini są oznaczone do kontroli.
- Różny dział, numer projektu lub pracownik: ostrzeżenie, bez cichego nadpisywania.
- Tylko matcher i JEV wybierają kody Optimy. Żaden model nie zmienia ilości automatycznie na podstawie opinii drugiego.
- Gemini wykorzystuje wyłącznie GEMINI_API_KEY_FREE i jeden model gemini-3.5-flash-lite. Nie ma automatycznej płatnej ścieżki w audycie. Jeśli darmowy Gemini przekroczy 17 s lub limit API, Claude + JEV działa bez niego, a przebieg AI wskazuje brak drugiej kontroli.
- Klucz Gemini przekazywany nagłówkiem x-goog-api-key, nie w adresie URL logowanym przez HTTPX.
- Hydraulika: oba silniki odczytują numer projektu i pracownika; NIE SZUKAJĄ numeru plomby. Panel ukrywa pole plomby i dawny alarm dotyczący wyłącznie plomby.
- Elektryka: numer plomby w głównym odczycie Claude działa jak wcześniej.
- Brak automatycznego księgowania; użytkownik sprawdza oznaczone pozycje przed eksportem.

Test jednej prawdziwej strony elektrycznej: Claude 18 pozycji w 9,24 s, Gemini Flash Lite 18 pozycji w 2,98 s, zgodne nazwy i ilości 18/18, cały równoległy odczyt i porównanie 10,38 s. To nie gwarancja wydajności ani bezbłędności na innych dokumentach.

Źródła kodu:
- backend/app/modules/documents/auto_gemini_audit.py — darmowe OCR, porównanie nazw/ilości i nagłówków;
- backend/app/modules/documents/tasks.py — równoległe uruchamianie Claude/Gemini, log przebiegu, kontrola Opus i JEV;
- backend/app/modules/ocr/providers.py — sekret Gemini w nagłówku zamiast w URL;
- backend/app/modules/ocr/prompt.py i ops/claude_bridge_host.py — brak plomby dla hydrauliki;
- frontend/src/pages/DocumentDetailPage.tsx — widoczność ostrzeżeń i metadanych według działu.
