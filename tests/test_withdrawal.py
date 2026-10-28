"""
The withdrawal engine is the product. Each test names a rule a farmer or a
co-op is relying on. The dangerous failure is a date that is too EARLY, so most
tests pin an exact date rather than "roughly right".
"""

from datetime import datetime, time

import pytest

from mifugo.clock import NAIROBI, MilkingSchedule
from mifugo.withdrawal import (
    ACCEPT,
    TEST,
    Kind,
    Status,
    Treatment,
    Withdrawal,
    animal_status,
    collection_check,
    meat_verdict,
    milk_verdict,
)

TWICE = MilkingSchedule((time(6, 0), time(17, 0)))


def at(day, hh, mm=0):
    """Dates in October 2026; the 28th is a Wednesday."""
    return datetime(2026, 10, day, hh, mm, tzinfo=NAIROBI)


def dose(given, milk, meat=Withdrawal(Kind.PERIOD, 28, "days"), animal="Njeri", product="Tube X"):
    return Treatment(animal, product, given, milk, meat)


def days(n):
    return Withdrawal(Kind.PERIOD, n, "days", f"Milk: {n} days")


def hours(n):
    return Withdrawal(Kind.PERIOD, n, "hours", f"Milk: {n} hours")


def milkings(n):
    return Withdrawal(Kind.PERIOD, n, "milkings", f"Milk: {n} milkings")


# -- the basic arithmetic ----------------------------------------------------

def test_no_treatment_is_clear():
    assert milk_verdict([], at(28, 9)).status is Status.CLEAR


def test_days_round_up_to_the_next_milking():
    # Dosed Wed 18:00 + 3 days = Sat 18:00. The Sat 17:00 milking is too early;
    # the first saleable milking is Sun 06:00.
    v = milk_verdict([dose(at(28, 18), days(3))], at(29, 9), TWICE)
    assert v.status is Status.WITHHOLD
    assert v.safe_from == datetime(2026, 11, 1, 6, 0, tzinfo=NAIROBI)


def test_end_exactly_on_a_milking_is_saleable_at_that_milking():
    v = milk_verdict([dose(at(28, 6), hours(72))], at(28, 9), TWICE)
    assert v.safe_from == at(31, 6)


def test_hours_unit():
    v = milk_verdict([dose(at(28, 7), hours(60))], at(28, 9), TWICE)
    # 07:00 Wed + 60h = 19:00 Fri -> Sat 06:00
    assert v.safe_from == at(31, 6)


def test_milkings_are_counted_in_real_milkings_not_hours():
    # Dosed Wed 07:00. Discard Wed 17:00, Thu 06:00, Thu 17:00, Fri 06:00.
    # The fifth milking after the dose, Fri 17:00, is the first saleable.
    v = milk_verdict([dose(at(28, 7), milkings(4))], at(28, 9), TWICE)
    assert v.safe_from == at(30, 17)


def test_milkings_respect_a_three_times_a_day_farm():
    thrice = MilkingSchedule((time(5, 0), time(13, 0), time(20, 0)))
    v = milk_verdict([dose(at(28, 6), milkings(3))], at(28, 9), thrice)
    # Discard Wed 13:00, Wed 20:00, Thu 05:00 -> Thu 13:00
    assert v.safe_from == at(29, 13)


def test_zero_withdrawal_means_the_next_milking():
    zero = Withdrawal(Kind.ZERO, quote="Milk: nil")
    v = milk_verdict([dose(at(28, 7), zero)], at(28, 9), TWICE)
    assert v.status is Status.WITHHOLD
    assert v.safe_from == at(28, 17)


def test_status_turns_clear_once_the_milking_arrives():
    t = dose(at(28, 18), days(3))
    sunday_dawn = datetime(2026, 11, 1, 5, 59, tzinfo=NAIROBI)
    sunday_milking = datetime(2026, 11, 1, 6, 0, tzinfo=NAIROBI)
    assert milk_verdict([t], sunday_dawn, TWICE).status is Status.WITHHOLD
    assert milk_verdict([t], sunday_milking, TWICE).status is Status.CLEAR


# -- many treatments ---------------------------------------------------------

