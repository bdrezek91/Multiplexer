"""Zbiorcza, semantyczna kontrola ilosci pominietych przez glowny OCR.

Wszystkie niejasne wiersze trafiaja do jednego zapytania na model, zawsze na PELNYM,
niezmienionym obrazie dokumentu (bez wycinania konkretnych wierszy - patrz nizej dlaczego).
Odpowiedz z samymi null NIE jest sukcesem: taki model zostaje odrzucony, a nierozpoznane
pozycje przechodza zbiorczo do nastepnego kroku lancucha.

Wczesniej ta funkcja (przez verification_image.py: prepare_verification_files) probowala
wycinac z obrazu konkretny wiersz na podstawie zakodowanego na sztywno, domniemanego ukladu
fizycznego kartki (numer strony + numer wiersza per nazwa pozycji). Usuniete calkowicie
(2026-08-31, na zyczenie uzytkownika) - papierowa wydawka rozni sie za kazdym razem (rozne
wersje formularza, rozne rewizje z biegiem czasu), wiec jakikolwiek sztywny uklad wierszy jest
z zalozenia niemozliwy do trwalego utrzymania. Trzy kolejne, coraz gorsze awarie tego samego typu
w Hydraulice (patrz docs/RAPORT_OCR_NIEZAWODNOSC_3.md, _4.md) i potwierdzone ~55% braku pokrycia
w mapie dla Elektryki (153 pozycje w aktualnym szablonie vs 69 w mapie wycinkow) pokazaly, ze to
nie byl przypadek do punktowej naprawy, tylko zle zalozenie architektoniczne. Kontrola dziala
teraz zawsze na pelnym obrazie - mniej precyzyjne "zoomowanie" przy bardzo zageszczonych
kartkach, ale zero ryzyka zlego dopasowania wiersza.

Lancuch (`quantity_verification_chain()`, patrz chain.py) jest na zyczenie uzytkownika (2026-08-07)
WYLACZNIE darmowy - pozycja, ktorej nie odczyta zaden z czterech darmowych modeli Gemini, zostaje
"Bez wyniku" (patrz `_publish_no_result`) i wymaga recznej weryfikacji na oryginale, bez placonego
fallbacku (inaczej niz `default_ocr_chain()` uzywany do pelnego odczytu calego dokumentu).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional

from .chain import (
    AllProvidersFailedError,
    OCRChainEventCallback,
    quantity_verification_chain,
    run_ocr_chain,
)
from .cooldown import OCRCooldownStore
from .parsing import extract_json, parse_float_loose

_NO_QUANTITY_REASON = "model nie odczytal zadnej ilosci dla sprawdzanych pozycji"


@dataclass
class VerifyResult:
    ilosc_wydana: Optional[float]
    ilosc_zuzyta: Optional[float]

    @property
    def found_anything(self) -> bool:
        return self.ilosc_wydana is not None or self.ilosc_zuzyta is not None


def _quantity(value: object) -> float | None:
    if value in (None, ""):
        return None
    parsed = parse_float_loose(value)
    return parsed if parsed is not None and parsed > 0 else None


def _parse_batch_response(text: str, expected_ids: set[str]) -> dict[str, VerifyResult]:
    parsed = extract_json(text)
    raw_items = parsed.get("pozycje") if isinstance(parsed, dict) else None
    if not isinstance(raw_items, list):
        return {}

    results: dict[str, VerifyResult] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id", "")).strip()
        if item_id not in expected_ids:
            continue
        result = VerifyResult(
            ilosc_wydana=_quantity(raw.get("ilosc_wydana")),
            ilosc_zuzyta=_quantity(raw.get("ilosc_zuzyta")),
        )
        if result.found_anything:
            results[item_id] = result
    return results


def _parse_group_response(text: str, expected_ids: set[str]) -> dict[str, VerifyResult]:
    """Jak _parse_batch_response, ale ZACHOWUJE jawne null-null - dla porownania grup
    (verify_row_group_alignment) rozroznienie "model potwierdzil brak wartosci" od "model w
    ogole nie odpowiedzial na to ID" (blad parsowania/przyciecie odpowiedzi) ma znaczenie,
    inaczej niz przy zwyklej weryfikacji niejasnych pozycji (_parse_batch_response), gdzie
    interesuje nas tylko czy cokolwiek znaleziono."""
    parsed = extract_json(text)
    raw_items = parsed.get("pozycje") if isinstance(parsed, dict) else None
    if not isinstance(raw_items, list):
        return {}

    results: dict[str, VerifyResult] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id", "")).strip()
        if item_id not in expected_ids:
            continue
        results[item_id] = VerifyResult(
            ilosc_wydana=_quantity(raw.get("ilosc_wydana")),
            ilosc_zuzyta=_quantity(raw.get("ilosc_zuzyta")),
        )
    return results


def _build_prompt(targets: list[tuple[str, str]], cropped: bool) -> str:
    target_lines = "\n".join(f'- ID {item_id}: "{name.replace(chr(34), chr(39))}"' for item_id, name in targets)
    source_hint = (
        "Otrzymujesz jeden obraz z osobnymi wycinkami. Kazdy wycinek ma etykiete 'Cel ID'. "
        "Kazdy wycinek zawiera WYLACZNIE jeden docelowy wiersz: jego nazwe i komorki ilosci. "
        "Nie ma na nim wierszy sasiednich."
        if cropped else
        "Otrzymujesz oryginalny dokument. Znajdz ponizsze wiersze po pelnej nazwie; podobne "
        "wiersze obok nie sa tym samym materialem."
    )
    return f"""Jestes przemyslowym silnikiem OCR do dokumentow magazynowych.
{source_hint}

