"""
DETERMINISTIC. When was the dose given?

Farmers say "jana jioni", "leo asubuhi saa mbili", "juzi", "yesterday evening",
"saa hii". Gemma extracts the phrase into a closed vocabulary (log_parser.py);
this file ALSO reads the raw text directly, so a model failure cannot lose the
time, and then turns either answer into a timestamp.

The one rule that matters: when a phrase covers a window of time, use the
LATEST moment in that window. A later dose time can only push the end of the
withdrawal later, so every guess this file makes errs towards not selling.
When the model and the lexicon disagree, the later of the two wins.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from mifugo.clock import NAIROBI, aware
from mifugo.sw_numbers import WORDS as NUMBER_WORDS
from mifugo.sw_numbers import parse_number
from mifugo.text import normalise

WHEN_VALUES = [
    "now",
    "earlier_today",
    "this_morning",
    "this_afternoon",
    "this_evening",
    "last_night",
    "yesterday",
    "yesterday_morning",
    "yesterday_afternoon",
    "yesterday_evening",
    "days_ago",
    "unknown",
]

# Latest moment of each window, as (day offset, hour, minute).
WINDOW_END = {
    "this_morning": (0, 11, 59),
    "this_afternoon": (0, 15, 59),
    "this_evening": (0, 20, 59),
    "last_night": (0, 4, 59),       # jana usiku runs 21:00 yesterday to dawn today
    "yesterday": (-1, 23, 59),
    "yesterday_morning": (-1, 11, 59),
    "yesterday_afternoon": (-1, 15, 59),
    "yesterday_evening": (-1, 20, 59),
}

DAY_OF = {
    "now": 0, "earlier_today": 0, "this_morning": 0, "this_afternoon": 0,
    "this_evening": 0, "last_night": 0, "yesterday": -1, "yesterday_morning": -1,
    "yesterday_afternoon": -1, "yesterday_evening": -1,
}

# Longest phrases first: "jana jioni" must win over "jana".
PHRASES = [
    ("asubuhi ya jana", "yesterday_morning"),
    ("jioni ya jana", "yesterday_evening"),
    ("usiku wa jana", "last_night"),
    ("asubuhi ya leo", "this_morning"),
    ("jioni ya leo", "this_evening"),
    ("day before yesterday", "days_ago:2"),
    ("yesterday morning", "yesterday_morning"),
    ("yesterday afternoon", "yesterday_afternoon"),
    ("yesterday evening", "yesterday_evening"),
    ("yesterday night", "last_night"),
    ("this morning", "this_morning"),
    ("this afternoon", "this_afternoon"),
    ("this evening", "this_evening"),
    ("last night", "last_night"),
    ("jana asubuhi", "yesterday_morning"),
    ("jana morning", "yesterday_morning"),
    ("jana mchana", "yesterday_afternoon"),
    ("jana jioni", "yesterday_evening"),
    ("jana evening", "yesterday_evening"),
    ("jana usiku", "last_night"),
    ("jana night", "last_night"),
    ("leo asubuhi", "this_morning"),
    ("leo morning", "this_morning"),
    ("leo mchana", "this_afternoon"),
    ("leo jioni", "this_evening"),
    ("leo evening", "this_evening"),
    ("sasa hivi", "now"),
    ("saa hii", "now"),
    ("right now", "now"),
    ("just now", "now"),
    ("sahii", "now"),
    ("yesterday", "yesterday"),
    ("jana", "yesterday"),
    ("juzi", "days_ago:2"),
    ("today", "earlier_today"),
    ("leo", "earlier_today"),
    ("asubuhi", "this_morning"),
    ("mchana", "this_afternoon"),
    ("jioni", "this_evening"),
    ("usiku", "last_night"),
]

_NUM = r"(\d+|(?:(?:" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")\s?)+)"
DAYS_AGO_PATTERNS = [
    re.compile(r"siku " + _NUM + r" (?:zilizopita|iliyopita|zimepita|nyuma)"),
    re.compile(_NUM + r" days? ago"),
]

SW_CLOCK = re.compile(r"saa " + _NUM + r"(?::(\d{2}))?\s*(asubuhi|mchana|jioni|usiku)?")
AMPM = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b")
H24 = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


@dataclass(frozen=True)
class WhenPhrase:
    when: str = "unknown"
    days_ago: int = None
    clock: str = None        # "HH:MM", 24-hour


def _swahili_hour(n, part):
    """saa N + part of day -> 24h hour. Swahili hours start at 06:00."""
    base = (n + 6) % 12
    if part == "asubuhi":
        return base
    if part in ("mchana", "jioni"):
        return base + 12
    if part == "usiku":
        return base + 12 if base >= 6 else base
    return None


PART_OF = {
    "this_morning": "asubuhi", "yesterday_morning": "asubuhi",
    "this_afternoon": "mchana", "yesterday_afternoon": "mchana",
    "this_evening": "jioni", "yesterday_evening": "jioni",
    "last_night": "usiku",
}


def _clock(hay, default_part=None):
    """'saa mbili asubuhi' -> '08:00'. A bare 'saa mbili' borrows the part of
    day from the surrounding phrase ('leo asubuhi saa mbili'); without one it
    is ambiguous by twelve hours and is ignored."""
    m = SW_CLOCK.search(hay)
    if m:
        n = parse_number(m.group(1))
        part = m.group(3) or default_part
        if n and 1 <= n <= 12 and part:
            hour = _swahili_hour(n, part)
            if hour is not None:
                return f"{hour:02d}:{int(m.group(2) or 0):02d}"
    m = AMPM.search(hay)
    if m:
        hour = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        return f"{hour:02d}:{int(m.group(2) or 0):02d}"
    m = H24.search(hay)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def scan(text):
    """Read the time phrase straight from the farmer's words. No model."""
    hay = normalise(text)

    for pattern in DAYS_AGO_PATTERNS:
        m = pattern.search(hay)
        if m:
            n = parse_number(m.group(1))
            if n is not None:
                return WhenPhrase("days_ago", n, _clock(hay))

    for phrase, value in PHRASES:
        if re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", hay):
            if value.startswith("days_ago:"):
                return WhenPhrase("days_ago", int(value.split(":")[1]), _clock(hay))
            return WhenPhrase(value, None, _clock(hay, PART_OF.get(value)))

    return WhenPhrase("unknown", None, _clock(hay))


