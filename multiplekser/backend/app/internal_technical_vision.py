import json
import os
import re
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from app.modules.ocr.providers import GeminiProvider, OCRProviderError

app = FastAPI(title="Multiplekser Internal Technical Vision", docs_url=None, redoc_url=None)

MAX_FILES = 12
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 28 * 1024 * 1024

PROMPT = """Jesteś specjalistycznym modułem odczytu TECHNICZNYCH kart, rzutów, elewacji i rysunków produkcyjnych pawilonów firmy Dampol.
Otrzymujesz WYŁĄCZNIE strony wcześniej dopuszczone przez lokalną bramkę prywatności.
Wynik będzie później łączony z RZECZYWISTYM RWS jako target treningowy, dlatego NIE przewiduj zużycia materiałów na podstawie wiedzy ogólnej i NIE zgaduj.

PRIORYTETY:
1. GEOMETRIA I WYMIARY — odczytaj każdą widoczną linię wymiarową, gabaryty, wysokości, spadki, podziały ścian, odległości i położenia otworów.
2. ELEWACJA — dla każdej ściany osobno odczytaj rodzaj wykończenia, pola materiałowe, kasetony, lamele, deski, kolory/RAL, kierunki podziałów, fugi, moduły i wymiary.
3. KASETONY/BLACHA — jeśli na którejkolwiek stronie występują kasetony, blacha elewacyjna albo regularny podział pól, uruchom OBOWIĄZKOWO TRYB KASETONOWY:
   a) przeanalizuj każdą elewację/strefę osobno i policz widoczne pionowe oraz poziome linie podziału;
   b) odczytaj każdy łańcuch wymiarowy przy elewacji i przypisz segmenty do konkretnych pól/kasetonów;
   c) wpisz liczbę kolumn i rzędów zawsze, gdy da się je jednoznacznie policzyć z rysunku;
   d) jeśli moduł nie jest podpisany wprost, ale jednoznacznie wynika z wymiaru strefy i liczby RÓWNYCH pól, WYLICZ go i zapisz w derived.kasetony wraz z formułą i confidence; nie wpisuj takiej wartości do pola bezpośredniego;
   e) jeśli siatkę przerywa okno/drzwi/narożnik, podziel elewację na strefy i zapisz docinki/niestandardowe szerokości zamiast uśredniać;
   f) odczytaj fugę, jeżeli jest zwymiarowana; jeśli wynika matematycznie z wymiaru strefy + modułów, zapisz ją tylko jako derived z formułą;
   g) dla każdego pola blachy zapisuj kolor/RAL i powierzchnię tylko wtedy, gdy wynika z jawnej lub wyliczonej geometrii;
   h) NIGDY nie zakładaj standardowego modułu/fugi (np. 240 mm/15 mm) tylko dlatego, że jest typowy — musi wynikać z konkretnego rysunku.
4. STOLARKA/SZKŁO — każdy element osobno: typ, szerokość, wysokość, ilość, zimne/ciepłe, 2/3 szyby, fix/RU/przesuwne/wydawcze, kierunek otwierania, słupki, PVB, mleczna/clear, kolor.
5. PŁYTY I PRZEGRODY — PIR/styropian, grubość, profilacja, kolor, ściana/dach/podłoga, MFP/OSB, wykładzina.
6. KONSTRUKCJA — rodzaj konstrukcji, profile, wymiary przekrojów, grubości, długości jeśli są podane, statyka/kratownica/podpory/kątowniki.
7. OBRÓBKI — attyki, narożniki, cokoły, obróbki wewnętrzne/zewnętrzne, szerokości, wysokości, grubości, kolory i długości tylko jeśli wynikają z rysunku.
8. INSTALACJE/WYPOSAŻENIE — elektryka, rolety, klimatyzacja, sanitariaty, aneks, kratki, daszki itd.

Nie zwracaj danych kontaktowych, nazwisk, adresów ani cen.
Odczytaj dopiski odręczne i zaznaczone checkboxy.
Jeżeli wartość jest nieczytelna albo sprzeczna, wpisz null i opisz problem w "niepewne".
Wartości bezpośrednio odczytane trzymaj osobno od wartości wyliczonych.
Każda wartość wyliczona musi mieć formułę/podstawę i confidence. Nie licz niczego, jeśli brakuje danych wejściowych.

Zwróć WYŁĄCZNIE poprawny JSON bez markdown, według schematu:
{
  "nr_projektu": null,
  "wymiary_pawilonu": null,
  "wysokosc": null,
  "gatunek": null,
  "geometria": {
    "dlugosc_mm": null,
    "szerokosc_mm": null,
    "wysokosc_front_mm": null,
    "wysokosc_tyl_mm": null,
    "spadek_dachu": null,
    "moduly_bryly": [],
    "sciany": [
      {
        "id": null,
        "strona": null,
        "szerokosc_mm": null,
        "wysokosc_lewa_mm": null,
        "wysokosc_prawa_mm": null,
        "pola_wymiarowe": [],
        "otwory": [],
        "uwagi": []
      }
    ],
    "wymiary_surowe": []
  },
  "konstrukcja": [],
  "profile_stalowe": [
    {
      "profil": null,
      "przekroj": null,
      "grubosc_mm": null,
      "dlugosc_mm": null,
      "ilosc": null,
      "lokalizacja": null,
      "zrodlo": null
    }
  ],
  "dach": {
    "typ": null,
    "grubosc": null,
    "kolor": null,
    "profilacja": null,
    "kierunek_spadku": null,
    "wymiary": []
  },
  "sciany": {
    "typ": null,
    "grubosc": null,
    "kolor_wewn": null,
    "kolor_zewn": null,
    "profilacja": null
  },
  "podloga": {
    "typ": null,
    "grubosc": null,
    "mfp": null,
    "osb": null,
    "wykladzina": null
  },
  "elewacja_zewnetrzna": [],
  "elewacje": [
    {
      "strona": null,
      "szerokosc_mm": null,
      "wysokosc_mm": null,
      "pola": [
        {
          "typ": null,
          "material": null,
          "kolor": null,
          "ral": null,
          "x_mm": null,
          "y_mm": null,
          "szerokosc_mm": null,
          "wysokosc_mm": null,
          "uwagi": []
        }
      ],
      "kasetony": {
        "obecne": null,
        "typ": null,
        "kolor": null,
        "ral": null,
        "orientacja": null,
        "modul_szerokosc_mm": null,
        "modul_wysokosc_mm": null,
        "fuga_mm": null,
        "liczba_kolumn": null,
        "liczba_rzedow": null,
        "wymiary_indywidualne": [],
        "narozne_L": [],
        "uwagi": []
      },
      "lamele": {
        "obecne": null,
        "szerokosc_mm": null,
        "szczelina_mm": null,
        "kolor": null,
        "dlugosci_mm": [],
        "ilosc": null
      }
    }
  ],
  "obrobki": [
    {
      "typ": null,
      "lokalizacja": null,
      "kolor": null,
      "ral": null,
      "szerokosc_mm": null,
      "wysokosc_mm": null,
      "dlugosc_mm": null,
      "grubosc_mm": null,
      "ilosc": null
    }
  ],
  "stolarka": [
    {
      "id": null,
      "typ": null,
      "material": null,
      "szerokosc_mm": null,
      "wysokosc_mm": null,
      "ilosc": null,
      "profil": null,
      "ciepla_zimna": null,
      "liczba_szyb": null,
      "funkcja": null,
      "kierunek_otwierania": null,
      "slupek": null,
      "kolor": null,
      "ral": null,
      "lokalizacja": null,
      "x_mm": null,
      "odleglosci_od_krawedzi_mm": [],
      "uwagi": []
    }
  ],
  "szklo": [
    {
      "id": null,
      "szerokosc_mm": null,
      "wysokosc_mm": null,
      "ilosc": null,
      "typ": null,
      "pakiet": null,
      "pvb": null,
      "mleczna_clear": null,
      "hartowane": null,
      "lokalizacja": null,
      "uwagi": []
    }
  ],
  "rolety_zaluzje": [],
  "elektryka": [],
  "klimatyzacja": [],
  "lazienka": [],
  "aneks_kuchenny": [],
  "informacje_dodatkowe": [],
  "dopiski_odreczne": [],
  "towary_materialy": [
    {
      "kategoria": null,
      "nazwa": null,
      "wariant": null,
      "specyfikacja": [],
      "ilosc": null,
      "jednostka": null
    }
  ],
  "derived": {
    "powierzchnia_podlogi_m2": {"value": null, "formula": null, "confidence": null},
    "powierzchnia_dachu_m2": {"value": null, "formula": null, "confidence": null},
    "powierzchnie_scian_brutto_m2": [],
    "powierzchnie_otworow_m2": [],
    "powierzchnie_scian_netto_m2": [],
    "powierzchnie_elewacji_m2": [],
    "powierzchnie_blach_m2": [],
    "obwody_i_dlugosci_mb": [],
    "kasetony": [
      {
        "strona": null,
        "strefa": null,
        "typ": null,
        "kolor": null,
        "ral": null,
        "strefa_szerokosc_mm": null,
        "strefa_wysokosc_mm": null,
        "modul_szerokosc_mm": null,
        "modul_wysokosc_mm": null,
        "fuga_mm": null,
        "liczba_kolumn": null,
        "liczba_rzedow": null,
        "docinki_mm": [],
        "formula": null,
        "confidence": null,
        "zrodlo": null
      }
    ],
    "lamele": [
      {
        "strona": null,
        "strefa": null,
        "szerokosc_mm": null,
        "szczelina_mm": null,
        "skok_mm": null,
        "ilosc": null,
        "formula": null,
        "confidence": null,
        "zrodlo": null
      }
    ]
  },
  "niepewne": []
}

ZASADY SZCZEGÓŁOWE:
- wszystkie wymiary liczbowe normalizuj do mm, ale zachowaj też tekst źródłowy w "wymiary_surowe", jeśli występuje;
- jeśli rysunek pokazuje kilka modułów/brył, zapisuj je oddzielnie;
- ściany/elewacje identyfikuj jako front/tył/lewa/prawa lub dokładnym oznaczeniem z rysunku;
- dla otworów zapisuj typ, wymiary, pozycję i odległości od krawędzi, jeśli są podane;
- kaseton kwadrat/prostokąt/poziomy/pionowy traktuj jako różne warianty; zapisuj każdą widoczną wielkość modułu;
- jeśli kasetony są widoczne, NIE kończ analizy bez próby policzenia rzędów/kolumn dla każdej strefy; gdy nie da się tego zrobić wiarygodnie, wpisz konkretny powód do "niepewne";
- jeśli wymiar strefy i liczba równych pól pozwalają policzyć moduł, zapisz wynik w derived.kasetony z formułą, np. "(szerokość_strefy - suma_fug) / liczba_kolumn";
- jeżeli widoczny jest łańcuch wymiarów kolejnych pól, traktuj go jako bezpośrednią podstawę wymiarów kasetonów, nawet jeśli brak osobnej etykiety "kaseton";
- jeżeli kasetony mają niestandardowe docinki przy otworach/narożach, zapisz wymiary indywidualne zamiast uśredniać;
- jeżeli na rysunku występuje fuga, zapisz jej rzeczywistą szerokość; jeśli da się ją tylko wyliczyć, zapisuj wyłącznie w derived.kasetony;
- dla lameli rozpoznaj szerokość listwy, szczelinę/skok i liczbę elementów; wyliczenia zapisuj w derived.lamele;
- pola powierzchnie_elewacji_m2 i powierzchnie_blach_m2 wypełniaj obiektami zawierającymi co najmniej stronę/strefę, kolor/RAL, value, formula i confidence;
- kolory zapisuj zarówno opisowo, jak i RAL, jeśli RAL jest podany;
- przy blachach rozróżniaj pola wg koloru/typu; NIE zakładaj powierzchni z samego wyglądu bez wymiarów;
- przy obróbkach rozróżniaj narożniki, attykę, parapety, cokół, opaski, daszki i inne elementy;
- przy szkle rozróżniaj samo szkło od całej stolarki;
- nie duplikuj tego samego elementu tylko dlatego, że występuje na kilku stronach;
- zachowaj stare pola (wymiary_pawilonu, konstrukcja, elewacja_zewnetrzna itd.) dla zgodności;
- NIE próbuj przewidywać RWS. Zwróć wyłącznie to, co da się odczytać lub jawnie obliczyć z rysunku.
"""

