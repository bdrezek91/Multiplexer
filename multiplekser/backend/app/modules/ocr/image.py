"""Skalowanie obrazu przed wyslaniem do AI - port downscaleImage() z monolitu (Pillow zamiast
Canvas/Image przegladarki). Zdjecia z telefonu maja 8-12 MB - upload trwa dluzej niz sam odczyt."""
from __future__ import annotations

from io import BytesIO
from typing import Optional

import fitz
from PIL import Image

from app.core.config import settings

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
    max_side NIE sa powiekszane (jak w oryginale JS - skalowanie tylko w dol)."""
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
