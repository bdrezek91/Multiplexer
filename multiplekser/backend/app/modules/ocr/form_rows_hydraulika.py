"""FORM_ROWS + ADDITIONAL_ROWS + snap_to_known_item_hydraulika() - port 1:1 z monolitu
Multipekser_Hydraulika.html (sekcja "SIATKA KONTROLNA: STALY SZABLON FORMULARZA Hydraulika" /
snapToKnownItem()).

W przeciwienstwie do Elektryki (jeden FORM_ROWS), Hydraulika ma DWA poziomy dopasowania -
swiadoma decyzja z oryginalnego monolitu (nie do "uproszczenia"):
  1) FORM_ROWS - staly szablon formularza pracownika (145 pozycji - "Rura fi 32 100 cm"
     dopisana pozniej, patrz docs/RAPORT_OCR_NIEZAWODNOSC_2.md: prawdziwy, drukowany wiersz
     formularza pominiety przy pierwotnym porcie, potwierdzone bezposrednio przez wlasciciela
     - ten sam realny material co "RURA FI 32 100 CM" dodane do katalogu Optima wczesniej).
  2) ADDITIONAL_ROWS - baza pomocnicza "INNE/DODATKOWE" (114 pozycji): istnieja w Optimie,
     pracownik moze je odrecznie dopisac, ale NIE sa czescia stalego formularza.

Progi (identyczne jak Elektryka):
  >= 0.95        -> zgodne, uzywamy nazwy wzorcowej po cichu (status "exact")
  0.70-0.95      -> literowka/przekrecona cyfra - poprawiamy, oznaczamy do weryfikacji
                    (status "fixed" z FORM_ROWS, "additional" z ADDITIONAL_ROWS)
  < 0.70 (oba)   -> nazwa spoza obu list - NIE wchodzi automatycznie, reczna decyzja (status "off")

UWAGA: w oryginalnym monolicie snapToKnownItem() NIE ma odpowiednika Elektryki
reconcile_form_row() (zachowania cyfr/slow atrybutowych przy statusie "fixed") - to
NIE przeoczenie tego portu, tylko wierne odzwierciedlenie zrodla (Hydraulika nigdy nie miala
tej poprawki, bo zostala odkryta i naprawiona TYLKO w Elektryce, patrz form_rows.py)."""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.parser.shared import bigrams, dice_coeff, strip_diacritics
import re

