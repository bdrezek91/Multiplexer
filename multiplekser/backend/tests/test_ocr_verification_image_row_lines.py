"""Regresja (2026-08-07): wykrywanie fizycznych linii wiersza w verification_image.py.

Realne zgloszenie uzytkownika: system oznaczyl 8 pustych wierszy jako "zaznaczone" na wydawce
Hydraulika (m.in. "Blat kuchenny 825x600", "Bojler 50 L") i nie potrafil potem znalezc dla nich
ilosci w zadnym modelu AI ("Dodatkowa kontrola ilosci" konczyla sie "Bez wyniku"). Przyczyna byla
podwojna:

1. `_find_row_lines` potrafilo wybrac do siatki wierszy slaba, przypadkowa "linie" (np. tekst
   pogrubionego naglowka kolumn) zamiast prawdziwej linii tabeli, przesuwajac indeksowanie
   WSZYSTKICH kolejnych wierszy strony - `_drop_weak_candidates`/`_trim_isolated_edges` to
   naprawiaja (patrz testy nizej, syntetyczne obrazy).
2. `_HYDRAULIKA_PAGES` (fizyczny uklad kolumn/wierszy do cropowania) mial "Nakretka M12"
   blednie jako OSTATNIA pozycje 1. strony zamiast PIERWSZEJ pozycji 2. strony, i BRAKOWALO
   "Blat kuchenny 1650x600" (prawdziwy, drukowany wiersz formularza, potwierdzony w katalogu
   Optima - baza_hydraulika.json) miedzy "1250x600" a "825x600" na 1. stronie - patrz test
   ponizej porownujacy uklad z lista."""
from PIL import Image, ImageDraw

from app.modules.ocr.verification_image import _HYDRAULIKA_PAGES, _find_row_lines


def test_layout_hydraulika_ma_blat_1650_miedzy_1250_a_825():
    page0 = _HYDRAULIKA_PAGES[0]
    assert page0.index("Blat kuchenny 1250x600") + 1 == page0.index("Blat kuchenny 1650x600")
    assert page0.index("Blat kuchenny 1650x600") + 1 == page0.index("Blat kuchenny 825x600")


def test_layout_hydraulika_nakretka_m12_jest_pierwsza_pozycja_2_strony_nie_ostatnia_1():
    page0, page1 = _HYDRAULIKA_PAGES
    assert "Nakrętka M12" not in page0
    assert page1[0] == "Nakrętka M12"


def _draw_grid(width: int, row_height: int, first_line: int, row_count: int) -> Image.Image:
    image = Image.new("RGB", (width, first_line + row_height * row_count + 60), "white")
    draw = ImageDraw.Draw(image)
    for row in range(row_count + 1):
        y = first_line + row * row_height
        draw.line((50, y, width - 50, y), fill="black", width=3)
    return image


def test_find_row_lines_ignoruje_slaba_linie_miedzy_dwoma_prawdziwymi():
    """Realny przypadek: tekst pogrubionego naglowka kolumn tworzyl kandydata na linie
    (szerokosc ~31% prawdziwej linii), ktory wszedl do siatki wierszy i przesunal caly rzad."""
    width, row_height, first_line, row_count = 1000, 40, 300, 10
    image = _draw_grid(width, row_height, first_line, row_count)
    draw = ImageDraw.Draw(image)
    weak_y = first_line + int(2.5 * row_height)
    draw.line((50, weak_y, 320, weak_y), fill="black", width=2)

    lines = _find_row_lines(image, row_count)

    assert lines == [first_line + row * row_height for row in range(row_count + 1)]


def test_find_row_lines_ignoruje_izolowana_linie_daleko_od_siatki():
    """Realny przypadek: samotna linia przy gornej krawedzi renderu strony, ~5x dalej od
    pierwszej prawdziwej linii tabeli niz typowy rozstaw wierszy."""
    width, row_height, first_line, row_count = 1000, 40, 300, 10
    image = _draw_grid(width, row_height, first_line, row_count)
    draw = ImageDraw.Draw(image)
    draw.line((50, 20, width - 50, 20), fill="black", width=3)

    lines = _find_row_lines(image, row_count)

    assert lines == [first_line + row * row_height for row in range(row_count + 1)]


def test_find_row_lines_ignoruje_oba_artefakty_jednoczesnie():
    width, row_height, first_line, row_count = 1000, 40, 300, 10
    image = _draw_grid(width, row_height, first_line, row_count)
    draw = ImageDraw.Draw(image)
    draw.line((50, 20, width - 50, 20), fill="black", width=3)
    weak_y = first_line + int(2.5 * row_height)
    draw.line((50, weak_y, 320, weak_y), fill="black", width=2)

    lines = _find_row_lines(image, row_count)

    assert lines == [first_line + row * row_height for row in range(row_count + 1)]
