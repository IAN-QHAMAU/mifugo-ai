"""
Deterministic vernacular matching over the raw herder text.

Runs entirely in Python. Nothing here calls the model. Its output is unioned
with Gemma's parse, so a term the model missed still reaches the routing table,
and — critically — the anthrax trigger has a path that does not depend on a
model-authored boolean.
"""

import json
import re
import unicodedata
from pathlib import Path

_DIR = Path(__file__).resolve().parent
LEXICON = json.loads((_DIR / "lexicon.json").read_text(encoding="utf-8"))


def normalise(text):
    """Lowercase, strip accents, collapse apostrophe variants and whitespace."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = text.replace("\u2019", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _hits(haystack, terms):
    found = []
    for term in terms:
        needle = normalise(term)
        if not needle:
            continue
        pattern = r"(?<![a-z'])" + re.escape(needle) + r"(?![a-z'])"
        if re.search(pattern, haystack):
            found.append(term)
    return found


def scan(text):
    """
    Returns everything the lexicon can find in one pass.

    {
      "species": "cattle" | None,
      "symptoms": {token, ...},
      "condition_hints": {condition_id, ...},
      "carcass_context": bool,
      "matched_terms": {token: [term, ...]}
    }
    """
    hay = normalise(text)
    result = {
        "species": None,
        "symptoms": set(),
        "condition_hints": set(),
        "carcass_context": False,
        "matched_terms": {},
    }
    if not hay:
        return result

    for species, terms in LEXICON["species_terms"].items():
        if _hits(hay, terms):
            result["species"] = species
            break

    for token, terms in LEXICON["symptom_terms"].items():
        found = _hits(hay, terms)
        if found:
            result["symptoms"].add(token)
            result["matched_terms"][token] = found

    for cond_id, terms in LEXICON["condition_hint_terms"].items():
        if _hits(hay, terms):
            result["condition_hints"].add(cond_id)

    result["carcass_context"] = bool(_hits(hay, LEXICON["carcass_context_terms"]))
    return result


def scan_all(texts):
    """Scan the original description plus every follow-up answer."""
    merged = {
        "species": None,
        "symptoms": set(),
        "condition_hints": set(),
        "carcass_context": False,
        "matched_terms": {},
    }
    for text in texts:
        one = scan(text)
        merged["species"] = merged["species"] or one["species"]
        merged["symptoms"] |= one["symptoms"]
        merged["condition_hints"] |= one["condition_hints"]
        merged["carcass_context"] = merged["carcass_context"] or one["carcass_context"]
        for token, terms in one["matched_terms"].items():
            merged["matched_terms"].setdefault(token, []).extend(terms)
    return merged
