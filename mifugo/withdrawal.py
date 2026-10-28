"""
DETERMINISTIC. The withdrawal engine.

Every "can I sell this milk?" answer Mifugo gives is computed here, in plain
Python, from three inputs: what the label says, when the dose was given, and
when the farm milks. Gemma never computes a date and never decides a verdict.
It reads the label and the farmer's words; this file does the arithmetic.

The rules, each conservative by construction:

1. Every logged dose is its own treatment, so the clock effectively starts at
   the LAST dose. An animal's status is the latest end across all of them.
2. Milk is saleable from the first scheduled milking at or after the end of
   the withdrawal period. Never earlier, never "about".
3. A period printed in milkings is counted in the farm's real milkings after
   the dose, not converted to hours.
4. If the period could not be read, or the label forbids use in lactating
   animals, the verdict is DO NOT SELL with no end date, until a person
   enters a confirmed period. Mifugo never substitutes a default number.
5. An uncertain dose time is resolved upstream (timewords.py) to the LATEST
   plausible moment, which can only push the end later.
"""

import math
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum

from mifugo.clock import MilkingSchedule, aware


class Kind(str, Enum):
    PERIOD = "period"
    ZERO = "zero"
    NOT_FOR_LACTATING = "not_for_lactating"   # milk only
    UNKNOWN = "unknown"


MILK_UNITS = ("hours", "days", "milkings")
MEAT_UNITS = ("hours", "days")

# Plausibility ceilings. A value above these is treated as a misread, not a
# long withdrawal: the reading is rejected and a person must confirm it.
MAX_MILK_DAYS = 60
MAX_MEAT_DAYS = 400


@dataclass(frozen=True)
class Withdrawal:
    kind: Kind
    value: float = None
    unit: str = None
    quote: str = ""

    def __post_init__(self):
        object.__setattr__(self, "kind", Kind(self.kind))
        if self.kind is Kind.PERIOD:
            if self.value is None or self.unit is None:
                raise ValueError("a withdrawal period needs a value and a unit")
            if self.value <= 0:
                raise ValueError("a withdrawal period must be positive; use Kind.ZERO for none")
            if self.unit not in MILK_UNITS:
                raise ValueError(f"unknown unit {self.unit!r}")

    @classmethod
    def unknown(cls, quote=""):
        return cls(Kind.UNKNOWN, quote=quote)

    def days(self, milkings_per_day=2):
        """Approximate length in days, for plausibility checks only."""
        if self.kind is not Kind.PERIOD:
            return 0.0
        if self.unit == "hours":
            return self.value / 24
        if self.unit == "milkings":
            return self.value / milkings_per_day
        return float(self.value)


@dataclass(frozen=True)
class Treatment:
    animal: str
    product: str
    given_at: object          # aware datetime
    milk: Withdrawal
    meat: Withdrawal
    id: int = None

    def __post_init__(self):
        object.__setattr__(self, "given_at", aware(self.given_at))


class Status(str, Enum):
    CLEAR = "clear"
    WITHHOLD = "withhold"                  # known end date
    WITHHOLD_UNKNOWN = "withhold_unknown"  # needs a person to confirm a period


@dataclass(frozen=True)
class Verdict:
    status: Status
    safe_from: object = None      # aware datetime, or None
    reason: str = "no_treatment"  # no_treatment | period | zero | unknown_period | not_for_lactating
    driving: Treatment = None     # the treatment that sets the date or blocks

    @property
    def sellable(self):
        return self.status is Status.CLEAR


@dataclass(frozen=True)
class AnimalStatus:
    animal: str
    milk: Verdict
    meat: Verdict
    treatments: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Single treatment
# ---------------------------------------------------------------------------

def milk_safe_from(treatment, schedule):
    """First saleable milking after this treatment, or None if no end is known."""
    w = treatment.milk
    if w.kind in (Kind.UNKNOWN, Kind.NOT_FOR_LACTATING):
        return None
    if w.kind is Kind.ZERO:
        # Zero withdrawal: the next milking after the dose is saleable.
        return next(schedule.milkings_after(treatment.given_at))
    if w.unit == "milkings":
        # Discard the next N milkings after the dose; the one after is saleable.
        milkings = schedule.milkings_after(treatment.given_at)
        for _ in range(math.ceil(w.value)):
            next(milkings)
        return next(milkings)
    hours = w.value * (24 if w.unit == "days" else 1)
    return schedule.first_at_or_after(treatment.given_at + timedelta(hours=hours))


