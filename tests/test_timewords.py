"""
Dose-time reading. The rule under test: a vague phrase resolves to the LATEST
moment it could mean, and never to a moment after now.
"""

from datetime import datetime

import pytest

from mifugo.clock import NAIROBI, say_en, say_sw, sw_clock
from mifugo.timewords import WhenPhrase, combine, resolve, scan

NOW = datetime(2026, 10, 28, 9, 30, tzinfo=NAIROBI)   # Wednesday morning


def at(day, hh, mm=0):
    return datetime(2026, 10, day, hh, mm, tzinfo=NAIROBI)


@pytest.mark.parametrize(
    "text, when, days_ago",
    [
        ("nilimdunga sindano jana jioni", "yesterday_evening", None),
        ("Njeri jana asubuhi", "yesterday_morning", None),
        ("jana usiku", "last_night", None),
        ("leo asubuhi", "this_morning", None),
        ("jana", "yesterday", None),
        ("juzi", "days_ago", 2),
        ("siku tatu zilizopita", "days_ago", 3),
        ("3 days ago", "days_ago", 3),
        ("sahii", "now", None),
        ("saa hii nimempa", "now", None),
        ("yesterday evening", "yesterday_evening", None),
        ("jana evening", "yesterday_evening", None),
        ("nimempa dawa ya mastitis", "unknown", None),
    ],
)
def test_scan_reads_swahili_sheng_and_english(text, when, days_ago):
    p = scan(text)
    assert p.when == when
    assert p.days_ago == days_ago


@pytest.mark.parametrize(
    "text, clock",
    [
        ("jana saa mbili usiku", "20:00"),
        ("leo saa mbili asubuhi", "08:00"),
        ("leo asubuhi saa mbili", "08:00"),       # part of day borrowed from the phrase
        ("jana saa kumi na moja jioni", "17:00"),
        ("saa sita mchana", "12:00"),
        ("yesterday at 5pm", "17:00"),
        ("jana 18:30", "18:30"),
        ("jana saa mbili", None),                 # twelve hours ambiguous: ignored
    ],
)
def test_swahili_clock(text, clock):
    assert scan(text).clock == clock


def test_window_resolves_to_its_latest_moment():
    r = resolve(WhenPhrase("yesterday_evening"), NOW)
    assert r.at == at(27, 20, 59)


def test_a_window_still_in_the_future_is_capped_at_now():
    r = resolve(WhenPhrase("this_evening"), NOW)
    assert r.at == NOW


def test_explicit_clock_beats_the_window():
    r = resolve(scan("jana saa mbili usiku"), NOW)
    assert r.at == at(27, 20)


def test_days_ago_is_end_of_that_day():
    assert resolve(WhenPhrase("days_ago", 3), NOW).at == at(25, 23, 59)


def test_no_time_counts_from_now_and_says_so():
    r = resolve(WhenPhrase("unknown"), NOW)
    assert r.at == NOW
    assert r.assumed


def test_bare_clock_later_than_now_means_yesterday():
    r = resolve(WhenPhrase("unknown", clock="18:00"), NOW)
    assert r.at == at(27, 18)


def test_combine_keeps_the_later_reading():
    model = WhenPhrase("yesterday_morning")
    lexicon = WhenPhrase("yesterday_evening")
    assert combine(model, lexicon, NOW).at == at(27, 20, 59)


def test_combine_prefers_understood_words_over_an_assumption():
    model = WhenPhrase("unknown")
    lexicon = WhenPhrase("yesterday_evening")
    assert combine(model, lexicon, NOW).at == at(27, 20, 59)


def test_swahili_clock_display():
    assert sw_clock(at(28, 17)) == "saa 11 jioni"
    assert sw_clock(at(28, 6)) == "saa 12 asubuhi"
    assert sw_clock(at(28, 19)) == "saa 1 usiku"
    assert sw_clock(at(28, 12)) == "saa 6 mchana"


def test_dates_read_back_with_both_clocks():
    assert say_sw(at(29, 17), NOW) == "kesho (Alhamisi), saa 11 jioni (17:00)"
    assert say_en(at(29, 17), NOW) == "tomorrow (Thursday) evening, 17:00"
