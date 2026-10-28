"""
The evidence rule. Each test hands Python a model reply and checks that a
period is accepted only when the quoted label words support it. The failure
being guarded against is a confident, wrong, SHORT period.
"""

import io

from PIL import Image

from mifugo import llm
from mifugo.label_reader import read_label, validate
from mifugo.withdrawal import Kind


def reply(milk, meat=None, **over):
    base = {
        "is_veterinary_label": True,
        "legibility": "clear",
        "product_name": "Mastitis Tube LC",
        "active_ingredients": ["cloxacillin"],
        "milk": milk,
        "meat": meat or {"stated": "period", "value": 7, "unit": "days", "quote": "Meat: 7 days"},
        "several_species_listed": False,
    }
    base.update(over)
    return base


def period(value, unit, quote):
    return {"stated": "period", "value": value, "unit": unit, "quote": quote}


def test_a_well_evidenced_period_is_accepted():
    r = validate(reply(period(96, "hours", "Withdrawal period: Milk 96 hours")))
    assert r.milk.kind is Kind.PERIOD
    assert (r.milk.value, r.milk.unit) == (96, "hours")
    assert r.issues == []
    assert not r.needs_confirmation


def test_a_number_not_in_the_quote_is_rejected():
    # Model says 3 days but the words it quoted say 5.
    r = validate(reply(period(3, "days", "Milk: 5 days")))
    assert r.milk.kind is Kind.UNKNOWN
    assert r.needs_confirmation


def test_a_quote_about_meat_cannot_set_the_milk_period():
    r = validate(reply(period(28, "days", "Meat and offal: 28 days")))
    assert r.milk.kind is Kind.UNKNOWN


def test_swapped_numbers_on_a_shared_line_are_rejected():
    line = "Cattle: meat 21 days, milk 4 days"
    swapped = validate(reply(period(21, "days", line), period(4, "days", line)))
    assert swapped.milk.kind is Kind.UNKNOWN      # 21 belongs to meat
    assert swapped.meat.kind is Kind.UNKNOWN      # 4 belongs to milk
    right = validate(reply(period(4, "days", line), period(21, "days", line)))
    assert (right.milk.value, right.meat.value) == (4, 21)


def test_both_periods_on_one_unpunctuated_line():
    line = "Meat and offal: 28 days Milk: 7 days"
    r = validate(reply(period(7, "days", line), period(28, "days", line)))
    assert (r.milk.value, r.meat.value) == (7, 28)


def test_a_number_before_the_keyword_is_refused_not_guessed():
    # "7 days for milk": the number precedes the word. Refusing is safe.
    r = validate(reply(period(7, "days", "Withdrawal: 7 days for milk")))
    assert r.milk.kind is Kind.UNKNOWN


def test_a_unit_not_in_the_quote_is_rejected():
    r = validate(reply(period(72, "days", "Milk: 72 hours")))
    assert r.milk.kind is Kind.UNKNOWN


def test_milkings_are_kept_as_milkings():
    r = validate(reply(period(6, "milkings", "Milk withdrawal: 6 milkings")))
    assert (r.milk.value, r.milk.unit) == (6, "milkings")


def test_several_species_needs_a_cattle_quote():
    sheep_line = period(4, "days", "Sheep: milk 4 days")
    r = validate(reply(sheep_line, several_species_listed=True))
    assert r.milk.kind is Kind.UNKNOWN
    cattle_line = period(7, "days", "Cattle: milk 7 days")
    r = validate(reply(cattle_line, several_species_listed=True))
    assert r.milk.kind is Kind.PERIOD


def test_another_species_number_is_rejected_even_inside_a_cattle_quote():
    block = "Sheep and goats: meat 7 days\nCattle: meat 14 days, milk 60 hours"
    sheep_meat = validate(reply(period(60, "hours", block), period(7, "days", block),
                                several_species_listed=True))
    assert sheep_meat.meat.kind is Kind.UNKNOWN
    cattle = validate(reply(period(60, "hours", block), period(14, "days", block),
                            several_species_listed=True))
    assert (cattle.milk.value, cattle.meat.value) == (60, 14)


def test_zero_needs_zero_words():
    ok = validate(reply({"stated": "zero", "value": 0, "unit": "none", "quote": "Milk: Nil"}))
    assert ok.milk.kind is Kind.ZERO
    bad = validate(reply({"stated": "zero", "value": 0, "unit": "none", "quote": "Milk withdrawal applies"}))
    assert bad.milk.kind is Kind.UNKNOWN


def test_not_for_lactating_is_kept():
    q = "Not for use in lactating animals producing milk for human consumption"
    r = validate(reply({"stated": "not_for_lactating", "value": 0, "unit": "none", "quote": q}))
    assert r.milk.kind is Kind.NOT_FOR_LACTATING


def test_not_stated_is_unknown_never_a_default():
    r = validate(reply({"stated": "not_stated", "value": 0, "unit": "none", "quote": ""}))
    assert r.milk.kind is Kind.UNKNOWN
    assert r.milk.value is None


def test_implausible_values_are_treated_as_misreads():
    r = validate(reply(period(400, "days", "Milk: 400 days")))
    assert r.milk.kind is Kind.UNKNOWN


def test_not_a_label_unknowns_everything():
    r = validate(reply(period(4, "days", "Milk: 4 days"), is_veterinary_label=False))
    assert r.milk.kind is Kind.UNKNOWN and r.meat.kind is Kind.UNKNOWN


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_read_label_sends_the_image_and_validates_the_reply():
    fake = llm.ScriptedBackend(lambda s, u, imgs: reply(period(4, "days", "Milk: 4 days")))
    llm.set_backend(fake)
    try:
        r = read_label(_jpeg())
    finally:
        llm.set_backend(None)
    assert r.milk.kind is Kind.PERIOD
    assert len(fake.calls[0]["images"]) == 1


def test_a_model_failure_becomes_unknown_not_a_crash():
    llm.set_backend(llm.NoModel())
    try:
        r = read_label(_jpeg())
    finally:
        llm.set_backend(None)
    assert r.milk.kind is Kind.UNKNOWN
    assert any("unavailable" in i for i in r.issues)
