"""Przygotowanie jednego, malego obrazu do dodatkowej kontroli ilosci.

Gemini radzi sobie znacznie lepiej, gdy zamiast calego wielostronicowego skanu dostaje kilka
wycietych wierszy tabeli. Formularze maja staly uklad: wykrywamy poziome linie tabeli,
mapujemy nazwe na fizyczny numer wiersza i skladamy wszystkie niejasne pozycje w jeden obraz.
Jesli dokument ma inny uklad albo renderowanie sie nie powiedzie, wolajacy bezpiecznie pozostaje
przy oryginalnych plikach - dodatkowa kontrola nadal jest zbiorcza, a nie per-wiersz.
"""
from __future__ import annotations

import io
import logging
import re
from statistics import median

from PIL import Image, ImageDraw, ImageOps

from app.modules.parser.shared import strip_diacritics

logger = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"
_RENDER_SCALE = 2.5
_MAX_PAGES = 6

# Doslowny uklad aktualnego dwustronicowego formularza. Nie uzywamy alfabetycznego FORM_ROWS
# ani historycznych wariantow z FORM_PHYSICAL_ORDER, bo do cropa potrzebny jest numer wiersza
# na realnej kartce.
_ELEKTRYKA_PAGES: tuple[tuple[str, ...], ...] = (
    (
        "Wtyczka odbiornikowa 32A (niebieska) 1F",
        "Gniazdo przenośne 32A (niebieska) 1F",
        "Rozdzielnica SRN12 biała",
        "Rozdzielnica SRN 24 biała",
        "Rozdzielnica SRN 36 biała",
        "Rozdzielnica SRN 48 biała",
        "Maskownica do rozdzielnicy",
        "Rozłącznik izolacyjny modułowy 2P",
        "Różnicówka polska CDC240J",
        "Różnicówka polska CDA263J",
        "Wyłącznik nadprądowy 10A polski",
        "Wyłącznik nadprądowy 16A polski",
        "Wyłącznik nadprądowy 20A polski",
        "Wyłącznik nadprądowy 25A polski",
        "Gniazdo pojedyńcze polskie białe",
        "Gniazdo podwójne polskie białe",
        "Gniazdo potrójne polskie białe",
        "Gniazdo podwójne hermetyczne polskie (IP65)",
        "Gniazdo podłogowe ORNO polskie",
        "Wyłącznik jednobiegunowy biały",
        "Łącznik świecznikowy biały",
        "Wyłącznik schodowy biały",
        "Wyłącznik krzyżowy biały",
        "Oprawa panel LED BLINGO 120X30 biała",
        "Oprawa panel LED BLINGO 60X60 biała",
        "Szynoprzewód czarny 1mb",
        "Szynoprzewód czarny 2mb",
        "Lampa LED na szynoprzewód czarna",
        "Szynoprzewód biały 1mb",
        "Szynoprzewód biały 2mb",
        "Lampa LED na szynoprzewód biała",
        "Lampa łazienkowa",
        "Lampa łazienkowa hermetyczna biała",
        "Kinkiet Kanlux LED REKA 7W grafit",
        "Kinkiet LED HANA",
        "Elektroniczny programator czasowy",
        "Czujnik zmierzchu",
        "czujka ruchu zewnętrzna",
        "czujka ruchu wewnętrzna",
        "Grzejnik…...............W",
        "Szyna grzebieniowa widełkowa",
        "Końcówka tulejkowa TE 1,5-10",
        "Końcówka tulejkowa TE 2,5-10",
        "Końcówka tulejkowa 4-12",
        "Końcówka tulejkowa 10/12",
        "Końcówka tulejkowa 16/12",
        "Wago zamykane podwójne",
        "Wago zamykane potrójne",
    ),
    (
        "Wago zamykane 5 przewodów",
        "Przewód 3x1,5",
        "Przewód 3x2,5",
        "Przewód 3x4",
        "Przewód 5x4",
        "Przewód 5x16",
        "Przewód 3X16",
        "Przewód 1x10 kolor",
        "Przewód OLFLEX 4X1,5",
        "Peszel Ø.....",
        "Puszka pusta 86x86 czarna",
        "Puszka pusta 86x45",
        "Puszka czarna Hermetyczna IP65",
        "Dławica PG….....................",
        "Korytko 32x15 białe",
        "Korytko 40x25 białe",
        "Korytko 60x40 białe",
        "Korytko 90x60 białe",
        "Wkręt ocynk 4,2x16",
        "Wkręt czarny OSB",
        "INNE",
    ),
)

