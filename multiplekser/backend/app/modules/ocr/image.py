"""Skalowanie obrazu przed wyslaniem do AI - port downscaleImage() z monolitu (Pillow zamiast
Canvas/Image przegladarki). Zdjecia z telefonu maja 8-12 MB - upload trwa dluzej niz sam odczyt."""
from __future__ import annotations

from io import BytesIO
from typing import Optional

import cv2
import fitz
import numpy as np
from PIL import Image

from app.core.config import settings

# Progi korekcji przekrzywienia (2026-09-14, na zyczenie uzytkownika - krzywo sfotografowana
# kartka utrudnia modelowi trzymanie sie linii siatki formularza, co bylo jednym z podejrzanych
# o "przeciekanie" ilosci miedzy wierszami). Ponizej _SKEW_MIN_DEG obraz jest juz wystarczajaco
# prosty - korekcja ponizej tego progu tylko dodawalaby szum bez realnej korzysci. Powyzej
# _SKEW_MAX_DEG wykryty "skos" zwykle oznacza, ze detekcja sie pomylila (np. zdjecie bez
# wyraznych linii poziomych) - lepiej nic nie ruszac niz obrocic obraz o przypadkowy, duzy kat.
_SKEW_MIN_DEG = 0.5
_SKEW_MAX_DEG = 30.0


def _detect_skew_angle_deg(gray: "np.ndarray") -> float:
    """Standardowa technika OpenCV (minAreaRect na progowanym obrazie) - zwraca kat w stopniach,
    o jaki trzeba obrocic obraz, zeby wyprostowac dominujace linie/tekst (dodatni = przeciwnie
    do ruchu wskazowek zegara, zgodnie z cv2.getRotationMatrix2D)."""
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.shape[0] < 50:  # zbyt malo tresci, zeby sensownie ocenic kat
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    return -(90 + angle) if angle < -45 else -angle


def deskew_image(file_bytes: bytes) -> bytes:
    """Prostuje krzywo sfotografowany/zeskanowany dokument PRZED wyslaniem do OCR. Bezpieczny
    no-op gdy obraz jest juz prosty (kat < _SKEW_MIN_DEG) lub gdy detekcja daje niewiarygodny,
    zbyt duzy kat (> _SKEW_MAX_DEG) - w obu przypadkach zwraca oryginalne bajty bez zmian,
    zamiast ryzykowac pogorszenie dobrego zdjecia zlym obrotem."""
    arr = np.frombuffer(file_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return file_bytes

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    angle = _detect_skew_angle_deg(gray)
    if abs(angle) < _SKEW_MIN_DEG or abs(angle) > _SKEW_MAX_DEG:
        return file_bytes

    height, width = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    rotated = cv2.warpAffine(
        img, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )
    ok, encoded = cv2.imencode(".jpg", rotated, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return encoded.tobytes() if ok else file_bytes

# DPI renderowania stron PDF do obrazow (2026-09-09, patrz historia czatu - dwustronicowy
# zeskanowany PDF, model zgubil gorna czesc pierwszej strony przy natywnym odczycie PDF przez
# Gemini). 200 DPI daje ostry tekst formularza przy rozsadnym rozmiarze pliku (obraz i tak
# przechodzi jeszcze przez downscale_image ponizej).
_PDF_RENDER_DPI = 200


def pdf_to_page_images(pdf_bytes: bytes) -> list[bytes]:
    """Rozbija PDF na osobne obrazy PNG, po jednym na strone - kazda strona trafia PONIZEJ do AI
    jako OSOBNA czesc zapytania, dokladnie tak jak juz sprawdzony przypadek "kilka zdjec z
    telefonu = kilka stron jednej wydawki" (patrz ocr/providers.py, tasks.py). Natywne wysylanie
    calego wielostronicowego PDF jako jednego pliku bylo mniej niezawodne - model potrafil
    zgubic fragment tresci (np. gorna czesc pierwszej strony) na gestym, dwustronicowym
    dokumencie."""
    zoom = _PDF_RENDER_DPI / 72
    matrix = fitz.Matrix(zoom, zoom)
    pages: list[bytes] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            pages.append(pix.tobytes("png"))
    return pages


def downscale_image(file_bytes: bytes, max_side: Optional[int] = None, quality: Optional[int] = None) -> bytes:
    """Zwraca bajty JPEG przeskalowane tak, ze dluzszy bok <= max_side. Obrazy juz mniejsze niz
    max_side NIE sa powiekszane (jak w oryginale JS - skalowanie tylko w dol). Prostowanie
    przekrzywienia (deskew_image) dzieje sie NAJPIERW, na pelnej rozdzielczosci - poprawia to
    dokladnosc wykrycia linii siatki formularza bardziej niz na juz pomniejszonym obrazie."""
    file_bytes = deskew_image(file_bytes)
    max_side = settings.ocr_image_max_side if max_side is None else max_side
    quality = settings.ocr_image_quality if quality is None else quality

    with Image.open(BytesIO(file_bytes)) as img:
        img = img.convert("RGB")
        longer = max(img.width, img.height)
        if longer > max_side:
            k = max_side / longer
            new_size = (round(img.width * k), round(img.height * k))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality)
        return out.getvalue()
