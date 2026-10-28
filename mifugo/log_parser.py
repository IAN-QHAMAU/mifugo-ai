"""
Gemma job 2: understand what the farmer wrote.

"Nimemdunga Njeri sindano ya mastitis jana jioni"
"Naweza kuuza maziwa ya Baraka leo?"
"Ng'ombe gani hawafai kukamuliwa kwa mauzo?"

Gemma turns that into a closed structure: what the farmer is doing, which
animals, which medicine, and when. Python then does three things the model
is never trusted with:

  * maps the names onto the farm's real herd (an unknown name is shown back to
    the farmer, never silently created),
  * reads the time phrase itself as a backstop and keeps the later reading,
  * turns the phrase into a timestamp (timewords.py).

If the model is down, the deterministic matchers still read names, intent and
time, so logging and asking keep working with less tolerance for messy text.
"""

import difflib
import re
from dataclasses import dataclass, field

from mifugo import llm
from mifugo.text import normalise
from mifugo.timewords import WHEN_VALUES, Resolved, WhenPhrase, combine, scan

INTENTS = ["log_treatment", "ask_milk", "ask_herd", "other"]

LOG_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "animal_names": {"type": "array", "items": {"type": "string"}},
        "product_mention": {"type": "string"},
        "when": {"type": "string", "enum": WHEN_VALUES},
        "days_ago": {"type": "integer"},
        "clock": {"type": "string"},
    },
    "required": ["intent", "animal_names", "product_mention", "when", "days_ago", "clock"],
}

SYSTEM = """You read short messages from Kenyan dairy farmers, written in Swahili, Sheng, English or a mixture.
You extract facts. You never give advice and never say whether milk is safe.

- intent:
  "log_treatment" when the farmer reports giving a medicine, injection (sindano), udder tube, dewormer, drench or spray to an animal.
  "ask_milk" when the farmer asks whether the milk of particular animals can be sold or used.
  "ask_herd" when the farmer asks which animals are affected, or about the whole herd.
  "other" for anything else.
- animal_names: the animal names the farmer used. The farm's herd is listed below; use those spellings when the farmer clearly means one of them.
- product_mention: the medicine name as the farmer wrote it, or "".
- when: when the medicine was given. Use "unknown" if the farmer did not say. days_ago is a number only when when is "days_ago", otherwise 0.
- clock: an exact time if the farmer said one, as 24-hour "HH:MM", otherwise "". Swahili time starts at 06:00: "saa mbili asubuhi" is 08:00, "saa mbili usiku" is 20:00, "saa kumi na moja jioni" is 17:00.
Return JSON only."""

ASK = re.compile(
    r"\bnaweza\b|\bnaeza\b|\binaweza\b|\bninaweza\b|\bniuze\b|\bnimuuze\b|"
    r"\byanafaa\b|\bni salama\b|\bcan i\b|\bcan we\b|\bis it safe\b|\bok to sell\b"
)
HERD = re.compile(r"ng'?ombe gani|\bgani\b|which cows?|\bwote\b|\ball\b|\bherd\b|\bkundi\b")
MILK = re.compile(r"\bmaziwa\b|\bmilk\b")
# Swahili verbs carry their subject and object as prefixes (ni-me-m-tibu,
# a-li-dung-wa), so verb stems are matched inside words, not at boundaries.
TREAT = re.compile(
    r"dung|sindano|inject|\bdawa\b|tibu|tibiwa|\btreat|\btube\b|\bdozi\b|\bdose|"
    r"mpa\b|wapa\b|pewa\b|spray|nyunyiz|drench|minyoo|deworm"
)


@dataclass
class ParsedLog:
    intent: str
    animals: list                      # names from the herd
    unmatched: list                    # names the farmer used that are not in the herd
    product_mention: str
    given_at: Resolved
    model_used: bool
    notes: list = field(default_factory=list)


def scan_intent(text, herd=()):
    """Intent from word lists alone. A question about a named cow is about
    her milk; a question naming no cow is about the herd."""
    hay = normalise(text)
    if "?" in (text or "") or ASK.search(hay):
        if scan_names(text, herd):
            return "ask_milk"
        if HERD.search(hay) or not MILK.search(hay):
            return "ask_herd"
        return "ask_milk"
    if TREAT.search(hay):
        return "log_treatment"
    return None


def scan_names(text, herd):
    """Herd names that appear verbatim in the text. No model."""
    hay = normalise(text)
    found = []
    for name in herd:
        needle = normalise(name)
        if needle and re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", hay):
            found.append(name)
    return found


def match_names(names, herd):
    """Model-reported names -> (herd names, names not in the herd)."""
    by_norm = {normalise(h): h for h in herd}
    matched, unmatched = [], []
    for name in names or []:
        key = normalise(name)
        if not key:
            continue
        if key in by_norm:
            matched.append(by_norm[key])
            continue
        close = difflib.get_close_matches(key, list(by_norm), n=1, cutoff=0.8)
        if close:
            matched.append(by_norm[close[0]])
        else:
            unmatched.append(name.strip())
    return matched, unmatched


def _model_phrase(raw):
    when = raw.get("when") if raw.get("when") in WHEN_VALUES else "unknown"
    days = raw.get("days_ago") if when == "days_ago" and isinstance(raw.get("days_ago"), int) else None
    clock = raw.get("clock") if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", raw.get("clock") or "") else None
    return WhenPhrase(when, days, clock)


def parse(text, herd, now):
    herd = list(herd)
    lexicon_phrase = scan(text)
    lexicon_names = scan_names(text, herd)
    notes = []

    try:
        user = (
            "Herd: " + (", ".join(herd) if herd else "(no animals registered)")
            + "\n\nFarmer's message:\n" + text
        )
        raw = llm.backend().chat(SYSTEM, user, LOG_SCHEMA)
        model_used = True
    except (llm.ModelUnavailable, ValueError) as exc:
        raw, model_used = {}, False
        notes.append(f"model unavailable, read with the Swahili word lists only ({exc.__class__.__name__})")

    model_intent = raw.get("intent") if raw.get("intent") in INTENTS else None
    intent = model_intent if model_intent and model_intent != "other" else (scan_intent(text, herd) or "other")

    matched, unmatched = match_names(raw.get("animal_names"), herd)
    animals = list(dict.fromkeys(matched + lexicon_names))
    unmatched = [u for u in unmatched if normalise(u) not in {normalise(a) for a in animals}]

    model_phrase = _model_phrase(raw) if model_used else None
    given_at = combine(model_phrase, lexicon_phrase, now)
    if given_at.assumed and intent == "log_treatment":
        notes.append("no time given: the withdrawal is counted from now")

    product = (raw.get("product_mention") or "").strip()[:80]
    return ParsedLog(intent, animals, unmatched, product, given_at, model_used, notes)