# Fizyczny uklad pierwszych dwoch stron aktualnego formularza Hydrauliki. Obejmuje drukowane
# wiersze (takze pozycje z bazy dodatkowej) i naprawia m.in. trójniki oraz węże z drugiej strony.
# Trzecia strona ma kilka scalonych, dwuwierszowych komórek; dla niej pozostaje bezpieczny
# fallback do oryginalnego PDF zamiast ryzykownego wycinka przesunietego o jeden wiersz.
_HYDRAULIKA_PAGES: tuple[tuple[str, ...], ...] = (
    (
        "__naglowek_hydraulika_pracownik__",
        "__naglowek_hydraulika_projekt__",
        "__naglowek_hydraulika_wymiar__",
        "__naglowek_hydraulika_kraj__",
        "__naglowek_hydraulika_kolumny__",
        "Bateria prysznicowa",
        "Bateria umywalkowa",
        "Bateria zlewozmywakowa",
        "Blat kuchenny 1200x600",
        "Blat kuchenny 1250x600",
        "Blat kuchenny 825x600",
        "Bojler 50 L",
        "Czwórnik 110x50 90 st",
        "Kabina prysznicowa 80 cm",
        "Kabina prysznicowa 90 cm",
        "Kolanko fi 20 45 st",
        "Kolanko kanalizacyjne fi 32 15 st",
        "Kolanko kanalizacyjne fi 32 30 st",
        "Kolanko kanalizacyjne fi 32 45 st",
        "Kolanko kanalizacyjne fi 32 67 st",
        "Kolanko kanalizacyjne fi 32 90 st",
        "Kolanko kanalizacyjne fi 40 15 st",
        "Kolanko kanalizacyjne fi 40 30 st",
        "Kolanko kanalizacyjne fi 40 45 st",
        "Kolanko kanalizacyjne fi 40 67 st",
        "Kolanko kanalizacyjne fi 40 90 st",
        "Kolanko kanalizacyjne fi 50 15 st",
        "Kolanko kanalizacyjne fi 50 30 st",
        "Kolanko kanalizacyjne fi 50 45 st",
        "Kolanko kanalizacyjne fi 50 90 st",
        "Kolanko PP fi 20 90 st",
        "Kolanko redukcyjne 50x32",
        "Kolanko ścienne GW",
        "Kompakt WC",
        "Końcówka beżowa",
        "Końcówka srebrna",
        "Kratka wentylacyjna 140x140 biała",
        "Kratka wentylacyjna 140x140 grafit",
        "Listwa boczna aluminiowa",
        "Mijanka PP fi 20",
        "Mufa dwukielichowa",
        "Mufa GW",
        "Mufa GZ",
        "Nakrętka M12",
    ),
    (
        "Narożnik wewnętrzny beżowy",
        "Narożnik wewnętrzny srebrny",
        "Podgrzewacz nadumywalkowy 10 L",
        "Podgrzewacz podumywalkowy 10 L",
        "Podkładka M12",
        "Pręt 12x1000",
        "Przyblatówka sonoma",
        "Przyblatówka srebrna",
        "Redukcja kanalizacyjna fi 40x32",
        "Redukcja kanalizacyjna fi 50x32",
        "Redukcja kanalizacyjna fi 50x40",
        "Rura fi 32 30 cm",
        "Rura fi 32 50 cm",
        "Rura fi 40 25 cm",
        "Rura fi 40 30 cm",
        "Rura fi 40 50 cm",
        "Rura fi 50 100 cm",
        "Rura fi 50 30 cm",
        "Rura fi 50 50 cm",
        "Rura kanalizacyjna 110x2,7x315",
        "Rura PP fi 20",
        "Syfon prysznicowy",
        "Syfon umywalkowy",
        "Szafka z umywalką 50 cm",
        "Szyna do montażu szafek",
        "Śruba do łączenia szafek",
        "Trójnik kanalizacyjny 100x50 90 st",
        "Trójnik kanalizacyjny fi 32 45 st",
        "Trójnik kanalizacyjny fi 32 67 st",
        "Trójnik kanalizacyjny fi 40 45 st",
        "Trójnik kanalizacyjny fi 50 45 st",
        "Trójnik kanalizacyjny fi 50 67 st",
        "Trójnik PP 20",
        "Uchwyt do rur fi 32",
        "Uchwyt do rur fi 40",
        "Uchwyt do rur fi 50",
        "Uchwyt rur podwójny fi 20",
        "Uchwyt rur pojedynczy fi 20",
        "Wąż 1/2x1/2 cala 20 cm",
        "Wąż 1/2x1/2 cala 30 cm",
        "Wąż 1/2x1/2 cala 40 cm",
        "Wąż 3/8x3/8 cala 40 cm",
        "Wąż 3/8x3/8 cala 30 cm",
        "Zaślepka fi 13 antracyt",
    ),
)


