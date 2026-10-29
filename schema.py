"""
Canonical vocabulary and the JSON schema handed to Ollama's structured-output
`format` field.

Why this file exists: Gemma is not asked to invent symptom names. It is
constrained by a closed enum, so the parse step cannot emit a token that the
Python routing table has never heard of. This removes the single most common
failure mode (model returns "drooling a lot" when the table expects
"salivation").
"""

SPECIES = ["cattle", "goat", "sheep", "camel", "chicken", "unknown"]

# Closed vocabulary. If you add a token here you MUST also use it in
# conditions.json or lexicon.json, otherwise it can never route anywhere.
CANONICAL_SYMPTOMS = [
    "salivation",
    "mouth_lesions",
    "foot_lesions",
    "teat_lesions",
    "lameness",
    "not_eating",
    "not_drinking",
    "weakness",
    "weight_loss",
    "pale_conjunctiva",
    "bottle_jaw",
    "diarrhoea",
    "bloody_diarrhoea",
    "nasal_discharge",
    "ocular_discharge",
    "coughing",
    "difficulty_breathing",
    "swollen_lymph_nodes",
    "fever",
    "distended_left_flank",
    "rapid_bloating",
    "distress",
    "recumbent",
    "abortion",
    "skin_lesions",
    "sudden_death",
    "bleeding_from_orifices",
    # --- poultry ---------------------------------------------------------
    "pale_comb",
    "cyanotic_comb",
    "swollen_head",
    "green_white_droppings",
    "ruffled_feathers",
    "twisted_neck",
    "drop_in_egg_production",
    "sudden_high_mortality",
]

# Fields Python needs before it will issue a verdict, in the order it will
# ask for them. Python owns this list, not the model.
REQUIRED_FIELDS = ["species", "animals_affected", "duration_days", "herd_size"]

FIELD_LABELS_SW = {
    "species": "aina ya mnyama (ng'ombe, mbuzi, kondoo, ngamia, kuku)",
    "animals_affected": "idadi ya wanyama walioathirika",
    "duration_days": "idadi ya siku tangu dalili zianze",
    "herd_size": "idadi ya wanyama wote katika kundi",
}

PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "species": {"type": "string", "enum": SPECIES},
        "symptoms": {
            "type": "array",
            "items": {"type": "string", "enum": CANONICAL_SYMPTOMS},
        },
        "duration_days": {"type": ["integer", "null"]},
        "animals_affected": {"type": ["integer", "null"]},
        "herd_size": {"type": ["integer", "null"]},
        "sudden_death": {"type": "boolean"},
        "bleeding_from_orifices": {"type": "boolean"},
    },
    "required": [
        "species",
        "symptoms",
        "duration_days",
        "animals_affected",
        "herd_size",
        "sudden_death",
        "bleeding_from_orifices",
    ],
}

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {"question_sw": {"type": "string"}},
    "required": ["question_sw"],
}

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {"message_sw": {"type": "string"}},
    "required": ["message_sw"],
}


def empty_parse():
    """A safe, fully-populated blank parse. Used when the model fails."""
    return {
        "species": "unknown",
        "symptoms": [],
        "duration_days": None,
        "animals_affected": None,
        "herd_size": None,
        "sudden_death": False,
        "bleeding_from_orifices": False,
    }


def coerce_parse(raw):
    """
    Defensive normalisation. Never trust the model's output shape even when a
    schema was supplied — a truncated generation can still produce junk.
    """
    out = empty_parse()
    if not isinstance(raw, dict):
        return out

    species = raw.get("species")
    if isinstance(species, str) and species.lower() in SPECIES:
        out["species"] = species.lower()

    syms = raw.get("symptoms")
    if isinstance(syms, list):
        out["symptoms"] = sorted(
            {s for s in syms if isinstance(s, str) and s in CANONICAL_SYMPTOMS}
        )

    for key in ("duration_days", "animals_affected", "herd_size"):
        val = raw.get(key)
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)) and val >= 0:
            out[key] = int(val)

    for key in ("sudden_death", "bleeding_from_orifices"):
        out[key] = bool(raw.get(key))

    return out