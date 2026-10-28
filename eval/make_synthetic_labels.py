"""
Render synthetic medicine-box panels with known withdrawal periods, so the
label reader can be run end to end before anyone has photographed real boxes.

    python -m eval.make_synthetic_labels

Synthetic labels are a smoke test, not evidence. Printed type on a flat
rendering is far easier than a creased box under a farm light. The real test
set is eval/labels/real/, photographed at an agrovet (see the README there).

Each panel mixes the withdrawal statement with the numbers that make reading
it hard on a real box: doses, body weights, storage temperatures, batch
numbers, expiry dates, and other species' periods.
"""

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent / "labels" / "synthetic"

CASES = [
    ("Milk: 72 hours\nMeat: 14 days", ("period", 72, "hours"), ("period", 14, "days"), False),
    ("WITHDRAWAL PERIODS\nMeat and offal: 28 days\nMilk: 7 days", ("period", 7, "days"), ("period", 28, "days"), False),
    ("Withdrawal period: Milk 96 hrs, Meat 10 days", ("period", 96, "hours"), ("period", 10, "days"), False),
    ("Milk withdrawal: 6 milkings\nSlaughter: 5 days", ("period", 6, "milkings"), ("period", 5, "days"), False),
    ("Milk: Nil\nMeat: 3 days", ("zero", None, None), ("period", 3, "days"), False),
    ("Not for use in lactating cows producing\nmilk for human consumption.\nMeat: 28 days",
     ("not_for_lactating", None, None), ("period", 28, "days"), False),
    ("Cattle: meat 21 days, milk 4 days\nSheep: meat 14 days, milk 7 days",
     ("period", 4, "days"), ("period", 21, "days"), True),
    ("Sheep and goats: meat 7 days\nCattle: meat 14 days, milk 60 hours",
     ("period", 60, "hours"), ("period", 14, "days"), True),
    ("Store below 25°C. Protect from light.", ("unknown", None, None), ("unknown", None, None), False),
    ("Withdrawal: Milk 5 days  Meat 21 days", ("period", 5, "days"), ("period", 21, "days"), False),
    ("Meat: 0 days\nMilk: 0 hours", ("zero", None, None), ("zero", None, None), False),
    ("Milk: 120 hours after last treatment\nMeat: 35 days", ("period", 120, "hours"), ("period", 35, "days"), False),
]

DISTRACTORS = [
    "Dosage: 1 ml per 10 kg body weight",
    "Give 2.5 ml per 50 kg by deep intramuscular injection",
    "Store below 30°C",
    "Batch No: 2407{n}",
    "Exp: 0{m}/2028",
    "Each ml contains 200 mg",
    "Shake well before use. 100 ml",
    "Repeat after 48 hours if necessary",
    "For veterinary use only",
    "Reg. No. VMD/{n}",
]


def font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render(i, statement, rng):
    w, h = 900, 640
    img = Image.new("RGB", (w, h), rng.choice(["#ffffff", "#f4f1e6", "#eef4f7"]))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 90], fill=rng.choice(["#1d4e89", "#8a1c1c", "#205d36"]))
    d.text((24, 22), f"SYNTH-{i:02d} VET", fill="white", font=font(44))
    lines = rng.sample(DISTRACTORS, 4)
    lines = [l.format(n=rng.randint(100, 999), m=rng.randint(1, 9)) for l in lines]
    lines.insert(rng.randint(1, 3), statement)
    y = 120
    for block in lines:
        for line in block.split("\n"):
            d.text((28, y), line, fill="#1b1b1b", font=font(rng.choice([24, 26, 28])))
            y += 38
        y += 14
    img = img.rotate(rng.uniform(-6, 6), expand=True, fillcolor="#777777")
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.0)))
    return img


def truth(t):
    kind, value, unit = t
    return {"kind": kind, "value": value, "unit": unit}


def main():
    rng = random.Random(7)
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (statement, milk, meat, several) in enumerate(CASES, 1):
        img = render(i, statement, rng)
        img.save(OUT / f"synth_{i:02d}.jpg", quality=88)
        (OUT / f"synth_{i:02d}.json").write_text(json.dumps({
            "image": f"synth_{i:02d}.jpg",
            "milk": truth(milk),
            "meat": truth(meat),
            "several_species": several,
            "printed": statement,
        }, indent=2))
    print(f"wrote {len(CASES)} labels to {OUT}")


if __name__ == "__main__":
    main()
