from datetime import datetime

import pytest

from mifugo import llm
from mifugo.clock import NAIROBI
from mifugo.log_parser import parse, scan_intent

NOW = datetime(2026, 10, 28, 9, 30, tzinfo=NAIROBI)
HERD = ["Njeri", "Baraka", "Wanjiru"]


@pytest.fixture
def no_model():
    llm.set_backend(llm.NoModel())
    yield
    llm.set_backend(None)


def scripted(reply):
    fake = llm.ScriptedBackend(lambda s, u, imgs: reply)
    llm.set_backend(fake)
    return fake


@pytest.fixture(autouse=True)
def _reset():
    yield
    llm.set_backend(None)


def test_model_reply_is_mapped_onto_the_herd():
    scripted({
        "intent": "log_treatment", "animal_names": ["njeri"], "product_mention": "Mastitis tube",
        "when": "yesterday_evening", "days_ago": 0, "clock": "",
    })
    p = parse("Nimemdunga Njeri sindano jana jioni", HERD, NOW)
    assert p.intent == "log_treatment"
    assert p.animals == ["Njeri"]
    assert p.given_at.at == datetime(2026, 10, 27, 20, 59, tzinfo=NAIROBI)


def test_an_unknown_name_is_reported_not_invented():
    scripted({
        "intent": "log_treatment", "animal_names": ["Kamau"], "product_mention": "",
        "when": "now", "days_ago": 0, "clock": "",
    })
    p = parse("Kamau amepewa dawa", HERD, NOW)
    assert p.animals == []
    assert p.unmatched == ["Kamau"]


def test_close_spelling_matches_the_herd():
    scripted({
        "intent": "ask_milk", "animal_names": ["Wanjirū"], "product_mention": "",
        "when": "unknown", "days_ago": 0, "clock": "",
    })
    assert parse("maziwa ya wanjiru?", HERD, NOW).animals == ["Wanjiru"]


def test_the_later_time_wins_when_model_and_words_disagree():
    # Model heard "yesterday morning"; the words say "jana jioni".
    scripted({
        "intent": "log_treatment", "animal_names": ["Njeri"], "product_mention": "",
        "when": "yesterday_morning", "days_ago": 0, "clock": "",
    })
    p = parse("Njeri jana jioni sindano", HERD, NOW)
    assert p.given_at.at.hour == 20


def test_a_malformed_model_clock_is_ignored():
    scripted({
        "intent": "log_treatment", "animal_names": ["Njeri"], "product_mention": "",
        "when": "yesterday", "days_ago": 0, "clock": "25:99",
    })
    p = parse("Njeri jana", HERD, NOW)
    assert p.given_at.at == datetime(2026, 10, 27, 23, 59, tzinfo=NAIROBI)


def test_without_a_model_the_word_lists_still_work(no_model):
    p = parse("Nimemdunga Baraka sindano jana saa mbili usiku", HERD, NOW)
    assert p.intent == "log_treatment"
    assert p.animals == ["Baraka"]
    assert p.given_at.at == datetime(2026, 10, 27, 20, 0, tzinfo=NAIROBI)
    assert not p.model_used


def test_no_time_is_flagged(no_model):
    p = parse("Njeri amepewa dawa ya minyoo", HERD, NOW)
    assert p.given_at.assumed
    assert any("counted from now" in n for n in p.notes)


@pytest.mark.parametrize(
    "text, intent",
    [
        ("Naweza kuuza maziwa ya Njeri leo?", "ask_milk"),
        ("Njeri maziwa?", "ask_milk"),
        ("Ng'ombe gani hawafai kuuzwa maziwa?", "ask_herd"),
        ("which cows can I milk for sale?", "ask_herd"),
        ("nimempa Baraka dawa ya minyoo", "log_treatment"),
        ("Habari yako", None),
    ],
)
def test_scan_intent(text, intent):
    assert scan_intent(text, HERD) == intent
