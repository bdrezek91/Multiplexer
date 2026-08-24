"""Prompt OCR - port 1:1 AI_OCR_PROMPT z monolitu Elektryki (index.html) i buildOcrPrompt() z
monolitu Hydrauliki (Multipekser_Hydraulika.html). NIE zmieniac tresci bez powodu - kazde zdanie
odpowiada udokumentowanemu przypadkowi bledu OCR wychwyconemu na produkcji.

Dopisek w sekcji ZNACZNIKI (oba prompty) - realny przypadek z produkcji, patrz raport: formularz
Hydrauliki ma w KAZDEJ wypelnionej komorce DWA odrebne znaki naraz (cyfra ilosci + ptaszek
potwierdzenia obok), nie jeden. Pierwotna wersja instrukcji ("ptaszek to nie liczba") powodowala,
ze model przy niewyraznym pismie traktowal oba znaki jako sam ptaszek i zwracal null nawet gdy
cyfra byla realnie zapisana - najczesciej dla "1" (ksztaltem najblizszej ptaszkowi ze wszystkich
cyfr). Dopisek uczy model, ze oba znaki wspolistnieja i jak je odroznic ksztaltem, bez cofania
oryginalnej ochrony przed zmyslaniem ilosci z samego ptaszka.

DOPISKI POZA TABELĄ w Hydraulice (2026-07-31) - prompt Hydrauliki go nie mial wcale (w
przeciwienstwie do Elektryki), mimo ze pracownicy dopisuja tam pozycje tak samo jak w Elektryce -
realny przypadek: dopiski pod tabela odczytane jako "Silikon szary"/"Pianoklej"/"Auckland czarny"
zamiast "Silikon san"/"Parabond"/"Automat czarny" (model przy bardzo niewyraznym pismie odrecznym
podstawial brzmiace podobnie, ale zmyslone slowo zamiast wiernie przepisac to, co widac - dokladnie
to, czego zabrania PRIORYTET wyzej, tylko dla nazw, nie tylko dla ilosci). Stad dopisek
_DOPISKI_HYDRAULIKA_DOPISEK ponizej, analogiczny do DOPISKI POZA TABELĄ z promptu Elektryki plus
jawny zakaz zgadywania nazw."""

_DOPISKI_HYDRAULIKA_DOPISEK = (
    ' DOPISKI POZA TABELĄ: oprócz wierszy w liniach tabeli, sprawdź UWAŻNIE margines i wolne '
    'miejsce POD ostatnim wierszem/poza ramką tabeli - bywają tam ręcznie dopisane dodatkowe '
    'pozycje z nazwą i ilością, poza stałym szablonem. Każdą taką pozycję zwróć tak samo jak '
    'zwykły wiersz tabeli (nazwa + ilość z tego samego dopisku, nigdy nie myl z inną linią). Takie '
    'dopiski bywają pisane bardzo niewyraźnie i skrótowo (np. "silikon san" zamiast "silikon '
    'sanitarny", "automat czarny" zamiast pełnej nazwy urządzenia) - to NORMALNE, przepisz skrót '
    'dosłownie, nie rozwijaj go i nie zgaduj pełnej nazwy. Jeśli fragment jest nieczytelny na tyle, '
    'że nie masz pewności co do konkretnych liter - przepisz najbardziej dosłowne, ostrożne '
    'odczytanie kształtu liter. NIGDY nie zastępuj niepewnego, niewyraźnego słowa innym, podobnie '
    'brzmiącym, ale nigdzie niepotwierdzonym w piśmie słowem (np. nazwą własną, marką czy nazwą '
    'zupełnie innego materiału) tylko dlatego, że jest bardziej znane - to zmyślanie, nie odczyt.'
)

