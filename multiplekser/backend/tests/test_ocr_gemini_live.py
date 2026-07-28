"""Test opcjonalny Etapu 6: PRAWDZIWE wywolanie Gemini API (pomijany bez ustawionego klucza).

Uruchom recznie z wlasnym kluczem:
    GEMINI_API_KEY_FREE=twoj_klucz pytest tests/test_ocr_gemini_live.py -v

Celowo NIE jest czescia standardowego zestawu testow (koszt/limity API, wymaga sieci) - patrz
test_ocr_provider_gemini.py dla testow na zamockowanym HTTP, ktore biegna zawsze.
"""
import os
from io import BytesIO

import pytest
from PIL import Image

from app.modules.ocr.prompt import AI_OCR_PROMPT
from app.modules.ocr.providers import GeminiProvider

_KEY = os.environ.get("GEMINI_API_KEY_FREE")


@pytest.mark.skipif(not _KEY, reason="wymaga prawdziwego klucza Gemini w zmiennej GEMINI_API_KEY_FREE")
async def test_gemini_recognize_prawdziwe_wywolanie():
    buf = BytesIO()
    Image.new("RGB", (200, 200), color="white").save(buf, format="JPEG")

    text = await GeminiProvider().recognize(
        file_bytes=buf.getvalue(), mime="image/jpeg", model="gemini-3.6-flash", api_key=_KEY, prompt=AI_OCR_PROMPT,
    )
    assert isinstance(text, str)
    assert len(text) > 0
