"""Testy formattera JSON (Etap "quick winy" - strukturalne logowanie, 2026-07-30)."""
import json
import logging

from app.core.logging_config import JsonFormatter


def _make_record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="testowa wiadomosc %s", args=("z parametrem",), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatuje_podstawowe_pola_jako_json():
    payload = json.loads(JsonFormatter().format(_make_record()))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "testowa wiadomosc z parametrem"
    assert "timestamp" in payload


def test_dolacza_pola_z_extra():
    payload = json.loads(JsonFormatter().format(_make_record(user_id="abc-123", email="a@b.pl")))
    assert payload["user_id"] == "abc-123"
    assert payload["email"] == "a@b.pl"


def test_dolacza_traceback_przy_wyjatku():
    try:
        raise ValueError("cos poszlo nie tak")
    except ValueError:
        import sys
        record = _make_record()
        record.exc_info = sys.exc_info()
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: cos poszlo nie tak" in payload["exception"]


def test_nie_wywala_sie_na_niesrializowalnej_wartosci_w_extra():
    payload = json.loads(JsonFormatter().format(_make_record(dziwna_wartosc=object())))
    assert "dziwna_wartosc" in payload  # default=str w json.dumps - nie rzuca wyjatku