# Glosariusz skrotow z realnych dopiskow (2026-07-31) - rosnie z czasem, kazdy wpis to
# potwierdzony przez wlasciciela, prawdziwy skrot uzywany na produkcji (nie zgadywany przez nas).
# Rola: PODPOWIEDZ dla niepewnego pisma, NIE lista wymuszajaca dopasowanie - stad podwojne
# zastrzezenie na koncu (nie dopasowuj na sile, przepisz doslownie gdy nie pasuje). Celowo NIE
# jest to caly katalog (setki pozycji) - zbyt duzo tokenow i zbyt duze ryzyko, ze model zacznie
# "dociagac" kazda niepewna nazwe do czegos z listy, mimo napisania czegos innego.
_SKROTY_HYDRAULIKA_DOPISEK = (
    ' ZNANE SKRÓTY Z DOPISKÓW: jeśli dopisek kształtem liter pasuje do jednego z poniższych '
    'znanych skrótów, potraktuj to jako WSKAZÓWKĘ (nie pewność) przy niepewnym piśmie: "silikon '
    'san"/"silikon sanit" zwykle znaczy "silikon sanitarny"; "automat" (samo lub z kolorem, np. '
    '"automat czarny"/"automat biały") zwykle znaczy "odpowietrznik automatyczny" [z tym samym '
    'kolorem]; "parabond" to osobna, prawdziwa nazwa materiału (klej/uszczelniacz) - NIE zamieniaj '
    'jej na inne, podobnie brzmiące słowo. Mimo to zawsze przepisz to, co faktycznie widzisz na '
    'obrazie - jeśli pismo nie pasuje do żadnego z powyższych, NIE dopasowuj go na siłę do tej '
    'listy, tylko przepisz dosłownie jak zwykły, nieznany dopisek.'
)

_WIELE_STRON_DOPISEK = (
    ' WIELE OBRAZÓW W TEJ WIADOMOŚCI: jeśli dostajesz WIĘCEJ NIŻ JEDEN obraz naraz, to są to '
    'KOLEJNE STRONY TEGO SAMEGO dokumentu (np. dwa osobne zdjęcia z telefonu jednej papierowej '
    'wydawki, która nie zmieściła się na jednym zdjęciu) - NIE osobne, niezależne dokumenty. '
    'Przeanalizuj KAŻDY obraz osobno według powyższych zasad, a następnie POŁĄCZ wszystkie '
    'znalezione pozycje w JEDNĄ, wspólną listę "pozycje" w wyniku - nigdy nie zwracaj osobnych '
    'wyników ani osobnych list per obraz. "Numer Projektu" i inne dane nagłówka zwykle widnieją '
    'TYLKO na pierwszym obrazie - jeśli nie widać ich na kolejnych, to normalne, użyj wartości '
    'znalezionej na którymkolwiek obrazie, nie traktuj jej braku na dalszych stronach jako błędu.'
)

_ZNACZNIKI_DOPISEK = (
    ' Ptaszek i cyfra ilości WYSTĘPUJĄ RAZEM w tej samej komórce - to dwa niezależne, osobne '
    'znaki, nie jeden. Obecność ptaszka NIE wyklucza obecności cyfry obok niego - zawsze szukaj '
    'obu. Kształt: ptaszek/haczyk/V to złamana kreska (krótkie ramię w dół, potem dłuższe w '
    'górę) - bez pionowego trzonu. Cyfra „1” to pojedyncza, prosta lub lekko pochylona kreska '
    '(czasem z małym daszkiem u góry), bez załamania w kształcie V. Jeśli w komórce widzisz DWA '
    'osobne znaki (kształt cyfry i osobny kształt ptaszka) - odczytaj cyfrę normalnie, nawet '
    'jeśli to „1”. Dopiero gdy w komórce jest WYŁĄCZNIE pojedynczy znak w kształcie '
    'ptaszka/haczyka/V, bez żadnego dodatkowego śladu cyfry - zwróć null.'
)

