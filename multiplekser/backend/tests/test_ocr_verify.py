from unittest.mock import AsyncMock

from app.modules.ocr.chain import OCRChainStep
from app.modules.ocr.providers import OCRProvider
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

    results = await verify_ambiguous_quantities(
        [(b"caly-pdf", "application/pdf")], ["Pozycja A", "Pozycja B"], "elektryka",
    )

    assert [result.ilosc_wydana for result in results] == [2, 1]
    assert len(provider.calls) == 1
    # Zawsze caly, niezmieniony dokument - wycinanie konkretnych wierszy usuniete (patrz
    # docstring verify.py: uklad papierowej wydawki rozni sie za kazdym razem).
    assert provider.calls[0]["files"] == [(b"caly-pdf", "application/pdf")]
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
    result = await verify_ambiguous_quantities(
        [(b"dokument", "image/jpeg")], ["Pozycja A"], "hydraulika",
        event_callback=events.append,
    )

    assert result[0].found_anything is False
    assert [event["status"] for event in events] == ["attempt", "rejected", "no_result"]
    assert events[1]["reason"] == "model nie odczytal zadnej ilosci dla sprawdzanych pozycji"
    assert "Pozycja A" in str(events[2]["reason"])


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


async def test_obie_puste_ilosci_eskaluja_nawet_bez_quantity_marks(monkeypatch):
    """quantity_marks jest wygaszony u zrodla (pipeline_hydraulika.py juz go nie generuje,
    patrz docs/RAPORT_OCR_NIEZAWODNOSC_4.md) - pozycja z obiema pustymi iloscami eskaluje do
    kontroli na podstawie samej deklaracji glownego modelu, bez dodatkowej weryfikacji."""
    from app.modules.documents.tasks import _verify_ambiguous_items

    items = [{"rozpoznana_nazwa": "Pozycja A", "ilosc_wydana": None, "ilosc_zuzyta": None,
              "ilosc_finalna": None}]
    batch = AsyncMock(return_value=[VerifyResult(1, None)])
    monkeypatch.setattr("app.modules.documents.tasks.verify_ambiguous_quantities", batch)

    await _verify_ambiguous_items(
        [(b"pdf", "application/pdf")], items, "doc-1", lambda event: None,
        cooldown_store=object(), dzial="hydraulika",
    )

    batch.assert_awaited_once()
    assert batch.await_args.args[1] == ["Pozycja A"]
