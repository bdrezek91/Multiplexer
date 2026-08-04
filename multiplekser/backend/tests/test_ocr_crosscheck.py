"""Testy niezaleznego drugiego odczytu (OpenAI) do wykrywania rozbieznosci z Gemini - realny
przypadek produkcyjny (2026-08-04): to samo zdjecie wydawki dawalo rozne wyniki miedzy przebiegami
Gemini (np. "Rozdzielnica SRN 24" zamiast "SRN 36", przestawione ilosci miedzy dwoma kinkietami).
Gemini pozostaje zrodlem prawdy - OpenAI tu wylacznie flaguje niepewne pozycje."""
from unittest.mock import AsyncMock, patch

from app.core.config import settings
from app.modules.matcher.result import MatchResult
from app.modules.ocr.crosscheck import flag_mismatches, run_cross_check
from app.modules.ocr.pipeline_elektryka import OCRItem, OCRResult


def _item(nazwa: str, wydana, zuzyta, kod: str | None) -> dict:
    return {
        "rozpoznana_nazwa": nazwa, "ilosc_wydana": wydana, "ilosc_zuzyta": zuzyta,
        "match_kod": kod, "needs_review": False, "form_note": "",
    }


def _pozycja(nazwa: str, wydana, zuzyta, kod: str | None) -> OCRItem:
    return OCRItem(
        rozpoznana_nazwa=nazwa, ilosc_wydana=wydana, ilosc_zuzyta=zuzyta, uwagi="",
        confidence=99.0, needs_review=False, off_form=False, form_note="",
        match=MatchResult(kod=kod, nazwa=kod, quality="ok", ratio=1.0),
    )


def test_flag_mismatches_nie_rusza_pozycji_zgodnej_ilosciowo():
    items = [_item("Rozdzielnica SRN 36 biała", 1.0, None, "ROZDZIELNICA SRN 36")]
    other = [_pozycja("Rozdzielnica SRN 36 biała", "1", None, "ROZDZIELNICA SRN 36")]

    flag_mismatches(items, other)

    assert items[0]["needs_review"] is False
    assert items[0]["form_note"] == ""


def test_flag_mismatches_oznacza_rozna_ilosc_jako_do_weryfikacji():
    # Realny przypadek: Gemini raz zwrocil Kinkiet Kanlux=1/HANA=3, kiedy indziej odwrotnie.
    items = [_item("Kinkiet Kanlux LED REKA 7W grafit", 1.0, None, "KINKIET KANLUX LED REKA 7W GRAFIT")]
    other = [_pozycja("Kinkiet Kanlux LED REKA 7W grafit", "3", None, "KINKIET KANLUX LED REKA 7W GRAFIT")]

    flag_mismatches(items, other)

    assert items[0]["needs_review"] is True
    assert "Niezgodność" in items[0]["form_note"]


def test_flag_mismatches_oznacza_pozycje_ktorej_openai_nie_znalazl():
    # Realny przypadek: Gemini zmyslil dodatkowy wiersz "Rozdzielnica SRN 12" ktorego nie bylo.
    items = [_item("Rozdzielnica SRN 12 biała", 1.0, None, "ROZDZIELNICA SRN 12")]
    other: list[OCRItem] = []

    flag_mismatches(items, other)

    assert items[0]["needs_review"] is True
    assert "nie znalazł" in items[0]["form_note"]


def test_flag_mismatches_dopasowuje_po_kodzie_a_nie_po_kolejnosci():
    items = [
        _item("A", 1.0, None, "KOD_A"),
        _item("B", 2.0, None, "KOD_B"),
    ]
    # OpenAI zwraca w odwrotnej kolejnosci - i tak musi trafic na wlasciwa pozycje po kodzie.
    other = [_pozycja("B", "2", None, "KOD_B"), _pozycja("A", "1", None, "KOD_A")]

    flag_mismatches(items, other)

    assert items[0]["needs_review"] is False
    assert items[1]["needs_review"] is False


def test_flag_mismatches_dopasowuje_po_nazwie_gdy_brak_kodu_dopasowania():
    items = [_item("Zupełnie nieznany towar", 1.0, None, None)]
    other = [_pozycja("zupełnie nieznany towar", "1", None, None)]

    flag_mismatches(items, other)

    assert items[0]["needs_review"] is False


async def test_run_cross_check_pomija_gdy_brak_klucza_openai():
    original = settings.openai_api_key
    settings.openai_api_key = None
    try:
        items = [_item("X", 1.0, None, "KOD_X")]
        with patch("app.modules.ocr.crosscheck.recognize_document") as mock_recognize:
            await run_cross_check(
                files=[(b"dane", "image/jpeg")], dzial="elektryka", catalog=None,
                magazyn=None, special_rules=None, items=items,
            )
        mock_recognize.assert_not_called()
        assert items[0]["needs_review"] is False
    finally:
        settings.openai_api_key = original


async def test_run_cross_check_flaguje_niezgodnosc_dla_elektryki():
    original = settings.openai_api_key
    settings.openai_api_key = "test-openai-key"
    try:
        items = [_item("Kinkiet Kanlux LED REKA 7W grafit", 1.0, None, "KINKIET KANLUX LED REKA 7W GRAFIT")]
        openai_result = OCRResult(
            numer_projektu=None,
            pozycje=[_pozycja("Kinkiet Kanlux LED REKA 7W grafit", "3", None, "KINKIET KANLUX LED REKA 7W GRAFIT")],
            used_provider="OpenAI (kontrola krzyżowa)", rejected_count=0,
        )
        with patch(
            "app.modules.ocr.crosscheck.recognize_document", new=AsyncMock(return_value=openai_result),
        ):
            await run_cross_check(
                files=[(b"dane", "image/jpeg")], dzial="elektryka", catalog=None,
                magazyn=None, special_rules=[], items=items,
            )
        assert items[0]["needs_review"] is True
    finally:
        settings.openai_api_key = original


async def test_run_cross_check_best_effort_przy_bledzie_nie_rzuca_wyjatku():
    original = settings.openai_api_key
    settings.openai_api_key = "test-openai-key"
    try:
        items = [_item("X", 1.0, None, "KOD_X")]
        with patch(
            "app.modules.ocr.crosscheck.recognize_document", new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await run_cross_check(
                files=[(b"dane", "image/jpeg")], dzial="elektryka", catalog=None,
                magazyn=None, special_rules=[], items=items,
            )
        assert items[0]["needs_review"] is False
    finally:
        settings.openai_api_key = original