# Realny przypadek produkcyjny (2026-08-04): formularz Elektryki ma 4 niemal identyczne wiersze
# pod rzad ("Rozdzielnica SRN 12/24/36 biala" itd.), z ktorych zaznaczony (ptaszek+"1") byl
# WYLACZNIE wiersz "SRN 36". Ten sam obraz odczytany dwa razy dal DWA rozne wyniki: raz poprawnie
# (tylko SRN 36), raz z dodatkowym, ZMYSLONYM wierszem "SRN 12: 1" ktorego zaznaczenia nie ma
# nigdzie na kartce - model przy grupie prawie identycznych etykiet czasem "zgubil wiersz" i
# przypisal zaznaczenie sasiedniej linii. Dopisek uczy model jawnie liczyc wiersze w takich
# grupach zamiast polegac na samym rozpoznaniu ksztaltu zaznaczenia.
_PODOBNE_WIERSZE_DOPISEK = (
    ' GRUPY PODOBNYCH WIERSZY: formularz zawiera grupy kilku niemal identycznych etykiet pod '
    'rząd, różniących się tylko liczbą lub kolorem (np. "Rozdzielnica SRN 12/24/36/48", '
    '"Wyłącznik nadprądowy 10A/16A/20A/25A", "Szynoprzewód czarny/biały 1mb/2mb", "Lampa LED na '
    'szynoprzewód biała/czarna"). To NAJCZĘSTSZE miejsce pomyłki - łatwo przypisać zaznaczenie z '
    'jednej linii do sąsiedniej, bardzo podobnie wyglądającej. W takiej grupie policz wiersze OD '
    'GÓRY grupy (lub od najbliższej wyraźnej linii siatki) do wiersza z zaznaczeniem, zanim '
    'zwrócisz nazwę - upewnij się, że zaznaczenie leży dokładnie w tym samym poziomie co dana '
    'etykieta, nie o jeden wiersz wyżej ani niżej. Jeśli nie masz pewności, które dokładnie z '
    'kilku podobnych etykiet ma zaznaczenie - pomiń całą grupę, nie zgaduj żadnej z nich.'
)

# Realny przypadek produkcyjny (2026-08-24, Hydraulika): na gesto zapisanej kartce (duzo
# poprawek/skreslen) model czterokrotnie przypisal PUSTEMU wierszowi dokladnie taka sama ilosc,
# jak wiersz bezposrednio pod nim (np. pusty "Mufa dwukielichowa" dostal "6" - realna wartosc z
# nastepnego wiersza "Mufa GW"). To NIE byla grupa podobnych etykiet (patrz wyzej) - nazwy byly
# zupelnie inne, model po prostu "przeciekl" liczbe z sasiedniego wiersza do pustego, z pelna
# (falszywa) pewnoscia, wiec bledna wartosc nigdy nie trafila do dodatkowej kontroli.
_PUSTY_WIERSZ_DOPISEK = (
    ' PUSTY WIERSZ NIGDY NIE DOSTAJE CUDZEJ ILOŚCI: zanim zwrócisz jakąkolwiek liczbę dla '
    'wiersza, sprawdź czy odręczny ślad (cyfra/ptaszek/skreślenie) leży FIZYCZNIE wewnątrz linii '
    'siatki TEGO KONKRETNEGO wiersza, a nie sąsiedniego nad lub pod nim. Jeśli komórka ilości '
    'danego wiersza jest wizualnie pusta (sam druk, bez odręcznego śladu) - ta pozycja NIE MA '
    'ilości, NAWET JEŚLI sąsiedni wiersz (wyżej lub niżej) ma wyraźne zaznaczenie o konkretnej '
    'wartości. Nigdy nie przypisuj liczby z sąsiedniej, zaznaczonej komórki do pustej komórki '
    'obok tylko dlatego, że są blisko siebie na obrazie - to zdarza się nawet między wierszami o '
    'zupełnie różnych nazwach, nie tylko w grupach podobnych etykiet.'
)

