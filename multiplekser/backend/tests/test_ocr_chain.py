"""Testy Etapu 6: run_ocr_chain() - port AI_CHAIN + petli prob w runAI() z monolitu."""
import pytest

from app.modules.ocr.chain import (
    AllProvidersFailedError,
    OCRChainStep,
    default_ocr_chain,
    run_ocr_chain,
)
from app.modules.ocr.providers import GeminiProvider, OCRProvider, OCRProviderError, OpenAIProvider


class _FakeProvider(OCRProvider):
    def __init__(self, behavior):
        self.behavior = behavior  # callable(model) -> str | raises OCRProviderError
        self.calls: list[str] = []

    async def recognize(self, *, files, model, api_key, prompt, thinking_level="medium"):
        self.calls.append(model)
        return self.behavior(model)


async def test_default_chain_ma_gemini_x4_darmowy_gemini_platny_openai_platny():
    """Cztery modele Gemini na kluczu darmowym, potem platny Gemini i OpenAI jako ostatni fallback."""
    chain = default_ocr_chain()
    assert len(chain) == 6
    gemini_steps = [s for s in chain if isinstance(s.provider, GeminiProvider)]
    openai_steps = [s for s in chain if isinstance(s.provider, OpenAIProvider)]
    assert len(gemini_steps) == 5
    assert len(openai_steps) == 1
    assert openai_steps[0] is chain[-1]  # OpenAI zawsze na koncu - ostatni fallback

    assert [s.model for s in gemini_steps] == [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
    ]

    free_steps = [s for s in chain if "darmowy" in s.label]
    paid_steps = [s for s in chain if "platny" in s.label]
    assert len(free_steps) == 4
    assert len(paid_steps) == 2  # Gemini platny + OpenAI platny


async def test_brak_zadnego_klucza_rzuca_z_jasnym_komunikatem():
    steps = [OCRChainStep("Krok bez klucza", _FakeProvider(lambda m: "x"), "model-a", None)]
    with pytest.raises(AllProvidersFailedError, match="Nie podano"):
        await run_ocr_chain([(b"dane", "image/jpeg")], "prompt", chain=steps)


async def test_pierwszy_dostawca_z_kluczem_wygrywa():
    provider = _FakeProvider(lambda m: '{"pozycje": []}')
    steps = [OCRChainStep("Krok 1", provider, "model-a", "klucz")]
    result = await run_ocr_chain([(b"dane", "image/jpeg")], "prompt", chain=steps)
    assert result.text == '{"pozycje": []}'
    assert result.used_label == "Krok 1"


async def test_blad_pierwszego_kroku_przelacza_na_kolejny():
    def behavior(model):
        if model == "model-a":
            raise OCRProviderError("429 rate limited")
        return "OK z model-b"

    provider = _FakeProvider(behavior)
    steps = [
        OCRChainStep("Krok 1", provider, "model-a", "klucz-1"),
        OCRChainStep("Krok 2", provider, "model-b", "klucz-2"),
    ]
    result = await run_ocr_chain([(b"dane", "image/jpeg")], "prompt", chain=steps)
    assert result.text == "OK z model-b"
    assert result.used_label == "Krok 2"
    assert provider.calls == ["model-a", "model-b"]


async def test_niepoprawna_odpowiedz_pierwszego_kroku_przelacza_na_kolejny():
    provider = _FakeProvider(
        lambda model: "to nie jest JSON" if model == "model-a" else '{"pozycje": []}'
    )
    steps = [
        OCRChainStep("Krok 1", provider, "model-a", "klucz-1"),
        OCRChainStep("Krok 2", provider, "model-b", "klucz-2"),
    ]
    result = await run_ocr_chain(
        [(b"dane", "image/jpeg")], "prompt", chain=steps,
        response_validator=lambda text: text.startswith("{"),
    )
    assert result.text == '{"pozycje": []}'
    assert result.used_label == "Krok 2"
    assert provider.calls == ["model-a", "model-b"]