FORM_ROWS: list[str] = [
    'Bateria umywalkowa',
    'Blat do szafki czarnej 60 cm Premium',
    'Blat kuchenny 1200x600',
    'Blat kuchenny 1250x600',
    'Blat kuchenny 825x600',
    'Bojler 50 L',
    'Bojler 80 L',
    'Czwórnik 110x50 90 st',
    'Czwórnik 16x16x16x16 PEX',
    'Czwórnik fi 110/110/50/90 st',
    'Drzwiczki rewizyjne czarne',
    'Grzejnik łazienkowy 40x70 biały',
    'Grzejnik łazienkowy 40x70 czarny',
    'Kabina prysznicowa 80 cm',
    'Kabina prysznicowa 80 cm czarna',
    'Kabina prysznicowa 90 cm',
    'Kabina prysznicowa 90 cm czarna',
    'Kabina prysznicowa 90 cm niski brodzik',
    'Kolanko fi 110 30 st',
    'Kolanko fi 110 45 st',
    'Kolanko fi 110 67 st',
    'Kolanko fi 110 90 st',
    'Kolanko fi 20 45 st',
    'Kolanko kanalizacyjne fi 32 15 st',
    'Kolanko kanalizacyjne fi 32 30 st',
    'Kolanko kanalizacyjne fi 32 45 st',
    'Kolanko kanalizacyjne fi 32 67 st',
    'Kolanko kanalizacyjne fi 32 90 st',
    'Kolanko kanalizacyjne fi 40 15 st',
    'Kolanko kanalizacyjne fi 40 30 st',
    'Kolanko kanalizacyjne fi 40 45 st',
    'Kolanko kanalizacyjne fi 40 67 st',
    'Kolanko kanalizacyjne fi 40 90 st',
    'Kolanko kanalizacyjne fi 50 15 st',
    'Kolanko kanalizacyjne fi 50 30 st',
    'Kolanko kanalizacyjne fi 50 45 st',
    'Kolanko kanalizacyjne fi 50 67 st.',
    'Kolanko kanalizacyjne fi 50 90 st',
    'Kolanko PP fi 20 90 st',
    'Kolanko redukcyjne 50x32',
    'Kolanko ścienne GW',
    'Kolanko wieszakowe GW 16x1/2" PEX',
    'Kompakt WC',
    'Końcówka beżowa',
    'Korek do umywalki nablatowej czarny',
    'Korek zaślepiający Fi 32',
    'Korek zaślepiający Fi 40',
    'Korek zaślepiający Fi 50',
    'Listwa boczna aluminiowa',
    'Lodówka pod zabudowę',
    'Lustro ścienne okrągłe',
    'Łącznik kolankowy dwustronny PEX',
    'Łącznik kolankowy GW 16x1/2" PEX',
    'Łącznik kolankowy GZ 16x1/2" PEX',
    'Łącznik prosty GW 16x1/2" PEX',
    'Mijanka PP fi 20',
    'Mufa dwukielichowa',
    'Mufa GW',
    'Mufa GZ',
    'Nakrętka M12',
    'Narożnik wewnętrzny beżowy',
    'Narożnik zewnętrzny beżowy',
    'Odpowietrznik automatyczny 1/2” biały',
    'Odpowietrznik automatyczny 1/2” czarny',
    'Okładzina ścienna 30x60 kamień',
    'Pisuar',
    'Płyta indukcyjna dwa pola',
    'Podgrzewacz nadumywalkowy 10 L',
    'Podgrzewacz podumywalkowy 10 L',
    'Podkładka M12',
    'Pręt 12x1000',
    'Przyblatówka sonoma',
    'Redukcja kanalizacyjna fi 40x32',
    'Redukcja kanalizacyjna fi 50x32',
    'Redukcja kanalizacyjna fi 50x40',
    'Rozeta 110',
    'Rozeta 50',
    'Rura fi 30 100 cm',
    'Rura fi 32 30 cm',
    'Rura fi 32 50 cm',
    'Rura fi 32 100 cm',
    'Rura fi 40 100 cm',
    'Rura fi 40 30 cm',
    'Rura fi 40 50 cm',
    'Rura fi 50 100 cm',
    'Rura fi 50 30 cm',
    'Rura fi 50 50 cm',
    'Rura kanalizacyjna 110x2,7x315',
    'Rura pex fi 16',
    'Rura PP fi 20',
    'Syfon do umywalki nablatowej niski',
    'Syfon prysznicowy',
    'Syfon umywalkowy',
    'Szafka umywalkowa 60cm czarna premium',
    'Szafka z umywalką 50 cm',
    'Szyna do montażu szafek',
    'Śruba do łączenia szafek',
    'Śrubunek do wodomierzy',
    'Śruby montażowe',
    'Trójnik 16x16x16 PEX',
    'Trójnik kanalizacyjny 100x50 90 st',
    'Trójnik kanalizacyjny fi 32 45 st',
    'Trójnik kanalizacyjny fi 32 67 st',
    'Trójnik kanalizacyjny fi 40 45 st',
    'Trójnik kanalizacyjny fi 40 90 st',
    'Trójnik kanalizacyjny fi 50 45 st',
    'Trójnik kanalizacyjny fi 50 90 st',
    'Trójnik PP 20',
    'Uchwyt do rur fi 16 (pex)',
    'Uchwyt do rur fi 32',
    'Uchwyt do rur fi 40',
    'Uchwyt do rur fi 50',
    'Uchwyt rur podwójny fi 20',
    'Uchwyt rur pojedynczy fi 20',
    'Umywalka nablatowa premium',
    'Wąż 1/2 x 1/2 120 cm z kolankiem',
    'Wąż 1/2 x 1/2 40 cm z kolankiem',
    'Wąż 1/2x1/2 cala 30 cm',
    'Wąż 1/2x1/2 cala 40 cm',
    'Wąż 1/2x3/8 cala 40 cm',
    'Wąż 3/8x3/8 cala 30 cm',
    'Wąż 3/8x3/8 cala 40 cm',
    'Zaślepka fi 10 antracyt',
    'Zaślepka fi 13 antracyt',
    'Zaślepka fi 13 biała',
    'Zaślepka fi 17 antracyt',
    'Zaślepka fi 19 antracyt',
    'Zaślepka fi 19 biała',
    'Zawór  kątowy 1/2x3/4',
    'Zawór czasowy do pisuaru',
    'Zawór czerpalny 1/2',
    'Zawór kątowy 1/2x1/2',
    'Zawór kątowy 1/2x3/8',
    'Zawór kulowy 1/2 cala',
    'Zawór kulowy DN15 PN16 ze śrubunkiem',
    'Zestaw geberit WC',
    'Zestaw mebli białych',
    'Zestaw mebli premium',
    'Zestaw mebli premium z szufladą',
    'Zlew kuchenny + bateria + syfon + koszyczek czarny',
    'Złącze harmonijkowe WC',
    'Złączka skręcana 16x1/2" GW PEX',
    'Złączka skręcana 16x1/2" GZ PEX',
    'Złączka skręcana 16x16 PEX',
    'Złączka zaciskowa  PP 20x1/2',
]

