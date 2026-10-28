"""
Time, the milking schedule, and how dates are spoken back to a Kenyan farmer.

Kenya has one time zone and no daylight saving, so every timestamp Mifugo
stores is aware and pinned to Africa/Nairobi.

Swahili time-telling starts the day at sunrise: 07:00 is "saa moja asubuhi",
17:00 is "saa kumi na moja jioni". Every date shown to a farmer gives the
Swahili clock and the 24-hour clock side by side, because a wrong reading of
"saa mbili" is a twelve-hour error in the one number that matters.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

NAIROBI = ZoneInfo("Africa/Nairobi")

DAYS_SW = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]
DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def now():
    return datetime.now(NAIROBI)


def aware(dt):
    """Pin a naive datetime to Nairobi; convert an aware one."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=NAIROBI)
    return dt.astimezone(NAIROBI)


@dataclass(frozen=True)
class MilkingSchedule:
    """The farm's milking times. Two a day unless the farm says otherwise."""

    times: tuple = (time(6, 0), time(17, 0))

    def __post_init__(self):
        if not self.times:
            raise ValueError("a milking schedule needs at least one time")
        object.__setattr__(self, "times", tuple(sorted(self.times)))

    @classmethod
    def parse(cls, text):
        """'06:00,17:00' -> MilkingSchedule. Invalid entries raise ValueError."""
        parsed = []
        for part in (text or "").split(","):
            part = part.strip()
            if not part:
                continue
            hh, mm = part.split(":")
            parsed.append(time(int(hh), int(mm)))
        return cls(tuple(parsed))

    def __str__(self):
        return ",".join(t.strftime("%H:%M") for t in self.times)

    def display(self):
        return ", ".join(t.strftime("%H:%M") for t in self.times)

    def _on_day(self, day):
        return [datetime.combine(day, t, tzinfo=NAIROBI) for t in self.times]

    def milkings_after(self, moment):
        """Yield scheduled milkings strictly after `moment`, in order, forever."""
        moment = aware(moment)
        day = moment.date()
        while True:
            for m in self._on_day(day):
                if m > moment:
                    yield m
            day += timedelta(days=1)

    def first_at_or_after(self, moment):
        moment = aware(moment)
        day = moment.date()
        while True:
            for m in self._on_day(day):
                if m >= moment:
                    return m
            day += timedelta(days=1)

    def latest_at_or_before(self, moment):
        """The milking whose milk is being delivered at `moment`."""
        moment = aware(moment)
        day = moment.date()
        while True:
            for m in reversed(self._on_day(day)):
                if m <= moment:
                    return m
            day -= timedelta(days=1)


# ---------------------------------------------------------------------------
# Speaking a date back
# ---------------------------------------------------------------------------

def part_of_day_sw(dt):
    h = dt.hour
    if 5 <= h < 12:
        return "asubuhi"
    if 12 <= h < 16:
        return "mchana"
    if 16 <= h < 19:
        return "jioni"
    return "usiku"


def part_of_day_en(dt):
    h = dt.hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 16:
        return "afternoon"
    if 16 <= h < 19:
        return "evening"
    return "night"


def sw_clock(dt):
    """17:00 -> 'saa 11 jioni'. Swahili hours count from 06:00/18:00."""
    hour = (dt.hour - 6) % 12 or 12
    minutes = f":{dt.minute:02d}" if dt.minute else ""
    return f"saa {hour}{minutes} {part_of_day_sw(dt)}"


def _relative_day_sw(dt, ref):
    delta = (dt.date() - ref.date()).days
    return {0: "leo", 1: "kesho", 2: "keshokutwa", -1: "jana", -2: "juzi"}.get(delta)


def _relative_day_en(dt, ref):
    delta = (dt.date() - ref.date()).days
    return {0: "today", 1: "tomorrow", -1: "yesterday"}.get(delta)


def say_sw(dt, ref=None):
    """'kesho (Ijumaa), saa 11 jioni (17:00)'."""
    dt = aware(dt)
    ref = aware(ref) if ref else now()
    day = DAYS_SW[dt.weekday()]
    rel = _relative_day_sw(dt, ref)
    head = f"{rel} ({day})" if rel else f"{day} {dt.day}/{dt.month}"
    return f"{head}, {sw_clock(dt)} ({dt:%H:%M})"


def say_en(dt, ref=None):
    """'tomorrow (Friday) evening, 17:00'."""
    dt = aware(dt)
    ref = aware(ref) if ref else now()
    day = DAYS_EN[dt.weekday()]
    rel = _relative_day_en(dt, ref)
    head = f"{rel} ({day})" if rel else f"{day} {dt.day}/{dt.month}"
    return f"{head} {part_of_day_en(dt)}, {dt:%H:%M}"


def join_names(names, lang="sw"):
    """['Njeri', 'Wanjiru', 'Tamu'] -> 'Njeri, Wanjiru na Tamu'."""
    names = list(names)
    if len(names) < 2:
        return "".join(names)
    last = " na " if lang == "sw" else " and "
    return ", ".join(names[:-1]) + last + names[-1]
