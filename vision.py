"""
Layer 3 — vision.

The architecture rule applies here exactly as it does to text, and it is the
single most important thing about this file:

    Gemma DESCRIBES what is in the photograph.
    Gemma NEVER scores, grades, or diagnoses from it.

The model returns observations drawn from a closed vocabulary. Python maps
those observations onto the same symptom tokens the text pipeline produces,
and the existing router and safety rules take it from there. A photograph is
just another way of getting facts into the deterministic pipeline.

Why this matters, concretely: FAMACHA anaemia scoring is a five-band colour
judgement with published false-positive rates of roughly 10-21% even among
trained human scorers. Asking a 2B-4B model to output "score 4" hides that
uncertainty inside a number that looks authoritative. Asking it to say
"the membrane is pink-white" and letting Python own the band keeps the
judgement inspectable and keeps the threshold in version control.

Licence note: the FAMACHA(c) chart is copyrighted and is deliberately NOT
reproduced, embedded, or shipped with this application. Mifugo asks the model
for a plain colour description and maps that description to a band in code.
"""

import base64
import io
import json

import gemma
from vision_schema import (
    OBSERVATION_SCHEMA,
    VISION_OBSERVATIONS,
    coerce_observation,
    empty_observation,
)

MAX_EDGE = 896  # Gemma 4 vision tiles around this; larger just costs latency.


# ---------------------------------------------------------------------------
# image preparation
# ---------------------------------------------------------------------------

def encode_image(file_or_bytes):
    """
    Accepts a Streamlit UploadedFile, a path, raw bytes, or a PIL image.
    Returns a base64 string suitable for Ollama's `images` array.

    Downscaling happens here rather than being left to the server because a
    12MP phone photo through an E4B vision tower on CPU is the difference
    between a 4 second demo and a 40 second one.
    """
    try:
        from PIL import Image
    except ImportError:  # Pillow missing — send the bytes untouched.
        raw = _raw_bytes(file_or_bytes)
        return base64.b64encode(raw).decode("ascii")

    if isinstance(file_or_bytes, Image.Image):
        img = file_or_bytes
    else:
        img = Image.open(io.BytesIO(_raw_bytes(file_or_bytes)))

    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_EDGE:
        scale = MAX_EDGE / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _raw_bytes(obj):
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj)
    if hasattr(obj, "read"):
        data = obj.read()
        if hasattr(obj, "seek"):
            obj.seek(0)
        return data
    with open(obj, "rb") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Job D — observe
# ---------------------------------------------------------------------------

OBSERVE_SYSTEM = """You are an observation tool for a Kenyan livestock triage app.
You look at one photograph of an animal and report ONLY what is visibly present.

Absolute rules:
- You do NOT diagnose. You do NOT name a disease. You do NOT give advice.
- You do NOT score, grade, or rate anything on any scale.
- Report only observations from the allowed list. If you are unsure whether
  something is present, do not report it.
- If the image is too dark, too blurry, out of focus, taken from too far away,
  or does not clearly show an animal or animal part, report image_unusable and
  report nothing else.
- If you cannot see the specific body part clearly, do not guess its colour.

For colour of a mucous membrane (inner lower eyelid, gum, comb, wattle), choose
the single closest description. Describe what you see, not what it means.

Return JSON only."""

OBSERVE_USER_TEMPLATE = """Allowed observations:
{allowed}

Animal type stated by the herder: {species}
Body part the herder says they photographed: {body_part}

Report what is visible in this photograph."""


def observe(image, species="unknown", body_part="unspecified"):
    """
    Returns a coerced observation dict:

      {
        "observations": [token, ...],
        "image_quality": "good" | "poor" | "unusable",
        "body_part_visible": "eyelid_conjunctiva" | "comb_wattle" | ...,
        "note": "short free text, display only, never routed",
        "regions": [{"label": str, "box": [x0,y0,x1,y1]}]   # 0-1000 normalised
      }
    """
    if gemma.MOCK_MODE:
        return coerce_observation(_mock_observation(body_part))

    b64 = encode_image(image)
    user = OBSERVE_USER_TEMPLATE.format(
        allowed=", ".join(VISION_OBSERVATIONS),
        species=species or "unknown",
        body_part=body_part or "unspecified",
    )

    try:
        raw = gemma._chat(
            OBSERVE_SYSTEM,
            user,
            OBSERVATION_SCHEMA,
            temperature=0.0,
            images=[b64],
        )
    except Exception:
        # Vision failing must never take the text pipeline down with it.
        out = empty_observation()
        out["image_quality"] = "unusable"
        out["error"] = "model_unavailable"
        return out

    return coerce_observation(raw)


def _mock_observation(body_part):
    if body_part == "comb_wattle":
        return {
            "observations": ["comb_pale"],
            "image_quality": "good",
            "body_part_visible": "comb_wattle",
            "note": "Comb appears markedly pale against the feathering.",
            "regions": [{"label": "comb", "box": [380, 90, 640, 300]}],
        }
    return {
        "observations": ["conjunctiva_pink_white"],
        "image_quality": "good",
        "body_part_visible": "eyelid_conjunctiva",
        "note": "Inner lower eyelid membrane is pale, close to white.",
        "regions": [{"label": "lower eyelid membrane", "box": [300, 380, 700, 560]}],
    }