FACADE_PROMPT = """Jesteś wyspecjalizowanym inspektorem GEOMETRII ELEWACJI pawilonów.
Otrzymujesz wyłącznie bezpieczne techniczne strony rysunku. Nie analizuj całego projektu i nie przewiduj RWS.
Twoim zadaniem jest maksymalnie dokładnie odtworzyć geometrię KASETONÓW, BLACH i LAMELI z widocznego rysunku.

OBOWIĄZKOWA PROCEDURA:
1. Znajdź każdą elewację / ścianę / strefę widoczną na obrazach.
2. Odczytaj jej całkowitą szerokość i wysokość z linii wymiarowych, jeśli są widoczne.
3. Wyszukaj pionowe i poziome linie podziału kasetonów/pól blachy. POLICZ je wizualnie.
4. Wpisz liczba_kolumn i liczba_rzedow, gdy podział jest jednoznaczny, nawet jeśli moduł nie ma osobnej etykiety.
5. Odczytaj każdy łańcuch wymiarowy segment po segmencie. Segmenty przy elewacji traktuj jako potencjalne szerokości/wysokości pól.
6. Jeżeli strefa ma N równych pól i znany wymiar całkowity, możesz wyliczyć wymiar POJEDYNCZEGO modułu. Zapisz go WYŁĄCZNIE w derived wraz z formułą i confidence.
   UWAGA: gdy liczba_kolumn=1, szerokość całej strefy NIE jest szerokością modułu kasetonu — modul_szerokosc_mm ma wtedy pozostać null, chyba że na rysunku jest jawny wymiar pojedynczego kasetonu.
   Analogicznie liczba_rzedow=1 nie oznacza, że wysokość całej strefy jest wysokością pojedynczego kasetonu.
7. Jeżeli występują otwory, narożniki lub docinki, podziel elewację na strefy i NIE uśredniaj ich z regularnym modułem.
8. Odczytaj fugę tylko jeśli jest podpisana lub matematycznie wynika z pełnego łańcucha wymiarowego. Nie zakładaj żadnej wartości standardowej.
9. Dla blachy/kasetonów zapisz kolor i RAL, jeśli są widoczne. Nie zgaduj RAL z samego koloru.
10. Dla lameli spróbuj ustalić szerokość listwy, szczelinę/skok, liczbę elementów i długości.
11. Jeśli nie da się ustalić dokładnego wymiaru, pozostaw null, ale nadal podaj wiarygodną liczbę pól/rzędów, jeśli można je policzyć.
12. NIGDY nie zakładaj typowych wartości takich jak 240 mm lub 15 mm bez podstawy z tego konkretnego rysunku.

Zwróć WYŁĄCZNIE JSON:
{
  "elewacje": [
    {
      "strona": null,
      "strefa": null,
      "szerokosc_mm": null,
      "wysokosc_mm": null,
      "kasetony": {
        "obecne": null,
        "typ": null,
        "kolor": null,
        "ral": null,
        "orientacja": null,
        "liczba_kolumn": null,
        "liczba_rzedow": null,
        "modul_szerokosc_mm": null,
        "modul_wysokosc_mm": null,
        "fuga_mm": null,
        "linie_pionowe": [],
        "linie_poziome": [],
        "wymiary_indywidualne": [],
        "docinki": [],
        "uwagi": []
      },
      "lamele": {
        "obecne": null,
        "szerokosc_mm": null,
        "szczelina_mm": null,
        "skok_mm": null,
        "ilosc": null,
        "dlugosci_mm": [],
        "uwagi": []
      }
    }
  ],
  "derived": {
    "kasetony": [
      {
        "strona": null,
        "strefa": null,
        "modul_szerokosc_mm": null,
        "modul_wysokosc_mm": null,
        "fuga_mm": null,
        "liczba_kolumn": null,
        "liczba_rzedow": null,
        "formula": null,
        "confidence": null
      }
    ],
    "powierzchnie_blach_m2": [
      {
        "strona": null,
        "strefa": null,
        "kolor": null,
        "ral": null,
        "value": null,
        "formula": null,
        "confidence": null
      }
    ]
  },
  "niepewne": []
}
"""


