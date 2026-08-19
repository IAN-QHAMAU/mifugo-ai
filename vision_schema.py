"""
Closed vocabulary for what the model is allowed to say it saw.

Same principle as schema.py: the model cannot emit a token the Python mapping
table has never heard of. Every entry here must appear in vision_rules.py,
otherwise it can never affect a verdict and is dead weight.

Note what is absent from this list: any disease name, any severity word, any
number, any score. Those are Python's, downstream.
"""

VISION_OBSERVATIONS = [
    # Mucous membrane colour — ruminants (inner lower eyelid)
    "conjunctiva_deep_red",
    "conjunctiva_red_pink",
    "conjunctiva_pink",
    "conjunctiva_pink_white",
    "conjunctiva_white",
    # Mucous membrane colour — poultry (comb and wattle)
    "comb_bright_red",
    "comb_pale",
    "comb_blue_purple",
    "comb_shrunken",
    # Lesions
    "mouth_lesions_visible",
    "foot_lesions_visible",
    "skin_lesions_visible",
    "skin_lesions_black_scab",
    "teat_lesions_visible",
    # Discharge
    "nasal_discharge_visible",
    "ocular_discharge_visible",
    "frothy_salivation_visible",
    # Swelling
    "swollen_jaw_underside",       # bottle jaw
    "swollen_lymph_node_visible",
    "swollen_head_or_face",
    "distended_left_flank",
    "abdomen_distended",
    # Droppings and discharge on ground
    "diarrhoea_visible",
    "bloody_diarrhoea_visible",
    "green_white_droppings",
    # Posture and condition
    "animal_recumbent",
    "visible_emaciation",
    "ruffled_feathers",
    "twisted_neck_posture",
    # Carcass indicators — these route to the zoonotic path
    "carcass_bloated",
    "blood_from_orifices_visible",
    # Escape hatch
    "image_unusable",
]

BODY_PARTS = [
    "eyelid_conjunctiva",
    "mouth_or_gums",
    "teat_or_udder",
    "comb_wattle",
    "foot_or_hoof",
    "skin",
    "whole_animal",
    "droppings",
    "carcass",
    "unclear",
]

IMAGE_QUALITY = ["good", "poor", "unusable"]

OBSERVATION_SCHEMA = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {"type": "string", "enum": VISION_OBSERVATIONS},
        },
        "image_quality": {"type": "string", "enum": IMAGE_QUALITY},
        "body_part_visible": {"type": "string", "enum": BODY_PARTS},
        "note": {"type": "string"},
        "regions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "box": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                },
                "required": ["label", "box"],
            },
        },
    },
    "required": ["observations", "image_quality", "body_part_visible"],
}


def empty_observation():
    return {
        "observations": [],
        "image_quality": "unusable",
        "body_part_visible": "unclear",
        "note": "",
        "regions": [],
        # Distinguishes "the model could not run" from "the photo is unreadable".
        # Telling someone to retake a photo when the real fault is a missing
        # model sends them to fix the wrong thing.
        "error": None,
    }


def coerce_observation(raw):
    """Defensive normalisation. A schema-constrained decode can still truncate."""
    out = empty_observation()
    if not isinstance(raw, dict):
        return out

    obs = raw.get("observations")
    if isinstance(obs, list):
        out["observations"] = sorted(
            {o for o in obs if isinstance(o, str) and o in VISION_OBSERVATIONS}
        )

    q = raw.get("image_quality")
    if isinstance(q, str) and q in IMAGE_QUALITY:
        out["image_quality"] = q
    elif out["observations"]:
        out["image_quality"] = "good"

    bp = raw.get("body_part_visible")
    if isinstance(bp, str) and bp in BODY_PARTS:
        out["body_part_visible"] = bp

    err = raw.get("error")
    if isinstance(err, str):
        out["error"] = err

    note = raw.get("note")
    if isinstance(note, str):
        out["note"] = note.strip()[:240]

    regions = raw.get("regions")
    if isinstance(regions, list):
        clean = []
        for r in regions[:4]:
            if not isinstance(r, dict):
                continue
            box = r.get("box")
            label = r.get("label")
            if (
                isinstance(box, list)
                and len(box) == 4
                and all(isinstance(v, (int, float)) for v in box)
            ):
                x0, y0, x1, y1 = (max(0, min(1000, int(v))) for v in box)
                if x1 > x0 and y1 > y0:
                    clean.append(
                        {
                            "label": str(label or "region")[:40],
                            "box": [x0, y0, x1, y1],
                        }
                    )
        out["regions"] = clean

    # An unusable image reports nothing else. Enforced here, not trusted to
    # the model's compliance with the prompt.
    if out["image_quality"] == "unusable" or "image_unusable" in out["observations"]:
        out["observations"] = []
        out["image_quality"] = "unusable"
        out["regions"] = []

    return out