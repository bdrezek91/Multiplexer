from io import BytesIO
from unittest.mock import AsyncMock

from PIL import Image, ImageDraw

from app.modules.ocr.chain import OCRChainStep
from app.modules.ocr.providers import OCRProvider
from app.modules.ocr.verification_image import prepare_verification_files
from app.modules.ocr.verify import VerifyResult, verify_ambiguous_quantities


class _FakeProvider(OCRProvider):
    def __init__(self, responses: list[str]):
        self.responses = iter(responses)
        self.calls: list[dict] = []

    async def recognize(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


async def test_jedno_zapytanie_obsluguje_wiele_pozycji(monkeypatch):
    provider = _FakeProvider([
        '{"pozycje":['
        '{"id":"1","ilosc_wydana":2,"ilosc_zuzyta":null},'
        '{"id":"2","ilosc_wydana":1,"ilosc_zuzyta":null}'
        ']}'
    ])
    monkeypatch.setattr(
        "app.modules.ocr.verify.default_ocr_chain",
        lambda: [OCRChainStep("Model pierwszy", provider, "model-a", "klucz")],
    )
    monkeypatch.setattr(
        "app.modules.ocr.verify.prepare_verification_files",
        lambda files, targets, dzial: ([(b"wycinki", "image/jpeg")], True),
    )

    results = await verify_ambiguous_quantities(
        [(b"caly-pdf", "application/pdf")], ["Pozycja A", "Pozycja B"], "elektryka",
    )

    assert [result.ilosc_wydana for result in results] == [2, 1]
    assert len(provider.calls) == 1
    assert provider.calls[0]["files"] == [(b"wycinki", "image/jpeg")]
    assert "Pozycja A" in provider.calls[0]["prompt"]
    assert "Pozycja B" in provider.calls[0]["prompt"]


async def test_null_przechodzi_do_nastepnego_modelu_tylko_dla_nierozpoznanej_pozycji(monkeypatch):
    first = _FakeProvider([
        '{"pozycje":['
        '{"id":"1","ilosc_wydana":2,"ilosc_zuzyta":null},'
        '{"id":"2","ilosc_wydana":null,"ilosc_zuzyta":null}'
        ']}'
    ])
    second = _FakeProvider([
        '{"pozycje":[{"id":"2","ilosc_wydana":1,"ilosc_zuzyta":null}]}'
    ])
    monkeypatch.setattr(
        "app.modules.ocr.verify.default_ocr_chain",
        lambda: [
            OCRChainStep("Model pierwszy", first, "model-a", "klucz-a"),
            OCRChainStep("Model drugi", second, "model-b", "klucz-b"),
        ],
    )
    monkeypatch.setattr(
        "app.modules.ocr.verify.prepare_verification_files",
        lambda files, targets, dzial: (files, False),
    )

    results = await verify_ambiguous_quantities(
        [(b"dokument", "image/jpeg")], ["Pozycja A", "Pozycja B"], "hydraulika",
    )

    assert [result.ilosc_wydana for result in results] == [2, 1]
    assert len(first.calls) == 1
    assert len(second.calls) == 1
    assert "Pozycja A" not in second.calls[0]["prompt"]
    assert "Pozycja B" in second.calls[0]["prompt"]


async def test_same_nulle_sa_odrzucone_i_log_konczy_sie_bez_wyniku(monkeypatch):
    provider = _FakeProvider([
        '{"pozycje":[{"id":"1","ilosc_wydana":null,"ilosc_zuzyta":null}]}'
    ])
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.modules.ocr.verify.default_ocr_chain",
        lambda: [OCRChainStep("Model pierwszy", provider, "model-a", "klucz")],
    )
    monkeypatch.setattr(
        "app.modules.ocr.verify.prepare_verification_files",
        lambda files, targets, dzial: (files, False),
    )

    result = await verify_ambiguous_quantities(
        [(b"dokument", "image/jpeg")], ["Pozycja A"], "hydraulika",
        event_callback=events.append,
    )

    assert result[0].found_anything is False
    assert [event["status"] for event in events] == ["attempt", "rejected", "no_result"]
    assert events[1]["reason"] == "model nie odczytal zadnej ilosci dla sprawdzanych pozycji"
    assert "Pozycja A" in str(events[2]["reason"])


def test_formularz_elektryczny_jest_zamieniany_na_jeden_obraz_z_wycinkiem():
    width, row_height, first_line, row_count = 1000, 30, 100, 48
    image = Image.new("RGB", (width, first_line + row_height * row_count + 100), "white")
    draw = ImageDraw.Draw(image)
    for row in range(row_count + 1):
        y = first_line + row * row_height
        draw.line((80, y, 850, y), fill="black", width=3)
    # Kilka pionowych krawedzi i znak w docelowym wierszu upodabniaja obraz do tabeli.
    for x in (80, 600, 720, 850):
        draw.line((x, first_line, x, first_line + row_height * row_count), fill="black", width=3)
    draw.text((640, first_line + 15 * row_height + 7), "2 V", fill="black")
    source = BytesIO()
    image.save(source, format="JPEG", quality=95)

    files, cropped = prepare_verification_files(
        [(source.getvalue(), "image/jpeg")],
        [("1", "Gniazdo podwójne polskie białe")],
        "elektryka",
    )

    assert cropped is True
    assert len(files) == 1
    assert files[0][1] == "image/jpeg"
    with Image.open(BytesIO(files[0][0])) as result:
        assert result.height < image.height
        assert result.width <= image.width + 20


async def test_task_wysyla_wszystkie_braki_jednym_wywolaniem_i_uzupelnia_items(monkeypatch):
    from app.modules.documents.tasks import _verify_ambiguous_items

    items = [
        {
            "rozpoznana_nazwa": "Pozycja A",
            "ilosc_wydana": None,
            "ilosc_zuzyta": None,
            "ilosc_finalna": None,
        },
        {
            "rozpoznana_nazwa": "Pozycja B",
            "ilosc_wydana": None,
            "ilosc_zuzyta": None,
            "ilosc_finalna": None,
        },
    ]
    batch = AsyncMock(return_value=[VerifyResult(2, None), VerifyResult(1, None)])
    monkeypatch.setattr("app.modules.documents.tasks.verify_ambiguous_quantities", batch)

    await _verify_ambiguous_items(
        [(b"pdf", "application/pdf")], items, "doc-1", lambda event: None,
        cooldown_store=object(), dzial="elektryka",
    )

    batch.assert_awaited_once()
    assert batch.await_args.args[:3] == (
        [(b"pdf", "application/pdf")], ["Pozycja A", "Pozycja B"], "elektryka",
    )
    assert [item["ilosc_finalna"] for item in items] == [2, 1]