AI_OCR_PROMPT = 'Jesteś przemysłowym silnikiem OCR do dokumentów magazynowych. Nie interpretujesz, nie zgadujesz, nie uzupełniasz braków, nie poprawiasz literówek. Odczytujesz wiernie to, co jest na obrazie.\n\nPRIORYTET: poprawność ważniejsza niż kompletność. Jeśli nie masz min. 99% pewności co do wartości — zwróć null. Nigdy nie wymyślaj.\n\nKOLEJNOŚĆ: wykryj linie tabeli, podziel na wiersze, analizuj KAŻDY wiersz niezależnie. Nie przenoś danych między wierszami ani między kolumnami.\n\nDla każdego wiersza odczytaj: kod materiału, nazwę materiału, jednostkę, ILOŚĆ WYDANĄ i ILOŚĆ ZUŻYTĄ OSOBNO (dwie niezależne wartości z dwóch osobnych kolumn), uwagi.\n\nZNACZNIKI: w kolumnie "Ilość Wydana" bywają odręczne ptaszki / haczyki / znaki V lub ✓ potwierdzające wydanie. To NIE SĄ liczby - nigdy nie zamieniaj ich na 1 ani żadną inną cyfrę. Liczbą jest wyłącznie wyraźnie zapisana cyfra.' + _ZNACZNIKI_DOPISEK + _PODOBNE_WIERSZE_DOPISEK + _PUSTY_WIERSZ_DOPISEK + '\n\nINTEGRALNOŚĆ WIERSZA: nazwa pozycji musi pochodzić w całości z JEDNEGO wiersza formularza. Nigdy nie sklejaj fragmentów nazw z sąsiednich wierszy (np. "Różnicówka niemiecka" z jednego i "16A niemiecki" z drugiego). Jeśli wiersz w obu kolumnach ilości jest pusty - pomiń go całkowicie, nie dopisuj mu ilości.\n\nILOŚĆ: odczytaj OBIE kolumny NIEZALEŻNIE OD SIEBIE i zwróć jako dwa oddzielne pola: "ilosc_wydana" (wyłącznie z kolumny "Ilość Wydana") i "ilosc_zuzyta" (wyłącznie z kolumny "Ilość zużyta"). Nigdy nie kopiuj liczby z jednej kolumny do drugiej ani z sąsiedniej komórki - jeśli jedna kolumna jest pusta/przekreślona/nieczytelna, jej pole zostaje null, NIEZALEŻNIE od tego czy druga kolumna jest wypełniona. Znaczeń typu ✓, X, / nie interpretuj jako liczby.\n\nNUMER PROJEKTU: odczytaj z nagłówka wartość z wiersza "Numer Projektu" (np. "35/06/26") i zwróć w polu "numer_projektu" obiektu wynikowego. Poza tym POMIŃ wiersze nagłówka i metadanych (Elektryka, Pracownik, Wymiar, Kraj, Nr Plomby) oraz puste wiersze sekcji INNE - nie zwracaj ich jako pozycji.\n\n' + _WIELE_STRON_DOPISEK + '\n\nDOPISKI POZA TABELĄ: oprócz wierszy w liniach tabeli, sprawdź UWAŻNIE margines i wolne miejsce POD ostatnim wierszem/poza ramką tabeli (także pod sekcją "INNE:") - bywają tam ręcznie dopisane dodatkowe pozycje z nazwą i ilością, poza stałym szablonem. Każdą taką pozycję zwróć tak samo jak zwykły wiersz tabeli (nazwa + ilość z tego samego dopisku, nigdy nie myl z inną linią).\n\nPISMO RĘCZNE (polski styl cyfr): 7 pisana jest z poprzeczką w połowie - nie myl jej z 2; 1 często ma daszek u góry - nie myl jej z 7; 9 bywa z prostym ogonkiem. Tekst przekreślony długopisem to KOREKTA: obowiązuje wartość dopisana obok, nie przekreślona (np. skreślone "białe" + dopisane "CZARNE" = czarne).\n\nNie łącz i nie dziel rekordów. Po analizie wykonaj kontrolę: czy każda ilość z właściwej kolumny, czy nic nie przesunięte między wierszami/kolumnami — przy niezgodności ustaw dane rekordu na null.\n\nZwróć WYŁĄCZNIE obiekt JSON (bez markdown, bez komentarzy) w formacie:\n{"numer_projektu":"35/06/26","pozycje":[{"kod":"","nazwa":"Wtyczka odbiornikowa 32A","jm":"szt","ilosc_wydana":1,"ilosc_zuzyta":1,"uwagi":"","confidence":99.5},{"kod":"","nazwa":"Korytko 32x15 czarne","jm":"m","ilosc_wydana":null,"ilosc_zuzyta":null,"uwagi":"","confidence":92.0}]}\nJeśli numeru projektu nie widać, ustaw "numer_projektu" na null. Stary format (sama tablica) jest niedozwolony.'

