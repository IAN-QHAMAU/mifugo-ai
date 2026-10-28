"""
Gemma job 1: read the withdrawal periods off a photo of the drug packaging.

This is the step that makes the product possible. The information a farmer
needs is printed on the box, in small English type, next to dosing tables and
species lists. Gemma reads it; Python then refuses to believe anything the
model cannot show evidence for.

The evidence rule:
  The model must copy the exact printed words of each withdrawal statement
  into `quote`. Python accepts a period only if
    * the quote contains the same number the model reported,
    * the quote talks about milk (or meat, for the meat period),
    * the value is plausible, and
    * where the label lists several species, the quote names cattle.
  Anything else becomes UNKNOWN, which the withdrawal engine treats as
  "do not sell until a person confirms". A misread can therefore make Mifugo
  more cautious, never less.
"""

import re
from dataclasses import dataclass, field

from mifugo import llm
from mifugo.withdrawal import MAX_MEAT_DAYS, MAX_MILK_DAYS, Kind, Withdrawal

_WITHDRAWAL = {
    "type": "object",
    "properties": {
        "stated": {
            "type": "string",
            "enum": ["period", "zero", "not_for_lactating", "not_stated", "unreadable"],
        },
        "value": {"type": "number"},
        "unit": {"type": "string", "enum": ["hours", "days", "milkings", "none"]},
        "quote": {"type": "string"},
    },
    "required": ["stated", "value", "unit", "quote"],
}

LABEL_SCHEMA = {
    "type": "object",
    "properties": {
        "is_veterinary_label": {"type": "boolean"},
        "legibility": {"type": "string", "enum": ["clear", "partial", "unreadable"]},
        "product_name": {"type": "string"},
        "active_ingredients": {"type": "array", "items": {"type": "string"}},
        "milk": _WITHDRAWAL,
        "meat": _WITHDRAWAL,
        "several_species_listed": {"type": "boolean"},
    },
    "required": [
        "is_veterinary_label",
        "legibility",
        "product_name",
        "active_ingredients",
        "milk",
        "meat",
        "several_species_listed",
    ],
}

SYSTEM = """You read photographs of veterinary medicine packaging for a Kenyan dairy app.
Report only what is printed in the photo.

Rules:
- Copy the exact printed words of each withdrawal statement into "quote", character for character.
- Never recall, estimate or calculate a withdrawal period. If the photo does not show it, use "not_stated"; if it is printed but you cannot read it, use "unreadable". In both cases value is 0 and unit is "none".
- Milk and meat are separate statements. "Milk" is milk. "Meat", "slaughter", "offal", "carcass" and "edible tissues" are meat.
- "Milk: nil", "Milk: 0 days" or "no milk withdrawal" is stated "zero".
- If the label says not to use the product in animals producing milk for human consumption, milk.stated is "not_for_lactating".
- If periods are listed for several species, set several_species_listed to true and report the cattle period, quoting the cattle line.
- unit is "hours", "days" or "milkings", exactly as printed. Do not convert.
You do not give advice. You only read."""

USER = "Read the withdrawal periods on this packaging."

MILK_WORDS = re.compile(r"milk|maziwa|lactat", re.I)
MEAT_WORDS = re.compile(r"meat|slaughter|offal|carcass|tissue|edible|nyama|kuchinja", re.I)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
CATTLE_WORDS = re.compile(r"cattle|cows?\b|bovine|ng'?ombe", re.I)
OTHER_SPECIES = re.compile(
    r"sheep|goats?|camels?|pigs?|swine|poultry|chickens?|horses?|dogs?|cats?|kondoo|mbuzi|ngamia", re.I
)
ZERO_WORDS = re.compile(r"\b(0|zero|nil|nill)\b|no (milk |meat )?withdrawal", re.I)
NOT_WORDS = re.compile(r"\bnot\b|\bdo not\b|\bmust not\b|\bshould not\b|usitumie|isitumike", re.I)
UNIT_WORDS = {
    "days": re.compile(r"day|siku", re.I),
    "hours": re.compile(r"hour|\bhrs?\b|\d\s*h\b|\bsaa\b", re.I),
    "milkings": re.compile(r"milking|ukamuaji", re.I),
}


@dataclass
class LabelReading:
    product_name: str
    active_ingredients: list
    milk: Withdrawal
    meat: Withdrawal
    issues: list = field(default_factory=list)   # why something became UNKNOWN
    raw: dict = None                             # the model's reply, for audit
    source: str = "label_photo"

    @property
    def needs_confirmation(self):
        return Kind.UNKNOWN in (self.milk.kind, self.meat.kind)


def _after_keyword(quote, words, other):
    """
    The stretch of text after each mention of this field, up to the next
    mention of the other field. 'Cattle: meat 21 days, milk 4 days' gives
    'milk' -> [' 4 days'] and 'meat' -> [' 21 days, '], so a model that swaps
    the two numbers fails the check instead of passing it.
    """
    spans = []
    for m in words.finditer(quote):
        rest = quote[m.end():]
        stop = other.search(rest)
        spans.append(rest[: stop.start()] if stop else rest)
    return spans