ADDITIONAL_ROWS: list[str] = [
    'Bateria prysznicowa',
    'Bateria umywalkowa czarna',
    'Bateria zlewozmywakowa czarna',
    'Blat kuchenny 1550x600',
    'Blat kuchenny Lancelot meble Premium',
    'Drzwiczki rewizyjne 30/30 białe',
    'Grzejnik 1000W',
    'Grzejnik 2000W',
    'Grzejnik 2000W (30/06/2026)',
    'Kabina prysznicowa (105/04/2026)',
    'Kolano ścienne fi 20 GW',
    'Kompakt WC (Deante)',
    'Komplet śrub do mocowania kompaktu',
    'Korek zaślepiający chrom 1/2 "',
    'Kran chromowany 1/2x3/4',
    'Kratka wentylacyjna + okapnik (50-57/07/2025)',
    'Kratka wentylacyjna 140x140 biała',
    'Kratka wentylacyjna 140x140 czarna',
    'Kratka wentylacyjna 140x140 grafit',
    'Kratka wentylacyjna żaluzja biała',
    'Narożnik wewnętrzny srebrny',
    'Odpływ podłogowy 55-57/04/2026',
    'Osłona went. 14x14 czarne',
    'PODGRZEWACZ PRZEPŁYWOWY 21KW (97/01/2026)',
    'Przyblatówka srebrna',
    'Rozeta 130 stalowa',
    'Rura wodna niebieska 32x3,0',
    'Syfon zlewozmywakowy',
    'Szafka z umywalką 60 cm (97/01/2026)',
    'Szczotka do WC czarna',
    'Uchwyt na papier czarny',
    'Uchwyt rur pojedyńczy fi 20 PP',
    'Umywalka 50cm prostokątna',
    'Umywalka nablatowa',
    'Wodomierz na zimną wodę',
    'wylot wentylacyjny z okapem 125 grafit',
    'Zestaw geberit WC (Deante)',
    'Zlew kuchenny + bateria + syfon (Deante)',
    'Zlew kuchenny czarny + bateria + koszyczek + syfon',
    'Bateria umywalkowa (Deante)',
    'Bateria zlewozmywakowa',
    'Blat kuchenny 1400x600',
    'Blat kuchenny 1450x600',
    'Blat kuchenny 1650x600',
    'Blat kuchenny 1700x600',
    'Blat kuchenny 1750x600',
    'Blat kuchenny 1800x600',
    'Bojler 200 L',
    'Bojler 30 L',
    'Elektryczny ogrzewacz wody',
    'Grzejnik 1500W',
    'Grzejnik 500W',
    'Kabina prysznicowa 80 cm niski brodzik',
    'Kolanko 3/4',
    'Kolanko fi 110 15 st',
    'Kolanko skręcane GW',
    'Kompakt WC premium (Deante)',
    'Korek czarny 1/2',
    'Korek zaślepiający 3/8 " chrom',
    'Końcówka srebrna',
    'Kratka wentylacyjna 25x25',
    'Kratka wentylacyjna czarna',
    'Kratka wentylacyjna żaluzja grafit',
    'Kurek kątowy 1/2x3/4',
    'Kątownik Alu do okładziny ściennej',
    'Listwa przyszybowa biała',
    'Miska do stelaża WC',
    'mufa do podgrzewacza 21 KW',
    'Nypel 1/2',
    'Odpowietrznik automatyczny 1/2” Mosiądz',
    'Ogrzewacz przeciwmrozowy grzejnik 400W',
    'Pisuar z zaworem',
    'Pisuar z zaworem i syfonem',
    'Podgrzewacz nadumywalkowy 5 L',
    'Podgrzewacz podumywalkowy 5 L',
    'Redukcja  100/50',
    'Redukcja 1/2',
    'Rura 16x2',
    'Rura 50 100cm',
    'Rura fi 40 25 cm',
    'Rura fi 50 200 cm',
    'Rura kanalizacyjna 110x2,7 0,5m',
    'Rura kanalizacyjna 110x2,7 1m',
    'Rura kanalizacyjna 50x1,8 1m',
    'Rura Kanalizacyjna wew. 110x2,7 2M',
    'Rura karbowana arot  niebieska 40/32',
    'Stelaż podtynkowy WC',
    'Syfon do pisuaru',
    'Szafka 50 cm prostokątna',
    'Szafka z umywalką 45 cm',
    'Szafka z umywalką 50 cm czarna',
    'Szafka z umywalką 60 cm czarna',
    'Trójnik kanalizacyjny fi 50 67 st',
    'Trójnik zaciskowy czarny 32 PE',
    'Uchwyt rur pojedyńczy fi 34',
    'uszczelka węża',
    'Wąż 1/2x1/2 cala 100 cm',
    'Wąż 1/2x1/2 cala 20 cm',
    'Wąż 1/2x3/8 cala 30 cm',
    'Zawór pisuarowy ferro',
    'Zaślepka fi 17 biała',
    'Zestaw hydrauliczny (hala stolarki)',
    'Zestaw hydrauliki do hali 72',
    'Zestaw przyłączeniowy geberit',
    'Zestaw wentylacyjny',
    'Zestaw wkrętów do hydrauliki',
    'Zlew kuchenny z syfonem',
    'Zlew kuchenny z syfonem granitowy',
    'Złącze harmonijkowe WC wzmocnione',
    'Złącze skręcane GW',
    'Złączka zaciskowa 32x1 GW - PE',
    'Złączka zaciskowa 32x1" GZ PE',
    'Łącznik H do pliśni biały',
    'Łącznik prosty GZ 16x1/2" PEX',
]


