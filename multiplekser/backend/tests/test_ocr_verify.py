from io import BytesIO
from unittest.mock import AsyncMock

from PIL import Image, ImageDraw

from app.modules.ocr.chain import OCRChainStep
from app.modules.ocr.providers import OCRProvider
from app.modules.ocr.verification_image import (
    discover_hydraulika_quantity_marks,
    discover_marked_hydraulika_rows,
    prepare_verification_files,
)
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
        "app.modules.ocr.verify.quantity_verification_chain",
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
        "app.modules.ocr.verify.quantity_verification_chain",
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
        "app.modules.ocr.verify.quantity_verification_chain",
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
        # Naglowek celu + tylko jeden wiersz tabeli; sasiednie wiersze nie moga wejsc do obrazu.
        assert result.height < 120
        assert result.width <= image.width + 20


def test_hydraulika_wykrywa_niebieski_znak_i_wycina_tylko_docelowy_wiersz():
    width, row_height, first_line, row_count = 1000, 30, 100, 44
    image = Image.new("RGB", (width, first_line + row_height * row_count + 100), "white")
    draw = ImageDraw.Draw(image)
    for row in range(row_count + 1):
        y = first_line + row * row_height
        draw.line((80, y, 850, y), fill="black", width=3)
    for x in (80, 390, 600, 720, 850):
        draw.line((x, first_line, x, first_line + row_height * row_count), fill="black", width=3)
    # Bateria umywalkowa jest szostym wierszem po pieciu wierszach naglowka.
    draw.text((430, first_line + 6 * row_height + 7), "1 V", fill=(20, 40, 210))
    source = BytesIO()
    image.save(source, format="JPEG", quality=95)
    input_files = [(source.getvalue(), "image/jpeg")]

    assert "Bateria umywalkowa" in discover_marked_hydraulika_rows(input_files)
    assert discover_hydraulika_quantity_marks(input_files)["Bateria umywalkowa"] == (True, False)
    files, cropped = prepare_verification_files(
        input_files, [("1", "Bateria umywalkowa")], "hydraulika",
    )

    assert cropped is True
    with Image.open(BytesIO(files[0][0])) as result:
        assert result.height < 120


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


async def test_task_nie_ucina_kontroli_po_pierwszych_osmiu_pozycjach(monkeypatch):
    from app.modules.documents.tasks import _verify_ambiguous_items

    items = [{
        "rozpoznana_nazwa": f"Pozycja {index}",
        "ilosc_wydana": None,
        "ilosc_zuzyta": None,
        "ilosc_finalna": None,
    } for index in range(10)]
    batch = AsyncMock(return_value=[VerifyResult(index + 1, None) for index in range(10)])
    monkeypatch.setattr("app.modules.documents.tasks.verify_ambiguous_quantities", batch)

    await _verify_ambiguous_items(
        [(b"pdf", "application/pdf")], items, "doc-1", lambda event: None,
        cooldown_store=object(), dzial="hydraulika",
    )

    assert len(batch.await_args.args[1]) == 10
    assert [item["ilosc_finalna"] for item in items] == list(range(1, 11))


