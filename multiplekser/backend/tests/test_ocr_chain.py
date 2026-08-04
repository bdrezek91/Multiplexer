"""Testy Etapu 6: run_ocr_chain() - port AI_CHAIN + petli prob w runAI() z monolitu."""
import pytest

from app.modules.ocr.chain import (
    AllProvidersFailedError,
    OCRChainStep,
    default_ocr_chain,
    run_ocr_chain,
)
from app.modules.ocr.providers import GeminiProvider, OCRProvider, OCRProviderError


class _FakeProvider(OCRProvider):
    def __init__(self, behavior):
        self.behavior = behavior  # callable(model) -> str | raises OCRProviderError
        self.calls: list[str] = []

    async def recognize(self, *, files, model, api_key, prompt):
        self.calls.append(model)
        return self.behavior(model)


async def test_default_chain_ma_5_krokow_jak_ai_chain_w_monolicie():
    chain = default_ocr_chain()
    assert len(chain) == 5
    assert all(isinstance(step.provider, GeminiProvider) for step in chain)
    # 4 kroki na kluczu darmowym + 1 na platnym (dokladnie jak AI_CHAIN)
    free_steps = [s for s in chain if "darmowy" in s.label]
    paid_steps = [s for s in chain if "platny" in s.label]
    assert len(free_steps) == 4
    assert len(paid_steps) == 1


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