Sprawdz WYŁĄCZNIE te pozycje:
{target_lines}

Dla kazdego ID odczytaj OSOBNO kolumny "Ilosc wydana" i "Ilosc zuzyta". Ptaszek/haczyk/V/✓
nie jest liczba, ale cyfra i ptaszek czesto stoja razem. Jesli obok ptaszka widac odrebna cyfre
(takze 1), zwroc te cyfre. Nie przenos wartosci z sasiedniego wiersza.

Zwroc WYLACZNIE JSON, zachowujac ID:
{{"pozycje":[{{"id":"1","ilosc_wydana":2,"ilosc_zuzyta":null}}]}}
Jesli dla konkretnego ID naprawde nie ma czytelnej cyfry, zwroc dla niego oba pola null."""


# Druga, niezalezna kontrola dla GRUP niemal identycznych wierszy (row_groups.py) - 2026-09-17,
# realny przypadek produkcyjny: model przypisal ilosc nalezaca do "Przewod 3x4" do sasiedniego
# "Przewod 3x1,5". W przeciwienstwie do _build_prompt (pojedyncze niejasne pozycje), to pytanie
# dostaje od razu CALA grupe podobnych etykiet i explicite ostrzega przed pomyleniem miedzy JEJ
# czlonkami - waskie, ukierunkowane pytanie, nie pelny ponowny odczyt calego dokumentu (taki byl
# juz probowany jako niezalezny cross-check OpenAI i porzucony z powodu duzego szumu, patrz git
# historia ocr/crosscheck.py - stad tu inny dostawca NIE jest uzywany, tylko ten sam, sprawdzony
# darmowy lancuch Gemini co reszta kontroli w tym pliku).
def _build_group_prompt(groups: list[list[str]], id_by_label: dict[str, str]) -> str:
    group_blocks = []
    for group_index, members in enumerate(groups, start=1):
        lines = "\n".join(
            f'  - ID {id_by_label[label]}: "{label.replace(chr(34), chr(39))}"' for label in members
        )
        group_blocks.append(f"GRUPA {group_index} (niemal identyczne etykiety, latwo je pomylic):\n{lines}")
    groups_text = "\n\n".join(group_blocks)
    return f"""Jestes przemyslowym silnikiem OCR do dokumentow magazynowych.
Otrzymujesz oryginalny dokument (pelny obraz, bez wycinkow).