async def test_task_uzupelnia_jedna_brakujaca_kolumne_i_nie_nadpisuje_odczytanej(monkeypatch):
    from app.modules.documents.tasks import _verify_ambiguous_items

    items = [
        {"rozpoznana_nazwa": "Pozycja A", "ilosc_wydana": None, "ilosc_zuzyta": 1,
         "ilosc_finalna": 1},
        {"rozpoznana_nazwa": "Pozycja B", "ilosc_wydana": 2, "ilosc_zuzyta": None,
         "ilosc_finalna": 2},
        {"rozpoznana_nazwa": "Pozycja C", "ilosc_wydana": None, "ilosc_zuzyta": 4,
         "ilosc_finalna": 4},
    ]
    batch = AsyncMock(return_value=[VerifyResult(1, 99), VerifyResult(9, 3)])
    monkeypatch.setattr("app.modules.documents.tasks.verify_ambiguous_quantities", batch)

    await _verify_ambiguous_items(
        [(b"pdf", "application/pdf")], items, "doc-1", lambda event: None,
        cooldown_store=object(), dzial="hydraulika",
        quantity_marks={
            "Pozycja A": (True, True),
            "Pozycja B": (True, True),
            # Wydana jest pusta i nie ma w niej znaku - tej pozycji nie kontrolujemy.
            "Pozycja C": (False, True),
        },
    )

    assert batch.await_args.args[1] == ["Pozycja A", "Pozycja B"]
    assert items[0]["ilosc_wydana"] == 1
    assert items[0]["ilosc_zuzyta"] == 1  # nie 99 z kontrolnego modelu
    assert items[1]["ilosc_wydana"] == 2  # nie 9 z kontrolnego modelu
    assert items[1]["ilosc_zuzyta"] == 3
    assert items[2]["ilosc_wydana"] is None


async def test_obie_puste_ilosci_bez_potwierdzenia_pikseli_pomijaja_kontrole(monkeypatch):
    """Glowny model zglosil ma_oznaczenie=true (stad pozycja w ogole istnieje z pustymi
    iloscami), ale pikselowy detektor przejrzal ta strone i nic tu nie znalazl - to falszywy
    alarm modelu na zabalaganionej kartce (skreslenia/poprawki), nie warto placic za kontrole."""
    from app.modules.documents.tasks import _verify_ambiguous_items

    items = [
        {"rozpoznana_nazwa": "Pozycja zaznaczona", "ilosc_wydana": None, "ilosc_zuzyta": None,
         "ilosc_finalna": None},
        {"rozpoznana_nazwa": "Pozycja pusta", "ilosc_wydana": None, "ilosc_zuzyta": None,
         "ilosc_finalna": None},
    ]
    batch = AsyncMock(return_value=[VerifyResult(3, None)])
    monkeypatch.setattr("app.modules.documents.tasks.verify_ambiguous_quantities", batch)

    await _verify_ambiguous_items(
        [(b"pdf", "application/pdf")], items, "doc-1", lambda event: None,
        cooldown_store=object(), dzial="hydraulika",
        quantity_marks={"Pozycja zaznaczona": (True, False)},
    )

    batch.assert_awaited_once()
    assert batch.await_args.args[1] == ["Pozycja zaznaczona"]
    assert items[0]["ilosc_finalna"] == 3
    assert items[1]["ilosc_wydana"] is None
    assert items[1]["ilosc_finalna"] is None


async def test_obie_puste_ilosci_ufaja_modelowi_gdy_detektor_nic_nie_znalazl_na_dokumencie(monkeypatch):
    """Pusty slownik quantity_marks (detektor nie znalazl ani jednego zaznaczenia na calym
    dokumencie) zwykle znaczy, ze nie zdazyl przeanalizowac strony (np. przeplatane puste
    strony skanu, patrz RAPORT_OCR_NIEZAWODNOSC_3) - wtedy nie ma czym potwierdzac, wracamy do
    zaufania modelowi jak przed ta zmiana."""
    from app.modules.documents.tasks import _verify_ambiguous_items

    items = [{"rozpoznana_nazwa": "Pozycja A", "ilosc_wydana": None, "ilosc_zuzyta": None,
              "ilosc_finalna": None}]
    batch = AsyncMock(return_value=[VerifyResult(1, None)])
    monkeypatch.setattr("app.modules.documents.tasks.verify_ambiguous_quantities", batch)

    await _verify_ambiguous_items(
        [(b"pdf", "application/pdf")], items, "doc-1", lambda event: None,
        cooldown_store=object(), dzial="hydraulika", quantity_marks={},
    )

    batch.assert_awaited_once()
    assert batch.await_args.args[1] == ["Pozycja A"]