def test_the_latest_end_wins_not_the_latest_dose():
    long_course = dose(at(26, 8), days(7), product="Long")
    short_later = dose(at(28, 8), days(2), product="Short")
    v = milk_verdict([long_course, short_later], at(28, 9), TWICE)
    assert v.driving.product == "Long"
    # Mon 26th 08:00 + 7 days = Mon 2 Nov 08:00 -> the 17:00 milking that day
    assert v.safe_from == datetime(2026, 11, 2, 17, 0, tzinfo=NAIROBI)


def test_a_repeat_dose_restarts_the_clock():
    first = dose(at(26, 8), days(3))
    second = dose(at(28, 8), days(3))
    v = milk_verdict([first, second], at(28, 9), TWICE)
    assert v.safe_from == at(31, 17)


# -- refusing to guess -------------------------------------------------------

def test_unknown_period_withholds_with_no_end_date():
    v = milk_verdict([dose(at(28, 7), Withdrawal.unknown())], at(28, 9), TWICE)
    assert v.status is Status.WITHHOLD_UNKNOWN
    assert v.safe_from is None
    assert v.reason == "unknown_period"


def test_an_old_unknown_treatment_still_blocks():
    old = dose(at(1, 7), Withdrawal.unknown(), product="Mystery")
    recent_known = dose(at(28, 7), days(1), product="Known")
    v = milk_verdict([old, recent_known], at(28, 9), TWICE)
    assert v.status is Status.WITHHOLD_UNKNOWN
    assert v.driving.product == "Mystery"


def test_not_for_lactating_animals_withholds():
    nfl = Withdrawal(Kind.NOT_FOR_LACTATING, quote="Not for use in lactating cows")
    v = milk_verdict([dose(at(28, 7), nfl)], at(28, 9), TWICE)
    assert v.status is Status.WITHHOLD_UNKNOWN
    assert v.reason == "not_for_lactating"


def test_a_period_needs_a_value_and_unit():
    with pytest.raises(ValueError):
        Withdrawal(Kind.PERIOD, None, "days")
    with pytest.raises(ValueError):
        Withdrawal(Kind.PERIOD, 3, "weeks")
    with pytest.raises(ValueError):
        Withdrawal(Kind.PERIOD, 0, "days")


# -- meat --------------------------------------------------------------------

def test_meat_is_calendar_time_not_milkings():
    v = meat_verdict([dose(at(1, 8), days(3), meat=Withdrawal(Kind.PERIOD, 28, "days"))], at(28, 9))
    assert v.status is Status.WITHHOLD
    assert v.safe_from == at(29, 8)


def test_meat_in_milkings_is_not_applied():
    odd = Withdrawal(Kind.PERIOD, 4, "milkings")
    v = meat_verdict([dose(at(28, 8), days(3), meat=odd)], at(28, 9))
    assert v.status is Status.WITHHOLD_UNKNOWN


def test_animal_status_only_counts_that_animal():
    ts = [dose(at(28, 7), days(3), animal="Njeri"), dose(at(28, 7), days(9), animal="Baraka")]
    s = animal_status("Njeri", ts, at(28, 9), TWICE)
    assert s.milk.safe_from == at(31, 17)
    assert len(s.treatments) == 1


# -- the collection point ----------------------------------------------------

def test_collection_accepts_a_clean_farm():
    check = collection_check(["Njeri", "Baraka"], [], at(28, 7, 30), TWICE)
    assert check.decision == ACCEPT
    assert check.milking_at == at(28, 6)


def test_collection_flags_the_can_and_names_the_cow():
    ts = [dose(at(27, 8), days(3), animal="Njeri")]
    check = collection_check(["Njeri", "Baraka"], ts, at(28, 7, 30), TWICE)
    assert check.decision == TEST
    assert [s.animal for s in check.exclude] == ["Njeri"]


def test_a_dose_after_the_milking_does_not_taint_that_milking():
    ts = [dose(at(28, 7), days(3), animal="Njeri")]   # treated after the 06:00 milking
    check = collection_check(["Njeri"], ts, at(28, 7, 30), TWICE)
    assert check.decision == ACCEPT


def test_collection_flags_unknown_periods():
    ts = [dose(at(20, 8), Withdrawal.unknown(), animal="Baraka")]
    check = collection_check(["Njeri", "Baraka"], ts, at(28, 7, 30), TWICE)
    assert check.decision == TEST
