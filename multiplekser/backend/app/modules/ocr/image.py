"""Skalowanie obrazu przed wyslaniem do AI - port downscaleImage() z monolitu (Pillow zamiast
Canvas/Image przegladarki). Zdjecia z telefonu maja 8-12 MB - upload trwa dluzej niz sam odczyt."""
from __future__ import annotations

from io import BytesIO
from typing import Optional

from PIL import Image

from app.core.config import settings


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