def _cattle_text(quote):
    """Only the parts of a multi-species statement that are about cattle:
    from each cattle word up to the next other-species word."""
    parts = []
    for m in CATTLE_WORDS.finditer(quote):
        rest = quote[m.end():]
        stop = OTHER_SPECIES.search(rest)
        parts.append(rest[: stop.start()] if stop else rest)
    return " | ".join(parts)


def _first_numbers(spans):
    found = set()
    for span in spans:
        n = NUMBER.search(span)
        if n:
            found.add(float(n.group()))
    return found


def _check(field_name, data, several_species):
    """One withdrawal statement -> (Withdrawal, [issues])."""
    stated = data.get("stated")
    quote = (data.get("quote") or "").strip()
    words = MILK_WORDS if field_name == "milk" else MEAT_WORDS
    other = MEAT_WORDS if field_name == "milk" else MILK_WORDS
    units = ("hours", "days", "milkings") if field_name == "milk" else ("hours", "days")

    if stated in ("not_stated", "unreadable", None):
        return Withdrawal.unknown(quote), [f"{field_name}: {stated or 'missing'} on the photo"]

    if not quote:
        return Withdrawal.unknown(), [f"{field_name}: no printed words quoted as evidence"]
    if not words.search(quote):
        return Withdrawal.unknown(quote), [f"{field_name}: the quoted words do not mention {field_name}"]
    if several_species and stated == "period" and not CATTLE_WORDS.search(quote):
        return Withdrawal.unknown(quote), [f"{field_name}: several species listed and the quote does not name cattle"]

    # Where several species are listed, only the cattle text may supply a number.
    evidence = _cattle_text(quote) if several_species else quote
    spans = _after_keyword(evidence, words, other)

    if stated == "zero":
        if any(ZERO_WORDS.search(s) for s in spans) or re.search(r"no (milk |meat )?withdrawal", quote, re.I):
            return Withdrawal(Kind.ZERO, quote=quote), []
        return Withdrawal.unknown(quote), [f"{field_name}: 'zero' not supported by the quoted words"]

    if stated == "not_for_lactating":
        if field_name == "milk" and NOT_WORDS.search(quote):
            return Withdrawal(Kind.NOT_FOR_LACTATING, quote=quote), []
        return Withdrawal.unknown(quote), [f"{field_name}: 'not for lactating' not supported by the quoted words"]

    # stated == "period"
    value, unit = data.get("value"), data.get("unit")
    if not isinstance(value, (int, float)) or value <= 0 or unit not in units:
        return Withdrawal.unknown(quote), [f"{field_name}: period without a usable value and unit"]
    if float(value) not in _first_numbers(spans):
        return Withdrawal.unknown(quote), [
            f"{field_name}: {value:g} is not the number printed after the word '{field_name}'"
        ]
    if not any(UNIT_WORDS[unit].search(s) for s in spans):
        return Withdrawal.unknown(quote), [f"{field_name}: the unit '{unit}' is not printed with the {field_name} period"]

    w = Withdrawal(Kind.PERIOD, float(value), unit, quote)
    ceiling = MAX_MILK_DAYS if field_name == "milk" else MAX_MEAT_DAYS
    if w.days() > ceiling:
        return Withdrawal.unknown(quote), [f"{field_name}: {value:g} {unit} is implausible; treated as a misread"]
    return w, []


def validate(raw):
    """Model reply -> LabelReading. Pure Python; unit-tested without a model."""
    issues = []
    if not raw.get("is_veterinary_label", False):
        issues.append("the photo does not look like veterinary medicine packaging")
    if raw.get("legibility") == "unreadable":
        issues.append("the label could not be read")
    several = bool(raw.get("several_species_listed"))

    if issues:
        milk = Withdrawal.unknown()
        meat = Withdrawal.unknown()
    else:
        milk, milk_issues = _check("milk", raw.get("milk") or {}, several)
        meat, meat_issues = _check("meat", raw.get("meat") or {}, several)
        issues += milk_issues + meat_issues

    ingredients = [str(x).strip() for x in raw.get("active_ingredients") or [] if str(x).strip()]
    return LabelReading(
        product_name=(raw.get("product_name") or "").strip()[:80],
        active_ingredients=ingredients[:6],
        milk=milk,
        meat=meat,
        issues=issues,
        raw=raw,
    )


def read_label(image_bytes):
    """
    Photo bytes -> LabelReading. Never raises for a model problem: a failure
    returns a reading with UNKNOWN periods and the reason, so the farmer is
    sent to manual entry instead of being shown an error.
    """
    try:
        b64 = llm.encode_image(image_bytes)
    except Exception as exc:
        return LabelReading("", [], Withdrawal.unknown(), Withdrawal.unknown(),
                            [f"could not open the photo: {exc}"], None)
    try:
        raw = llm.backend().chat(SYSTEM, USER, LABEL_SCHEMA, images=[b64])
    except (llm.ModelUnavailable, ValueError) as exc:
        return LabelReading("", [], Withdrawal.unknown(), Withdrawal.unknown(),
                            [f"label reader unavailable: {exc}"], None)
    return validate(raw)
