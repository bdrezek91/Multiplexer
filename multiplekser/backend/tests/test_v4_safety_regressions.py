"""Real regression cases found in the 2026-10-13 hydraulic issue sheet."""
import pytest
from app.modules.documents.auto_v3 import select_verify_targets
from app.modules.generator.safety_hydraulika import is_ignored_zas127, screw_code_safe
from app.modules.generator import GeneratorItem, generate_output_hydraulika


def test_opus_selector_never_adds_empty_third_page_after_three_rows():
    risky = [
        ({"nazwa":"Kolanko ścienne GW","page_number":1},object()),
        ({"nazwa":"Rura fi 40 30 cm","page_number":2},object()),
        ({"nazwa":"Mufa GZ","page_number":2},object()),
        ({"nazwa":"Rura fi 50 50 cm","page_number":3},object()),
    ]
    assert select_verify_targets(risky,3)=={
        1:["Kolanko ścienne GW"],
        2:["Rura fi 40 30 cm","Mufa GZ"],
    }


def test_opus_selector_can_accept_only_third_page():
    assert select_verify_targets([
        ({"nazwa":"Trójnik PP 20","page_number":3},object()),
    ],3)=={3:["Trójnik PP 20"]}


def test_opus_selector_handles_duplicate_names_and_invalid_pages():
    risky=[
        ({"nazwa":"Kolanko","page_number":0},object()),
        ({"nazwa":"Kolanko","page_number":1},object()),
        ({"nazwa":"Kolanko","page_number":1},object()),
        ({"nazwa":"Rura","page_number":-1},object()),
    ]
    assert select_verify_targets(risky,3)=={1:["Kolanko"]}


@pytest.mark.parametrize("name",[
    "ZAS 127","zas127","Zas 127","Zaślepka 127 czerwona",
])
def test_zas_127_is_excluded(name):
    assert is_ignored_zas127(name)


@pytest.mark.parametrize("name",[
    "Zaślepka fi 127","Zaślepka fi 10","ZAS 120","Wkręt 4x16",
])
def test_unrelated_material_is_not_excluded(name):
    assert not is_ignored_zas127(name)


def test_critical_screw_attributes_must_match():
    src="Wkręty RAL 9005 4x16"
    assert not screw_code_safe(src,"ZESTAW WKRĘTÓW DO HYDRAULIKI","Zestaw wkrętów do hydrauliki")
    assert not screw_code_safe(src,"WKRĘTY RAL 9005 4X20","Wkręty RAL 9005 4x20")
    assert not screw_code_safe(src,"WKRĘTY RAL 7016 4X16","Wkręty RAL 7016 4x16")
    assert screw_code_safe(src,"WKRĘTY RAL 9005 4X16","Wkręty RAL 9005 4x16")


def test_zas_127_never_reaches_txt(catalog_hydra):
    items=[GeneratorItem(name="ZAS 127",qty=1),
           GeneratorItem(name="Bojler 80 L",qty=2)]
    lines=generate_output_hydraulika(items,catalog_hydra,magazyn="Zabrze").lines
    assert not any("127" in line for line in lines)
    assert any("BOJLER" in line for line in lines)


def test_screw_cannot_export_as_generic_set(catalog_hydra):
    items=[GeneratorItem(name="Wkręty RAL 9005 4x16",qty=250,
         match_kod="ZESTAW WKRĘTÓW DO HYDRAULIKI",
         match_nazwa="Zestaw wkrętów do hydrauliki",
         match_quality="ok")]
    lines=generate_output_hydraulika(items,catalog_hydra,magazyn="Zabrze").lines
    assert len(lines)==1
    assert lines[0].startswith("### BRAK DOPASOWANIA")
    assert not lines[0].startswith("ZESTAW WKRĘTÓW")


@pytest.fixture(scope="module")
def catalog_hydra():
    import json
    from pathlib import Path
    from app.modules.products import Catalog
    p=Path(__file__).parent/"fixtures"/"baza_hydraulika.json"
    return Catalog.from_json_dict(json.loads(p.read_text(encoding="utf-8")),dzial="hydraulika")
