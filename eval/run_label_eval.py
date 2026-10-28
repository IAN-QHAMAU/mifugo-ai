"""
How well does Mifugo read withdrawal periods off a photo?

    python -m eval.run_label_eval eval/labels/real
    python -m eval.run_label_eval eval/labels/synthetic

Each image has a JSON file beside it with the true periods (see the README in
eval/labels/real). Every reading is pushed through the same withdrawal engine
the app uses, for a fixed dose time, and the resulting saleable date is
compared with the truth. Outcomes, worst first:

  DANGEROUS  the read date is EARLIER than the true one, or a period was
             accepted where the label states none. Target: 0.
  cautious   the read date is later than the truth. Milk is wasted.
  refused    the label states a period but Mifugo would not trust its
             reading. Safe; the farmer types it in.
  correct    same date.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from mifugo import llm
from mifugo.clock import NAIROBI, MilkingSchedule
from mifugo.label_reader import read_label
from mifugo.withdrawal import Kind, Treatment, Withdrawal, milk_safe_from

DOSE = datetime(2026, 10, 28, 8, 0, tzinfo=NAIROBI)
SCHEDULE = MilkingSchedule()


def withdrawal_from(truth):
    kind = Kind(truth["kind"])
    if kind is Kind.PERIOD:
        return Withdrawal(kind, truth["value"], truth["unit"])
    return Withdrawal(kind)


def safe_from(w):
    return milk_safe_from(Treatment("x", "x", DOSE, w, Withdrawal.unknown()), SCHEDULE)


def classify(read, true):
    t, r = safe_from(true), safe_from(read)
    true_blocks = true.kind in (Kind.UNKNOWN, Kind.NOT_FOR_LACTATING)
    read_blocks = read.kind in (Kind.UNKNOWN, Kind.NOT_FOR_LACTATING)
    if true_blocks:
        return "correct" if read_blocks else "DANGEROUS"
    if read_blocks:
        return "refused"
    if r < t:
        return "DANGEROUS"
    return "correct" if r == t else "cautious"


def main(folder="eval/labels/real"):
    folder = Path(folder)
    cases = sorted(folder.glob("*.json"))
    if not cases:
        print(f"No labelled photos in {folder}. See eval/labels/real/README.md.")
        return 2
    tally = {"DANGEROUS": 0, "cautious": 0, "refused": 0, "correct": 0}
    lines = []
    for case in cases:
        meta = json.loads(case.read_text())
        image = folder / meta["image"]
        reading = read_label(image.read_bytes())
        outcome = classify(reading.milk, withdrawal_from(meta["milk"]))
        tally[outcome] += 1
        lines.append(f"  {meta['image']:18} {outcome:9}  read={reading.milk.kind.value} "
                     f"{reading.milk.value or ''} {reading.milk.unit or ''}  "
                     f"{'; '.join(reading.issues)[:60]}")

    print(f"\nMifugo label reading (milk)  ·  {len(cases)} photos  ·  {folder}")
    print(f"backend: {llm.backend().describe()}")
    print("=" * 72)
    for k in ("DANGEROUS", "cautious", "refused", "correct"):
        print(f"  {k:10} {tally[k]}")
    print("=" * 72)
    print("\n".join(lines))
    return 1 if tally["DANGEROUS"] else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