def meat_safe_from(treatment):
    """Earliest moment the animal may be slaughtered for food, or None."""
    w = treatment.meat
    if w.kind is Kind.ZERO:
        return treatment.given_at
    if w.kind is not Kind.PERIOD or w.unit not in MEAT_UNITS:
        return None
    hours = w.value * (24 if w.unit == "days" else 1)
    return treatment.given_at + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Many treatments on one animal
# ---------------------------------------------------------------------------

def milk_verdict(treatments, now, schedule=MilkingSchedule()):
    now = aware(now)
    if not treatments:
        return Verdict(Status.CLEAR)

    # Rule 4: one unconfirmed treatment blocks sale, however old the others are.
    blocked = [t for t in treatments if t.milk.kind in (Kind.UNKNOWN, Kind.NOT_FOR_LACTATING)]
    if blocked:
        t = max(blocked, key=lambda x: x.given_at)
        reason = "not_for_lactating" if t.milk.kind is Kind.NOT_FOR_LACTATING else "unknown_period"
        return Verdict(Status.WITHHOLD_UNKNOWN, None, reason, t)

    ends = [(milk_safe_from(t, schedule), t) for t in treatments]
    safe_from, t = max(ends, key=lambda pair: pair[0])
    reason = "zero" if t.milk.kind is Kind.ZERO else "period"
    if now >= safe_from:
        return Verdict(Status.CLEAR, safe_from, reason, t)
    return Verdict(Status.WITHHOLD, safe_from, reason, t)


def meat_verdict(treatments, now):
    now = aware(now)
    if not treatments:
        return Verdict(Status.CLEAR)

    blocked = [t for t in treatments if meat_safe_from(t) is None]
    if blocked:
        t = max(blocked, key=lambda x: x.given_at)
        return Verdict(Status.WITHHOLD_UNKNOWN, None, "unknown_period", t)

    ends = [(meat_safe_from(t), t) for t in treatments]
    safe_from, t = max(ends, key=lambda pair: pair[0])
    reason = "zero" if t.meat.kind is Kind.ZERO else "period"
    if now >= safe_from:
        return Verdict(Status.CLEAR, safe_from, reason, t)
    return Verdict(Status.WITHHOLD, safe_from, reason, t)


def animal_status(animal, treatments, now, schedule=MilkingSchedule()):
    mine = [t for t in treatments if t.animal == animal]
    return AnimalStatus(
        animal=animal,
        milk=milk_verdict(mine, now, schedule),
        meat=meat_verdict(mine, now),
        treatments=sorted(mine, key=lambda t: t.given_at, reverse=True),
    )


def herd_status(animals, treatments, now, schedule=MilkingSchedule()):
    return [animal_status(a, treatments, now, schedule) for a in animals]


# ---------------------------------------------------------------------------
# The co-op collection point
# ---------------------------------------------------------------------------

ACCEPT = "accept"
TEST = "test"


@dataclass(frozen=True)
class CollectionCheck:
    decision: str            # ACCEPT | TEST
    milking_at: object       # the milking being delivered
    exclude: list            # AnimalStatus for animals whose milk is not saleable


def collection_check(animals, treatments, at, schedule=MilkingSchedule()):
    """
    A clerk receiving a delivery at `at` is receiving the most recent milking.
    Any animal whose milk is not saleable at that milking must be out of the
    can, and the can is flagged for a residue test. This is risk-based testing:
    the co-op spends its test strips on the deliveries that can actually carry
    residues instead of guessing.
    """
    milking = schedule.latest_at_or_before(at)
    # A dose given after that milking cannot be in that milk.
    before = [t for t in treatments if t.given_at <= milking]
    statuses = herd_status(animals, before, milking, schedule)
    exclude = [s for s in statuses if not s.milk.sellable]
    return CollectionCheck(TEST if exclude else ACCEPT, milking, exclude)
