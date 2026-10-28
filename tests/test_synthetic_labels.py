"""
The evidence rule must not refuse a CORRECT reading. For every synthetic
label, hand Python the reply a perfect reader would give (quoting the whole
printed statement, the lazy way a model often does) and check the outcome is
"correct", never "refused" or worse.
"""

import json
from pathlib import Path

import pytest

from eval.run_label_eval import classify, withdrawal_from
from mifugo.label_reader import validate

FOLDER = Path(__file__).resolve().parent.parent / "eval" / "labels" / "synthetic"
STATED = {"period": "period", "zero": "zero", "not_for_lactating": "not_for_lactating", "unknown": "not_stated"}


def ideal(truth, printed):
    return {
        "stated": STATED[truth["kind"]],
        "value": truth["value"] or 0,
        "unit": truth["unit"] or "none",
        "quote": printed if truth["kind"] != "unknown" else "",
    }


@pytest.mark.parametrize("case", sorted(FOLDER.glob("*.json")), ids=lambda p: p.stem)
def test_a_perfect_reading_is_accepted(case):
    meta = json.loads(case.read_text())
    raw = {
        "is_veterinary_label": True,
        "legibility": "clear",
        "product_name": meta["image"],
        "active_ingredients": [],
        "milk": ideal(meta["milk"], meta["printed"]),
        "meat": ideal(meta["meat"], meta["printed"]),
        "several_species_listed": meta["several_species"],
    }
    reading = validate(raw)
    assert classify(reading.milk, withdrawal_from(meta["milk"])) == "correct", reading.issues
    true_meat = withdrawal_from(meta["meat"])
    assert (reading.meat.kind, reading.meat.value) == (true_meat.kind, true_meat.value), reading.issues
