"""V4 shadow contract tests. No live requests or writes."""
import asyncio
from app.modules.documents import auto_v4


class FakeResponse:
    is_success = True
    status_code = 200
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


class FakeClient:
    def __init__(self, payload, received, *args, **kwargs):
        self.payload, self.received = payload, received
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def post(self, url, json, headers):
        self.received.append((url,json,headers))
        return FakeResponse(self.payload)


def sample_rows(dzial="hydraulika"):
    words = ("Kolanko fi 20", "Rura 20", "Syfon") if dzial == "hydraulika" else ("Przewód", "Gniazdo", "Rozdzielnia")
    return {"dzial": dzial, "numer_projektu":"7/10/26", "pracownik":"Test",
            "pozycje":[{"nazwa": name,"jm":"szt","ilosc_wydana":1,"ilosc_zuzyta":1,
                        "ilosc_wydana_raw":"1","ilosc_zuzyta_raw":"1",
                        "ma_oznaczenie":True,"strona":1} for name in words]}


def run(fake_payload, monkeypatch, model="gemini-3.5-flash-lite", thinking="minimal"):
    captured = []
    monkeypatch.setattr(auto_v4.httpx, "AsyncClient", lambda *args, **kwargs: FakeClient(fake_payload, captured))
    result=asyncio.run(auto_v4.shadow_one_pass([(b"jpeg-bytes", "image/jpeg")], model=model,
                 thinking=thinking, api_key="KEY-UNIT-TEST"))
    return result, captured


def test_shadow_returns_valid_hydraulic_rows_and_schema(monkeypatch):
    import json
    payload={"candidates":[{"content":{"parts":[{"text":json.dumps(sample_rows())}]}}]}
    result, captured=run(payload,monkeypatch)
    assert result.dzial=="hydraulika" and len(result.rows)==3
    assert captured[0][1]["generationConfig"]["responseMimeType"]=="application/json"
    assert captured[0][1]["generationConfig"]["responseJsonSchema"]==auto_v4.V4_SCHEMA
    assert captured[0][1]["generationConfig"]["thinkingConfig"]["thinkingLevel"]=="minimal"
    assert "KEY-UNIT-TEST" not in str(captured[0][1])


def test_shadow_returns_valid_electric_rows(monkeypatch):
    import json
    result,_=run({"candidates":[{"content":{"parts":[{"text":json.dumps(sample_rows("elektryka"))}]}}]},monkeypatch)
    assert result.dzial=="elektryka"


def test_shadow_rejects_inconsistent_department(monkeypatch):
    import json, pytest
    data=sample_rows("hydraulika");data["dzial"]="elektryka"
    with pytest.raises(auto_v4.AmbiguousDepartment):
        run({"candidates":[{"content":{"parts":[{"text":json.dumps(data)}]}}]},monkeypatch)


def test_shadow_rejects_category_based_only_on_model_hint(monkeypatch):
    import json, pytest
    data=sample_rows();data["pozycje"]=data["pozycje"][:1]
    with pytest.raises(auto_v4.AmbiguousDepartment):
        run({"candidates":[{"content":{"parts":[{"text":json.dumps(data)}]}}]},monkeypatch)


def test_shadow_rejects_empty_rows(monkeypatch):
    import json, pytest
    data=sample_rows();data["pozycje"]=[]
    with pytest.raises(auto_v4.AmbiguousDepartment):
        run({"candidates":[{"content":{"parts":[{"text":json.dumps(data)}]}}]},monkeypatch)


def test_v4_flash38_never_requests_unsupported_minimal():
    import pytest
    with pytest.raises(ValueError):
        asyncio.run(auto_v4.shadow_one_pass([(b"image","image/jpeg")],model="gemini-3.8-flash",
                                                  thinking="minimal", api_key="UNIT-TEST"))


def test_v4_25_lite_disables_thinking_with_budget_zero(monkeypatch):
    import json
    result, captured = run(
        {"candidates":[{"content":{"parts":[{"text":json.dumps(sample_rows())}]}}]},
        monkeypatch, model="gemini-2.5-flash-lite", thinking="off")
    assert len(result.rows)==3
    assert captured[0][1]["generationConfig"]["thinkingConfig"] == {"thinkingBudget":0}


def test_v4_25_lite_rejects_3x_thinking_levels():
    import pytest
    with pytest.raises(ValueError):
        asyncio.run(auto_v4.shadow_one_pass([(b"image","image/jpeg")],
            model="gemini-2.5-flash-lite", thinking="minimal", api_key="UNIT-TEST"))


def test_v4_never_allows_unknown_models():
    import pytest
    with pytest.raises(ValueError):
        asyncio.run(auto_v4.shadow_one_pass([(b"image","image/jpeg")],model="untrusted-model",
                                                  api_key="UNIT-TEST"))