def _norm(value: str) -> str:
    value = strip_diacritics((value or "").lower())
    return re.sub(r"[^a-z0-9]", "", value)


_FORM_LAYOUTS = {
    "elektryka": _ELEKTRYKA_PAGES,
    "hydraulika": _HYDRAULIKA_PAGES,
}
_FORM_LOCATIONS = {
    dzial: {
        _norm(name): (page_index, row_index)
        for page_index, rows in enumerate(pages)
        for row_index, name in enumerate(rows)
    }
    for dzial, pages in _FORM_LAYOUTS.items()
}


def _render_pages(files: list[tuple[bytes, str]]) -> list[Image.Image]:
    pages: list[Image.Image] = []
    for raw, mime in files:
        if len(pages) >= _MAX_PAGES:
            break
        try:
            if mime == _PDF_MIME:
                import fitz  # PyMuPDF - zaleznosc produkcyjna, import leniwy dla zwyklych JPG

                with fitz.open(stream=raw, filetype="pdf") as document:
                    for page in document:
                        if len(pages) >= _MAX_PAGES:
                            break
                        pix = page.get_pixmap(
                            matrix=fitz.Matrix(_RENDER_SCALE, _RENDER_SCALE), alpha=False,
                        )
                        pages.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
            else:
                with Image.open(io.BytesIO(raw)) as image:
                    pages.append(ImageOps.exif_transpose(image).convert("RGB"))
        except Exception:
            logger.warning("OCR AI - nie udalo sie przygotowac wycinkow wierszy", exc_info=True)
            return []
    return pages


def _horizontal_line_centers(
    image: Image.Image, dark_level: int = 210, min_width_fraction: float = 0.24,
) -> list[tuple[int, int]]:
    """Zwraca (y, sila_linii) dla dlugich poziomych linii tabeli.

    Prog jest celowo wzgledny do szerokosci - dziala zarowno dla renderu PDF, jak i zdjecia po
    przeskalowaniu. Grupowanie laczy kilkupikselowa grubosc jednej linii w jeden punkt.
    """
    # Skan Hydrauliki jest wyraznie bledszy na dole 2. i 3. strony. Autokontrast wzmacnia
    # szare linie siatki, zanim policzymy ciemne piksele w kazdym poziomym przekroju.
    gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
    width, height = gray.size
    candidates: list[tuple[int, int]] = []
    for y in range(height):
        histogram = gray.crop((0, y, width, y + 1)).histogram()
        dark = sum(histogram[:dark_level])
        if dark >= width * min_width_fraction:
            candidates.append((y, dark))

    groups: list[list[tuple[int, int]]] = []
    for candidate in candidates:
        if not groups or candidate[0] > groups[-1][-1][0] + 2:
            groups.append([candidate])
        else:
            groups[-1].append(candidate)
    return [
        (round(sum(y for y, _ in group) / len(group)), max(strength for _, strength in group))
        for group in groups
    ]


