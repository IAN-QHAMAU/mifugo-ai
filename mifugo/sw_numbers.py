"""
Deterministic Swahili numeral parsing.

Used where Python must read a number from the farmer's own words without
trusting the model: "siku tatu zilizopita", "saa kumi na moja jioni",
"dozi mbili".
"""

import re

from mifugo.text import normalise

UNITS = {
    "moja": 1, "mmoja": 1,
    "mbili": 2, "wawili": 2,
    "tatu": 3, "watatu": 3,
    "nne": 4, "wanne": 4,
    "tano": 5, "watano": 5,
    "sita": 6, "wasita": 6,
    "saba": 7, "wasaba": 7,
    "nane": 8, "wanane": 8,
    "tisa": 9, "watisa": 9, "kenda": 9,
}

TENS = {
    "kumi": 10,
    "ishirini": 20,
    "thelathini": 30,
    "arobaini": 40,
    "hamsini": 50,
    "sitini": 60,
    "sabini": 70,
    "themanini": 80,
    "tisini": 90,
}

MULT = {"mia": 100, "elfu": 1000}

ZERO = {"sifuri", "hakuna", "hamna"}

WORDS = set(UNITS) | set(TENS) | set(MULT) | {"na"}


def parse_number(text):
    """
    Returns an int, or None if no number is present.

    Handles digits first, then Swahili numerals including compounds:
      "15"                    -> 15
      "kumi na tano"          -> 15
      "mbuzi watatu"          -> 3
      "mia mbili na ishirini" -> 220
    """
    if not text:
        return None

    digits = re.search(r"\d+", text)
    if digits:
        return int(digits.group())

    tokens = normalise(text).split()
    if any(t in ZERO for t in tokens):
        return 0

    total = 0
    found = False
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in MULT:
            multiplier = 1
            if i + 1 < len(tokens) and tokens[i + 1] in UNITS:
                multiplier = UNITS[tokens[i + 1]]
                i += 1
            total += MULT[token] * multiplier
            found = True
        elif token in TENS:
            total += TENS[token]
            found = True
        elif token in UNITS:
            total += UNITS[token]
            found = True
        i += 1

    return total if found else None
