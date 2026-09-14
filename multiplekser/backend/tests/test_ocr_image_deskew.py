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