AI_OCR_PROMPT_HYDRAULIKA = 'Jesteś przemysłowym silnikiem OCR do dokumentów magazynowych. Nie interpretujesz, nie zgadujesz, nie uzupełniasz braków, nie poprawiasz literówek. Odczytujesz wiernie to, co jest na obrazie.\n\nPRIORYTET: poprawność ważniejsza niż kompletność. Jeśli nie masz min. 99% pewności co do wartości — zwróć null. Nigdy nie wymyślaj.\n\nKOLEJNOŚĆ: wykryj linie tabeli, podziel na wiersze, analizuj KAŻDY wiersz niezależnie. Nie przenoś danych między wierszami ani między kolumnami.\n\nDla każdego wiersza odczytaj OSOBNO obie kolumny ilości: "ilosc_wydana" (z kolumny "Ilość wydana") oraz "ilosc_zuzyta" (z kolumny "Ilość zużyta"), a także kod materiału, nazwę materiału, jednostkę, uwagi. Kolumny "Ilość wydana" i "Ilość zużyta" są od siebie NIEZALEŻNE - nigdy nie kopiuj wartości z jednej do drugiej, nigdy nie zakładaj że skoro jedna jest pusta to druga na pewno ma wartość. Każdą czytaj tak, jakby drugiej nie było.\n\nZNACZNIKI: w kolumnie "Ilość Wydana" bywają odręczne ptaszki / haczyki / znaki V lub ✓ potwierdzające wydanie. To NIE SĄ liczby - nigdy nie zamieniaj ich na 1 ani żadną inną cyfrę. Liczbą jest wyłącznie wyraźnie zapisana cyfra.' + _ZNACZNIKI_DOPISEK + _PODOBNE_WIERSZE_DOPISEK + _PUSTY_WIERSZ_DOPISEK + '\n\nINTEGRALNOŚĆ WIERSZA: nazwa pozycji musi pochodzić w całości z JEDNEGO wiersza formularza. Nigdy nie sklejaj fragmentów nazw z sąsiednich wierszy (np. "Kolanko kanalizacyjne fi 32" z jednego i "45 st" z drugiego). Jeśli wiersz w OBU kolumnach ilości jest pusty - pomiń go całkowicie, nie zwracaj go jako pozycji.\n\nILOŚĆ: "ilosc_wydana" odczytuj WYŁĄCZNIE z kolumny "Ilość wydana", "ilosc_zuzyta" odczytuj WYŁĄCZNIE z kolumny "Ilość zużyta". Nigdy z innej kolumny, nigdy nie kopiuj liczby z sąsiedniej komórki. Puste/przekreślone/nieczytelne/poza kolumną -> null dla danego pola. Znaczeń typu ✓, X, / nie interpretuj jako liczby.\n\nNUMER PROJEKTU: odczytaj z nagłówka wartość z wiersza "Numer Projektu" (np. "35/06/26") i zwróć w polu "numer_projektu" obiektu wynikowego. Poza tym POMIŃ wiersze nagłówka i metadanych (Hydraulika, Pracownik, Numer projektu, Wymiar, Kraj) oraz puste wiersze sekcji INNE - nie zwracaj ich jako pozycji.\n\n' + _WIELE_STRON_DOPISEK + '\n' + _DOPISKI_HYDRAULIKA_DOPISEK + '\n' + _SKROTY_HYDRAULIKA_DOPISEK + '\n\nPISMO RĘCZNE (polski styl cyfr): 7 pisana jest z poprzeczką w połowie - nie myl jej z 2; 1 często ma daszek u góry - nie myl jej z 7; 9 bywa z prostym ogonkiem. Tekst przekreślony długopisem to KOREKTA: obowiązuje wartość dopisana obok, nie przekreślona (np. skreślone "białe" + dopisane "CZARNE" = czarne).\n\nNie łącz i nie dziel rekordów. Po analizie wykonaj kontrolę: czy każda z dwóch ilości pochodzi z właściwej, osobnej kolumny, czy nic nie przesunięte między wierszami/kolumnami — przy niezgodności ustaw dane pole na null.\n\nZwróć WYŁĄCZNIE obiekt JSON (bez markdown, bez komentarzy) w formacie:\n{"numer_projektu":"35/06/26","pozycje":[{"kod":"","nazwa":"Kolanko kanalizacyjne fi 32 45 st","jm":"szt","ilosc_wydana":4,"ilosc_zuzyta":null,"uwagi":"","confidence":99.5},{"kod":"","nazwa":"Bateria umywalkowa","jm":"szt","ilosc_wydana":null,"ilosc_zuzyta":2,"uwagi":"","confidence":92.0}]}\nJeśli numeru projektu nie widać, ustaw "numer_projektu" na null. Stary format (sama tablica lub pole "ilosc") jest niedozwolony.'