async def test_krok_bez_klucza_jest_pomijany_nie_liczy_sie_jako_blad():
    provider = _FakeProvider(lambda m: "OK")
    steps = [
        OCRChainStep("Krok bez klucza", provider, "model-a", None),
        OCRChainStep("Krok z kluczem", provider, "model-b", "klucz"),
    ]
    result = await run_ocr_chain([(b"dane", "image/jpeg")], "prompt", chain=steps)
    assert result.used_label == "Krok z kluczem"
    assert provider.calls == ["model-b"]  # pominiety krok wcale nie wywolal recognize()


async def test_wszyscy_dostawcy_zawiedli_zawiera_ostatni_blad_i_pominiete():
    provider = _FakeProvider(lambda m: (_ for _ in ()).throw(OCRProviderError(f"blad {m}")))
    steps = [
        OCRChainStep("Bez klucza", provider, "model-x", None),
        OCRChainStep("Zawodzi", provider, "model-y", "klucz"),
    ]
    with pytest.raises(AllProvidersFailedError) as exc_info:
        await run_ocr_chain([(b"dane", "image/jpeg")], "prompt", chain=steps)
    assert "blad model-y" in str(exc_info.value)
    assert "Bez klucza" in str(exc_info.value)


async def test_loguje_start_odrzucenie_powod_i_wybrany_model(caplog):
    def behavior(model):
        if model == "model-a":
            raise OCRProviderError("API 429: limit zapytan")
        return '{"pozycje": []}'

    provider = _FakeProvider(behavior)
    steps = [
        OCRChainStep("Model pierwszy", provider, "model-a", "sekretny-klucz-a"),
        OCRChainStep("Model drugi", provider, "model-b", "sekretny-klucz-b"),
    ]
    events: list[dict[str, object]] = []

    with caplog.at_level("INFO", logger="app.modules.ocr.chain"):
        await run_ocr_chain(
            [(b"dane", "image/jpeg")], "tajny prompt", chain=steps,
            log_context={"document_id": "doc-123", "ai_stage": "full_ocr_elektryka"},
            event_callback=events.append,
        )

    start = next(record for record in caplog.records if record.message == "OCR AI - start lancucha modeli")
    rejected = next(record for record in caplog.records if record.message == "OCR AI - model odrzucony")
    selected = next(record for record in caplog.records if record.message == "OCR AI - wybrano model")

    assert start.first_ai_model == "model-a"
    assert start.document_id == "doc-123"
    assert rejected.ai_model == "model-a"
    assert rejected.reason == "API 429: limit zapytan"
    assert selected.ai_model == "model-b"
    assert selected.ai_provider == "_Fake"
    assert selected.ai_stage == "full_ocr_elektryka"
    assert [event["status"] for event in events] == ["attempt", "rejected", "attempt", "selected"]
    assert events[1]["model"] == "model-a"
    assert events[1]["reason"] == "API 429: limit zapytan"
    assert events[3]["model"] == "model-b"

    rendered_data = repr([record.__dict__ for record in caplog.records]) + repr(events)
    assert "sekretny-klucz" not in rendered_data
    assert "tajny prompt" not in rendered_data


async def test_loguje_odrzucenie_odpowiedzi_przez_walidator(caplog):
    provider = _FakeProvider(
        lambda model: "niepoprawny tekst" if model == "model-a" else '{"pozycje": []}'
    )
    steps = [
        OCRChainStep("Model pierwszy", provider, "model-a", "klucz-a"),
        OCRChainStep("Model drugi", provider, "model-b", "klucz-b"),
    ]

    with caplog.at_level("INFO", logger="app.modules.ocr.chain"):
        await run_ocr_chain(
            [(b"dane", "image/jpeg")], "prompt", chain=steps,
            response_validator=lambda text: text.startswith("{"),
        )

    rejected = next(
        record for record in caplog.records
        if record.message == "OCR AI - odpowiedz modelu odrzucona"
    )
    assert rejected.ai_model == "model-a"
    assert rejected.reason == "odpowiedz nie spelnia wymagan formatu lub schematu"
    assert rejected.error_type == "ResponseValidationError"