def _clean_json(raw: str):
    value = (raw or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\\s*", "", value, flags=re.I)
        value = re.sub(r"\\s*```$", "", value)
        value = value.strip()
    try:
        return json.loads(value)
    except Exception:
        pass

    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(value[start:end + 1])
        except Exception:
            pass
    return None

@app.get("/health")
def health():
    return {"ok": True, "service": "internal-technical-vision"}

async def _read_with_prompt(
    files: list[UploadFile],
    prompt: str,
):
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f"Dozwolone 1-{MAX_FILES} obrazów.")

    prepared = []
    total = 0
    for f in files:
        ctype = (f.content_type or "").lower()
        if ctype not in {"image/jpeg", "image/png"}:
            raise HTTPException(400, "Serwis przyjmuje wyłącznie obrazy JPEG/PNG, nigdy PDF.")
        data = await f.read()
        if not data or len(data) > MAX_FILE_BYTES:
            raise HTTPException(400, "Nieprawidłowy rozmiar obrazu.")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise HTTPException(400, "Łączny rozmiar obrazów jest zbyt duży.")
        prepared.append((data, ctype))

    free_key = os.getenv("GEMINI_API_KEY_FREE", "").strip()
    paid_key = os.getenv("GEMINI_API_KEY_PAID", "").strip()
    attempts = [
        ("gemini-3.6-flash", paid_key),
        ("gemini-3.5-flash", free_key),
    ]
    provider = GeminiProvider()
    errors = []

    for model, key in attempts:
        if not key:
            continue
        try:
            raw = await provider.recognize(
                files=prepared,
                model=model,
                api_key=key,
                prompt=prompt,
                thinking_level="high",
            )
            parsed = _clean_json(raw)
            return {
                "ok": True,
                "model": model,
                "data": parsed,
                "raw": None if parsed is not None else raw,
                "images_received": len(prepared),
            }
        except OCRProviderError as exc:
            errors.append(f"{model}: {exc}")

    raise HTTPException(502, " | ".join(errors[-2:]) or "Brak klucza Gemini.")


@app.post("/read")
async def read_technical_pages(
    files: Annotated[list[UploadFile], File(description="Allowed technical page images")],
):
    return await _read_with_prompt(files, PROMPT)


@app.post("/read-facade")
async def read_facade_pages(
    files: Annotated[list[UploadFile], File(description="Allowed technical facade page images")],
):
    return await _read_with_prompt(files, FACADE_PROMPT)