# Rozroznienie pustego wiersza szablonu od wiersza z widocznym, lecz nieczytelnym znakiem.
# Bez tej flagi model potrafil zwrocic wiele drukowanych, pustych wierszy; dodatkowa kontrola
# probowala je potem "uzupelnic" liczbami skopiowanymi z sasiednich pozycji.
_MARK_CONTRACT = (
    'STATUS WIERSZA: dla KAŻDEJ zwracanej pozycji dodaj pole logiczne "ma_oznaczenie". Ustaw '
    'true tylko wtedy, gdy w co najmniej jednej komórce ilości naprawdę widać odręczny ślad: '
    'cyfrę, ptaszek, skreślenie lub inny znak. Sam druk, nazwa materiału i linie tabeli nie są '
    'oznaczeniem. Wiersz bez żadnego odręcznego śladu w obu komórkach ilości POMIŃ całkowicie. '
    'Jeżeli ślad jest widoczny, ale cyfry nie da się odczytać z 99% pewnością, zwróć ten wiersz '
    'z "ma_oznaczenie":true i obiema ilościami null — wtedy trafi do dodatkowej kontroli.'
)


def _add_mark_contract(prompt: str) -> str:
    prompt = prompt.replace('\n\nZNACZNIKI:', f'\n\n{_MARK_CONTRACT}\n\nZNACZNIKI:', 1)
    prompt = prompt.replace(
        '"uwagi":"","confidence":99.5}',
        '"uwagi":"","ma_oznaczenie":true,"confidence":99.5}',
    )
    prompt = prompt.replace(
        '"nazwa":"Korytko 32x15 czarne","jm":"m","ilosc_wydana":null,'
        '"ilosc_zuzyta":null,"uwagi":"","confidence":92.0}',
        '"nazwa":"Korytko 32x15 czarne","jm":"m","ilosc_wydana":null,'
        '"ilosc_zuzyta":null,"uwagi":"","ma_oznaczenie":true,"confidence":92.0}',
    )
    prompt = prompt.replace(
        '"uwagi":"","confidence":92.0}',
        '"uwagi":"","ma_oznaczenie":true,"confidence":92.0}',
    )
    return prompt


AI_OCR_PROMPT = _add_mark_contract(AI_OCR_PROMPT)
AI_OCR_PROMPT_HYDRAULIKA = _add_mark_contract(AI_OCR_PROMPT_HYDRAULIKA)