Ponizej sa GRUPY wierszy formularza, ktore roznia sie MIEDZY SOBA tylko liczba/wymiarem/
przekrojem (np. "Przewod 3x1,5" vs "Przewod 3x4") - to NAJCZESTSZE miejsce pomylki: latwo
przypisac zaznaczenie/ilosc z jednego wiersza grupy do SASIEDNIEGO wiersza tej samej grupy.
W jednej grupie MOZE byc wypelnionych kilka wierszy naraz (to NIE jest wybor "dokladnie jeden z
listy") - kazdy wiersz kazdej grupy odczytaj OSOBNO i NIEZALEZNIE, tak jakbys nie widzial reszty
grupy, ale zanim zwrocisz wynik dla danego ID, POLICZ wiersze OD GORY jego grupy do wiersza z
zaznaczeniem, zeby miec pewnosc ze nie jest to o jeden lub dwa wiersze za wysoko/za nisko:

{groups_text}

Dla kazdego ID odczytaj OSOBNO kolumny "Ilosc wydana" i "Ilosc zuzyta". Ptaszek/haczyk/V/✓ nie
jest liczba, ale cyfra i ptaszek czesto stoja razem - jesli obok ptaszka widac odrebna cyfre
(takze 1), zwroc te cyfre. Jesli dla danego ID nie ma zadnego sladu wartosci - zwroc null, NIE
kopiuj wartosci z sasiedniego wiersza tej samej ani innej grupy.

Zwroc WYLACZNIE JSON, zachowujac ID, dla WSZYSTKICH podanych ID (rowniez tych z null):
{{"pozycje":[{{"id":"1","ilosc_wydana":2,"ilosc_zuzyta":null}}]}}"""


async def verify_row_group_alignment(
    files: list[tuple[bytes, str]],
    groups: list[list[str]],
    log_context: Optional[Mapping[str, object]] = None,
    event_callback: Optional[OCRChainEventCallback] = None,
    cooldown_store: Optional[OCRCooldownStore] = None,
) -> dict[str, VerifyResult]:
    """Zwraca ilosc dla KAZDEJ etykiety KAZDEJ przekazanej grupy (klucz = etykieta), niezaleznie
    czy glowny odczyt cokolwiek dla niej znalazl - wynik sluzy do porownania z glownym odczytem
    w tasks.py i wykrycia rozbieznosci (sygnal przesuniecia wiersza), nie do bezposredniego
    nadpisania danych. Puste `groups` -> pusty wynik bez zadnego zapytania (brak ryzykownych
    grup w tym dokumencie)."""
    labels = [label for group in groups for label in group]
    if not labels:
        return {}

    id_by_label = {label: str(index + 1) for index, label in enumerate(labels)}
    label_by_id = {item_id: label for label, item_id in id_by_label.items()}
    expected_ids = set(label_by_id)
    prompt = _build_group_prompt(groups, id_by_label)
    target_label = ", ".join(labels)[:500]

    # Walidacja wymaga odpowiedzi dla WSZYSTKICH ID (nie tylko tych z wartoscia, w
    # przeciwienstwie do _parse_batch_response) - polprodukt (np. tylko czesc grupy) jest tu
    # bezuzyteczny do rzetelnego porownania z glownym odczytem, wiec lepiej przejsc do
    # kolejnego kroku lancucha niz zaakceptowac niepelna odpowiedz.
    try:
        chain_result = await run_ocr_chain(
            files, prompt, chain=quantity_verification_chain(),
            response_validator=lambda text: expected_ids.issubset(_parse_group_response(text, expected_ids)),
            log_context={**dict(log_context or {}), "ai_stage": "row_group_verification", "ai_target": target_label},
            event_callback=event_callback,
            cooldown_store=cooldown_store,
            invalid_response_reason=_NO_QUANTITY_REASON,
            publish_terminal_failure=False,
        )
    except AllProvidersFailedError:
        return {}

    parsed = _parse_group_response(chain_result.text, expected_ids)
    return {label_by_id[item_id]: result for item_id, result in parsed.items()}


def _publish_no_result(
    unresolved: list[tuple[str, str]], event_callback: Optional[OCRChainEventCallback],
) -> None:
    if not unresolved or event_callback is None:
        return
    names = ", ".join(name for _, name in unresolved)
    try:
        event_callback({
            "status": "no_result",
            "stage": "quantity_verification",
            "provider": None,
            "model": None,
            "label": None,
            "reason": f"Nie znaleziono ilosci dla: {names}",
            "step": None,
            "total_steps": None,
            "duration_ms": None,
            "attempt": None,
            "target": names,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        # To tylko log dla UI; zapis nie moze uniewaznic poprawnie zakonczonego OCR.
        return


async def verify_ambiguous_quantities(
    files: list[tuple[bytes, str]], names: list[str], dzial: str,
    log_context: Optional[Mapping[str, object]] = None,
    event_callback: Optional[OCRChainEventCallback] = None,
    cooldown_store: Optional[OCRCooldownStore] = None,
) -> list[VerifyResult]:
    """Sprawdza wszystkie nazwy zbiorczo i zwraca wyniki w tej samej kolejnosci."""
    targets = [(str(index + 1), name) for index, name in enumerate(names)]
    if not targets:
        return []

    # Zawsze pelny, niezmieniony obraz - patrz docstring modulu, dlaczego wycinanie
    # konkretnych wierszy zostalo calkowicie usuniete.
    verification_files, cropped = files, False
    unresolved = dict(targets)
    found: dict[str, VerifyResult] = {}
    steps = quantity_verification_chain()

    for step_index, step in enumerate(steps):
        if not unresolved:
            break
        current_targets = list(unresolved.items())
        expected_ids = set(unresolved)
        prompt = _build_prompt(current_targets, cropped)
        target_label = ", ".join(unresolved.values())[:500]
        try:
            chain_result = await run_ocr_chain(
                verification_files,
                prompt,
                chain=[step],
                response_validator=lambda text, ids=expected_ids: bool(
                    _parse_batch_response(text, ids)
                ),
                log_context={
                    **dict(log_context or {}),
                    "ai_stage": "quantity_verification",
                    "ai_target": target_label,
                },
                event_callback=event_callback,
                cooldown_store=cooldown_store,
                invalid_response_reason=_NO_QUANTITY_REASON,
                chain_position_offset=step_index,
                chain_total_steps=len(steps),
                publish_terminal_failure=False,
            )
        except AllProvidersFailedError:
            continue

        parsed_results = _parse_batch_response(chain_result.text, expected_ids)
        for item_id, result in parsed_results.items():
            found[item_id] = result
            unresolved.pop(item_id, None)

    _publish_no_result(list(unresolved.items()), event_callback)
    return [found.get(item_id, VerifyResult(None, None)) for item_id, _ in targets]


async def verify_ambiguous_quantity(
    files: list[tuple[bytes, str]], nazwa: str,
    log_context: Optional[Mapping[str, object]] = None,
    event_callback: Optional[OCRChainEventCallback] = None,
    cooldown_store: Optional[OCRCooldownStore] = None,
) -> VerifyResult:
    """Wstecznie zgodny wrapper dla pojedynczego wiersza."""
    results = await verify_ambiguous_quantities(
        files, [nazwa], "elektryka", log_context, event_callback, cooldown_store,
    )
    return results[0]