@dataclass(frozen=True)
class Resolved:
    at: datetime
    assumed: bool     # True when the farmer gave no usable time
    basis: str        # what the timestamp was built from, for display


def resolve(phrase, now):
    """WhenPhrase -> the latest plausible dose time, never after `now`."""
    now = aware(now)
    today = now.date()

    if phrase.when == "days_ago" and phrase.days_ago is not None:
        offset = -phrase.days_ago
    else:
        offset = DAY_OF.get(phrase.when)

    if phrase.clock and offset is not None:
        hh, mm = (int(x) for x in phrase.clock.split(":"))
        at = datetime.combine(today + timedelta(days=offset), time(hh, mm), tzinfo=NAIROBI)
        return Resolved(min(at, now), False, f"{phrase.when}+{phrase.clock}")

    if phrase.clock and phrase.when == "unknown":
        hh, mm = (int(x) for x in phrase.clock.split(":"))
        at = datetime.combine(today, time(hh, mm), tzinfo=NAIROBI)
        if at > now:
            at -= timedelta(days=1)
        return Resolved(at, False, f"clock {phrase.clock}")

    if phrase.when in ("now", "earlier_today"):
        return Resolved(now, False, phrase.when)

    if phrase.when == "days_ago" and phrase.days_ago is not None:
        if phrase.days_ago <= 0:
            return Resolved(now, False, "today")
        day = today - timedelta(days=phrase.days_ago)
        at = datetime.combine(day, time(23, 59), tzinfo=NAIROBI)
        return Resolved(min(at, now), False, f"{phrase.days_ago} days ago, end of day")

    if phrase.when in WINDOW_END:
        days, hh, mm = WINDOW_END[phrase.when]
        at = datetime.combine(today + timedelta(days=days), time(hh, mm), tzinfo=NAIROBI)
        return Resolved(min(at, now), False, f"{phrase.when}, latest moment")

    # Nothing usable: counting from now is the only choice that cannot be early.
    return Resolved(now, True, "no time given, counted from now")


def combine(model_phrase, lexicon_phrase, now):
    """Resolve both readings and keep the later one."""
    a = resolve(model_phrase, now) if model_phrase else None
    b = resolve(lexicon_phrase, now)
    if a is None:
        return b
    # A reading that had to assume "now" loses to one that understood the words.
    if a.assumed and not b.assumed:
        return b
    if b.assumed and not a.assumed:
        return a
    return a if a.at >= b.at else b
