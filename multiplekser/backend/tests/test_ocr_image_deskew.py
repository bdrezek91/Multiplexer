"""Testy prostowania przekrzywienia (deskew) przed OCR - na zyczenie uzytkownika (2026-09-14):
krzywo sfotografowana kartka utrudnia modelowi trzymanie sie linii siatki formularza, co bylo
podejrzewane o udzial w "przeciekaniu" ilosci miedzy sasiednimi wierszami (patrz historia czatu -
"Peszel" -> "Puszka pusta 86x86"). Obrazy syntetyczne (linie tabeli na bialym tle), nie realne
skany - testujemy sam mechanizm geometryczny, nie jakosc odczytu AI."""
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.modules.ocr.image import _detect_skew_angle_deg, deskew_image


def _synthetic_form_jpeg(rotate_deg: float = 0.0) -> bytes:
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in range(100, 900, 40):
        draw.line([(50, y), (750, y)], fill="black", width=2)
    draw.line([(50, 100), (50, 900)], fill="black", width=2)
    draw.line([(750, 100), (750, 900)], fill="black", width=2)
    for y in range(110, 890, 40):
        draw.rectangle([(60, y), (300, y + 20)], fill="black")
    if rotate_deg:
        img = img.rotate(-rotate_deg, expand=True, fillcolor="white")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _measured_angle(jpeg_bytes: bytes) -> float:
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return _detect_skew_angle_deg(gray)


def test_deskew_prostuje_przekrzywiona_kartke():
    raw = _synthetic_form_jpeg(rotate_deg=4.0)
    assert abs(_measured_angle(raw)) > 3.0  # kontrola - obraz wejsciowy faktycznie krzywy

    fixed = deskew_image(raw)
    assert abs(_measured_angle(fixed)) < 0.5


def test_deskew_nie_rusza_juz_prostego_obrazu():
    raw = _synthetic_form_jpeg(rotate_deg=0.0)
    assert deskew_image(raw) == raw


def test_deskew_nie_wywraca_sie_na_niepoprawnych_bajtach():
    assert deskew_image(b"to nie jest obraz") == b"to nie jest obraz"


def test_is_blank_page_pusta_biala_strona():
    from app.modules.ocr.image import is_blank_page

    buf = BytesIO()
    Image.new("RGB", (800, 1000), "white").save(buf, format="JPEG", quality=95)
    assert is_blank_page(buf.getvalue()) is True


def test_is_blank_page_prawdziwy_formularz_nie_jest_pusty():
    from app.modules.ocr.image import is_blank_page

    assert is_blank_page(_synthetic_form_jpeg()) is False


def test_is_blank_page_niepoprawny_obraz_nigdy_nie_jest_pusty():
    from app.modules.ocr.image import is_blank_page

    # Bezpieczny fallback: gdy nie da sie zdekodowac obrazu, NIGDY nie odfiltrowuj (lepiej
    # wyslac cos bezuzytecznego do AI niz zgubic strone przez blad dekodowania).
    assert is_blank_page(b"nie-jest-obrazem") is False


def _synthetic_form_jpeg_nierownomierna_tresc() -> bytes:
    """Prosta (nieobrocona) tabela, ale z BARDZO nierownomiernym rozkladem tresci (gesto
    zapisana gora, prawie pusty dol) - dokladnie taki uklad dal falszywe 8.2 st. skosu w
    realnym przypadku produkcyjnym (2026-09-18, PDF ze skanera, strona 3 - patrz historia
    czatu: "Przewod 3x4" -> "Przewod 3x2,5"), bo stara metoda (minAreaRect na calej chmurze
    ciemnych pikseli) jest wrazliwa na taka asymetrie."""
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    for y in range(100, 900, 40):
        draw.line([(50, y), (750, y)], fill="black", width=2)
    draw.line([(50, 100), (50, 900)], fill="black", width=2)
    draw.line([(750, 100), (750, 900)], fill="black", width=2)
    # Tekst/wypelnienie TYLKO w gornej jednej trzeciej - reszta tabeli pusta.
    for y in range(110, 350, 40):
        draw.rectangle([(60, y), (600, y + 20)], fill="black")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_detect_skew_nie_daje_falszywego_alarmu_na_prostej_ale_nierownomiernej_tabeli():
    """Regresja realnego przypadku produkcyjnego (2026-09-18) - patrz
    _synthetic_form_jpeg_nierownomierna_tresc. Metoda oparta na dlugich liniach siatki (Hough)
    musi zmierzyc kat bliski zeru, mimo asymetrycznego rozkladu tresci, ktory myli stara metode
    (minAreaRect na calej chmurze ciemnych pikseli)."""
    raw = _synthetic_form_jpeg_nierownomierna_tresc()
    assert abs(_measured_angle(raw)) < 0.5


def _synthetic_form_jpeg_kilka_dlugich_linii(rows: int = 6) -> bytes:
    """Prosta (nieobrocona) tabela z NIELICZNYMI, ale ZGODNYMI ze soba dlugimi liniami siatki
    (mniej niz stary prog _MIN_HOUGH_LINES=15) i asymetrycznym rozkladem tresci - dokladnie taki
    uklad dal DRUGI realny przypadek produkcyjny falszywego skosu (2026-09-18, PDF ze skanera,
    strona 2: "Peszel" -> "Puszka pusta 86x86") - zbyt malo dlugich linii oddawalo glos zawodnej
    minAreaRect, mimo ze te nieliczne linie byly ze soba zgodne (rozrzut < 0.1°)."""
    img = Image.new("RGB", (800, 1000), "white")
    draw = ImageDraw.Draw(img)
    step = 800 // (rows + 1)
    for i in range(1, rows + 1):
        y = i * step
        draw.line([(50, y), (750, y)], fill="black", width=2)
    draw.line([(50, step), (50, rows * step)], fill="black", width=2)
    draw.line([(750, step), (750, rows * step)], fill="black", width=2)
    # Tekst/wypelnienie TYLKO w gornej jednej trzeciej - tak jak w realnym przypadku.
    for i in range(1, rows // 2 + 1):
        y = i * step
        draw.rectangle([(60, y + 5), (600, y + 20)], fill="black")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_detect_skew_z_kilkoma_ale_zgodnymi_liniami_siatki_uzywa_hougha():
    """Test mechanizmu wprowadzonego po drugim realnym przypadku produkcyjnym (2026-09-18:
    "Peszel" -> "Puszka pusta 86x86") - realna, gesto zapisana strona formularza miala mniej niz
    stary prog _MIN_HOUGH_LINES=15 dlugich linii siatki, co oddawalo glos zawodnej minAreaRect
    (falszywe 2.15° zamiast realnych ~0.47°), mimo ze te nieliczne linie byly ze soba zgodne
    (rozrzut < 0.1°). Ten syntetyczny obraz nie odtwarza samego artefaktu JPG/skanera, ktory
    zmylil minAreaRect w oryginalnym przypadku (nie da sie tego wiarygodnie zsyntetyzowac) -
    weryfikuje natomiast, ze przy tylko kilku dlugich liniach wynik nadal pochodzi z Hougha
    (obnizony prog + kontrola zgodnosci katow, patrz _MIN_HOUGH_LINES/_MAX_HOUGH_ANGLE_STD_DEG)."""
    raw = _synthetic_form_jpeg_kilka_dlugich_linii(rows=6)
    assert abs(_measured_angle(raw)) < 0.5