def _find_row_lines(image: Image.Image, row_count: int) -> list[int] | None:
    centers = _horizontal_line_centers(image)
    required = row_count + 1
    if len(centers) < required:
        # Ostatnia strona Hydrauliki jest bardzo blada. Drugi prog dopuszcza jasniejsze linie,
        # a ponizsza kontrola regularnego rozstawu nadal odrzuca tekst i przypadkowe zabrudzenia.
        centers = _horizontal_line_centers(image, dark_level=225, min_width_fraction=0.18)
        if len(centers) < required:
            return None
        return _interpolate_faint_table_lines(centers, row_count, image.height)

    best: tuple[float, list[int]] | None = None
    width = image.width
    for start in range(len(centers) - required + 1):
        window = centers[start:start + required]
        ys = [y for y, _ in window]
        gaps = [b - a for a, b in zip(ys, ys[1:])]
        typical = median(gaps)
        if typical < 12 or typical > image.height * 0.08:
            continue
        variation = sum(abs(gap - typical) for gap in gaps) / (len(gaps) * typical)
        strength = sum(value for _, value in window) / (len(window) * width)
        # Stabilny rozstaw wybiera jeden blok tabeli; sila odroznia pelna tabele materialow od
        # wezszych tabel naglowka, ktore na pierwszej stronie maja podobny rozstaw.
        score = variation - strength
        if best is None or score < best[0]:
            best = (score, ys)
    return best[1] if best else None


def _interpolate_faint_table_lines(
    centers: list[tuple[int, int]], row_count: int, image_height: int,
) -> list[int] | None:
    """Odtwarza regularna siatke, gdy czesc bardzo bladych linii nie przekroczyla progu.

    Skan 3. strony Hydrauliki ma brakujace fragmenty linii, ale gorna i dolna krawedz oraz
    rozstaw pozostaja stale. Wybieramy pare krawedzi, ktorej interpolacja trafia w najwiecej
    rzeczywiscie wykrytych linii; tekst pomiedzy wierszami nie tworzy tak regularnego ukladu.
    """
    ys = [y for y, _ in centers]
    best: tuple[int, float, list[int]] | None = None
    for start_index, start in enumerate(ys):
        for end in ys[start_index + 1:]:
            gap = (end - start) / row_count
            if gap < 25 or gap > 55 or end > image_height:
                continue
            expected = [round(start + index * gap) for index in range(row_count + 1)]
            distances = [min(abs(y - actual) for actual in ys) for y in expected]
            hits = sum(distance <= 6 for distance in distances)
            mean_distance = sum(min(distance, 20) for distance in distances) / len(distances)
            candidate = (hits, -mean_distance, expected)
            if best is None or candidate[:2] > best[:2]:
                best = candidate
    if best is None or best[0] < max(4, (row_count + 1) // 3):
        return None
    return best[2]


def _row_crop(image: Image.Image, lines: list[int], row_index: int) -> Image.Image:
    # Pokazujemy wylacznie docelowy wiersz. Sasiednie wiersze pomagaly w orientacji, ale przy
    # pustej komorce model potrafil skopiowac z nich ilosc do celu.
    top = max(0, lines[row_index] - 4)
    bottom = min(image.height, lines[row_index + 1] + 4)
    strip = image.crop((0, top, image.width, bottom)).convert("RGB")

    # Usuwamy biale marginesy, ale zostawiamy cala szerokosc tabeli: nazwa i obie kolumny
    # ilosci musza pozostac w jednym wycinku.
    bbox = ImageOps.invert(strip.convert("L")).getbbox()
    if bbox:
        left = max(0, bbox[0] - 12)
        right = min(strip.width, bbox[2] + 12)
        strip = strip.crop((left, 0, right, strip.height))
    return strip


def _compose_crops(crops: list[tuple[str, str, Image.Image]]) -> bytes:
    header_height = 34
    padding = 10
    width = max(crop.width for _, _, crop in crops) + padding * 2
    height = sum(header_height + crop.height + padding for _, _, crop in crops) + padding
    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    y = padding
    for item_id, name, crop in crops:
        draw.text((padding, y + 8), f"Cel {item_id}: {name}", fill="black")
        y += header_height
        canvas.paste(crop, (padding, y))
        y += crop.height + padding

    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=92, optimize=True)
    return output.getvalue()


