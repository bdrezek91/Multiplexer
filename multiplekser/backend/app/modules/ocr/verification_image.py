"""Przygotowanie jednego, malego obrazu do dodatkowej kontroli ilosci.

Gemini radzi sobie znacznie lepiej, gdy zamiast calego wielostronicowego skanu dostaje kilka
wycietych wierszy tabeli. Formularz Elektryka ma staly uklad: wykrywamy poziome linie tabeli,
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


def _norm(value: str) -> str:
    value = strip_diacritics((value or "").lower())
    return re.sub(r"[^a-z0-9]", "", value)


_ELEKTRYKA_LOCATIONS = {
    _norm(name): (page_index, row_index)
    for page_index, rows in enumerate(_ELEKTRYKA_PAGES)
    for row_index, name in enumerate(rows)
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


def _horizontal_line_centers(image: Image.Image) -> list[tuple[int, int]]:
    """Zwraca (y, sila_linii) dla dlugich poziomych linii tabeli.

    Prog jest celowo wzgledny do szerokosci - dziala zarowno dla renderu PDF, jak i zdjecia po
    przeskalowaniu. Grupowanie laczy kilkupikselowa grubosc jednej linii w jeden punkt.
    """
    gray = image.convert("L")
    width, height = gray.size
    candidates: list[tuple[int, int]] = []
    for y in range(height):
        histogram = gray.crop((0, y, width, y + 1)).histogram()
        dark = sum(histogram[:210])
        if dark >= width * 0.24:
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
        return None

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


def prepare_verification_files(
    files: list[tuple[bytes, str]], targets: list[tuple[str, str]], dzial: str,
) -> tuple[list[tuple[bytes, str]], bool]:
    """Zwraca jeden obraz z wycinkami albo niezmienione pliki jako bezpieczny fallback.

    `targets` to pary (stabilne_id, rozpoznana_nazwa). Flaga informuje prompt, czy dostal
    wycinki opisane etykietami "Cel ID", czy nadal oryginalny dokument.
    """
    if dzial != "elektryka" or not targets:
        return files, False

    locations = [_ELEKTRYKA_LOCATIONS.get(_norm(name)) for _, name in targets]
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
                pages[page_index], len(_ELEKTRYKA_PAGES[page_index]),
            )
        lines = line_cache[page_index]
        if lines is None or row_index + 1 >= len(lines):
            return files, False
        crops.append((item_id, name, _row_crop(pages[page_index], lines, row_index)))

    return [(_compose_crops(crops), "image/jpeg")], True