def _normalize_key(name: str) -> str:
    stripped = strip_diacritics((name or "").lower())
    cleaned = re.sub(r"[^a-z0-9 ]", " ", stripped)
    return re.sub(r"\s+", " ", cleaned).strip()


_FORM_PARSED = [
    {"name": n, "key": _normalize_key(n), "bg": bigrams(_normalize_key(n))}
    for n in FORM_ROWS
]
_ADDITIONAL_PARSED = [
    {"name": n, "key": _normalize_key(n), "bg": bigrams(_normalize_key(n))}
    for n in ADDITIONAL_ROWS
]


@dataclass
class SnapResultHydraulika:
    name: str
    ratio: float
    status: str  # "exact" | "fixed" | "additional" | "off"


def _best_match(key: str, parsed: list[dict]) -> tuple[str | None, float]:
    best_name, best_ratio = None, -1.0
    for row in parsed:
        r = dice_coeff(key, row["key"], row["bg"])
        if r > best_ratio:
            best_name, best_ratio = row["name"], r
    return best_name, best_ratio


def snap_to_known_item_hydraulika(name: str) -> SnapResultHydraulika:
    key = _normalize_key(name)
    if not key:
        return SnapResultHydraulika(name=name, ratio=0.0, status="off")

    form_name, form_ratio = _best_match(key, _FORM_PARSED)
    if form_name is not None and form_ratio >= 0.95:
        return SnapResultHydraulika(name=form_name, ratio=form_ratio, status="exact")
    if form_name is not None and form_ratio >= 0.70:
        return SnapResultHydraulika(name=form_name, ratio=form_ratio, status="fixed")

    add_name, add_ratio = _best_match(key, _ADDITIONAL_PARSED)
    if add_name is not None and add_ratio >= 0.70:
        return SnapResultHydraulika(name=add_name, ratio=add_ratio, status="additional")

    fallback_ratio = max(form_ratio, add_ratio) if (form_name is not None or add_name is not None) else 0.0
    return SnapResultHydraulika(name=name, ratio=max(fallback_ratio, 0.0), status="off")