def discover_hydraulika_quantity_marks(
    files: list[tuple[bytes, str]],
) -> dict[str, tuple[bool, bool]]:
    """Wykrywa niebieskie oznaczenia osobno w kolumnach wydanej i zuzytej.

    Formularz ma czarny/szary druk, a pracownicy wypelniaja go niebieskim dlugopisem. Analiza
    dotyczy tylko srodkowych kolumn ilosci, wiec poprawki nazw i notatki na marginesie nie sa
    mylone z iloscia. To bezpieczna siatka dla trójników i węży z dolu drugiej strony.
    """
    pages = _render_pages(files)
    marked: dict[str, tuple[bool, bool]] = {}
    # Granice (poczatek wydanej, podzial kolumn, koniec zuzytej) sa lekko inne przez skos skanu.
    quantity_bounds = ((0.38, 0.545, 0.68), (0.40, 0.565, 0.70))
    for page_index, rows in enumerate(_HYDRAULIKA_PAGES):
        if page_index >= len(pages):
            break
        image = pages[page_index]
        lines = _find_row_lines(image, len(rows))
        if lines is None:
            continue
        wydana_start, column_split, zuzyta_end = quantity_bounds[page_index]
        wydana_left = round(image.width * wydana_start)
        split = round(image.width * column_split)
        zuzyta_right = round(image.width * zuzyta_end)
        for row_index, name in enumerate(rows):
            if name.startswith("__"):
                continue
            top = min(image.height, lines[row_index] + 3)
            bottom = max(top, min(image.height, lines[row_index + 1] - 3))
            counts: list[int] = []
            for left, right in ((wydana_left, split), (split, zuzyta_right)):
                cell = image.crop((left, top, right, bottom)).convert("RGB")
                counts.append(sum(
                    1 for red, green, blue in cell.getdata()
                    if blue >= red + 18 and blue >= green + 10 and blue < 245
                ))
            has_wydana, has_zuzyta = counts[0] >= 12, counts[1] >= 12
            if has_wydana or has_zuzyta:
                marked[name] = (has_wydana, has_zuzyta)
    return marked


def discover_marked_hydraulika_rows(files: list[tuple[bytes, str]]) -> list[str]:
    """Wstecznie zgodna lista nazw wierszy zawierajacych znak w dowolnej kolumnie."""
    return list(discover_hydraulika_quantity_marks(files))


def prepare_verification_files(
    files: list[tuple[bytes, str]], targets: list[tuple[str, str]], dzial: str,
) -> tuple[list[tuple[bytes, str]], bool]:
    """Zwraca jeden obraz z wycinkami albo niezmienione pliki jako bezpieczny fallback.

    `targets` to pary (stabilne_id, rozpoznana_nazwa). Flaga informuje prompt, czy dostal
    wycinki opisane etykietami "Cel ID", czy nadal oryginalny dokument.
    """
    layout = _FORM_LAYOUTS.get(dzial)
    locations_by_name = _FORM_LOCATIONS.get(dzial)
    if layout is None or locations_by_name is None or not targets:
        return files, False

    locations = [locations_by_name.get(_norm(name)) for _, name in targets]
    if any(location is None for location in locations):
        return files, False

    pages = _render_pages(files)
    if not pages:
        return files, False

    line_cache: dict[int, list[int] | None] = {}
    crops: list[tuple[str, str, Image.Image]] = []
    for (item_id, name), location in zip(targets, locations):
        assert location is not None
        page_index, row_index = location
        if page_index >= len(pages):
            return files, False
        if page_index not in line_cache:
            line_cache[page_index] = _find_row_lines(
                pages[page_index], len(layout[page_index]),
            )
        lines = line_cache[page_index]
        if lines is None or row_index + 1 >= len(lines):
            return files, False
        crops.append((item_id, name, _row_crop(pages[page_index], lines, row_index)))

    return [(_compose_crops(crops), "image/jpeg")], True
