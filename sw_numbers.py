"""
Deterministic number extraction from a herder's answer.

Python asked the question, so Python reads the answer. This means the
elicitation loop closes even when the model is unavailable, mis-parses, or is
running in MOCK_MODE — and it stops the loop asking the same question three
times, which is the failure you would hit live on stage.

Only applied to the answer of a specific elicited field, never to the free-text
description, so "siku mbili" cannot be mistaken for an animal count.
"""

import re

from lexicon import normalise

UNITS = {
    "moja": 1, "mmoja": 1, "moja": 1,
    "mbili": 2, "wawili": 2, "mbili": 2,
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


def parse_number(text):
    """
    Returns an int, or None if no number is present.

    Handles digits first, then Swahili numerals including compounds:
      "15"                    -> 15
      "kumi na tano"          -> 15
      "mbuzi watatu"          -> 3
      "mia mbili na ishirini" -> 220
      "sitini"                -> 60
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
