"""
The only file that talks to the model.

Three jobs, all language jobs:
  A. parse   - messy Swahili/Sheng -> constrained JSON
  B. elicit  - one natural follow-up question in Swahili
  C. explain - reword a Python-authored verdict in warm plain Swahili

Notes on Ollama configuration that will bite you otherwise:
  * num_ctx defaults far below Gemma 4's real window. Set it explicitly.
  * Gemma 4 has configurable thinking. Reasoning traces break strict JSON and
    destroy latency on E4B, so thinking is off for every call here.
  * `format` takes a JSON schema, which is enforced during decoding. This is
    much stronger than asking the model nicely for JSON in the prompt.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from schema import (
    EXPLAIN_SCHEMA,
    PARSE_SCHEMA,
    QUESTION_SCHEMA,
    coerce_parse,
    empty_parse,
)

_DIR = Path(__file__).resolve().parent

OLLAMA_URL = os.environ.get("MIFUGO_OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.environ.get("MIFUGO_MODEL", "gemma4:e4b")
NUM_CTX = int(os.environ.get("MIFUGO_NUM_CTX", "8192"))
TIMEOUT = int(os.environ.get("MIFUGO_TIMEOUT", "120"))
MOCK_MODE = os.environ.get("MIFUGO_MOCK", "0") == "1"

MOCKS = json.loads((_DIR / "mock_responses.json").read_text(encoding="utf-8"))

_supports_think_flag = True


class ModelUnavailable(Exception):
    pass


# ---------------------------------------------------------------------------
# transport
# ---------------------------------------------------------------------------

def _post(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ModelUnavailable(f"Ollama unreachable at {OLLAMA_URL}: {exc}") from exc


def is_available():
    if MOCK_MODE:
        return True
    try:
        req = urllib.request.Request(OLLAMA_URL + "/api/tags")
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def _chat(system, user, fmt, temperature=0.0, images=None):
    global _supports_think_flag

    message = {"role": "user", "content": user}
    if images:
        message["images"] = images

    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, message],
        "stream": False,
        "format": fmt,
        "options": {
            "num_ctx": NUM_CTX,
            "temperature": temperature,
            "top_p": 0.9,
        },
    }
    if _supports_think_flag:
        payload["think"] = False

    try:
        result = _post("/api/chat", payload)
    except ModelUnavailable:
        raise
    except Exception:
        if _supports_think_flag:
            _supports_think_flag = False
            payload.pop("think", None)
            result = _post("/api/chat", payload)
        else:
            raise

    content = (result.get("message") or {}).get("content", "")
    return _loads(content)


def _loads(content):
    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.split("\n", 1)[-1] if "\n" in content else content
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model output: {content[:200]!r}")
    return json.loads(content[start : end + 1])


# ---------------------------------------------------------------------------
# Job A - parse
# ---------------------------------------------------------------------------

PARSE_SYSTEM = """You are a translation and extraction tool for a Kenyan livestock triage app.
You read what a herder wrote in Swahili, Sheng, English or a mixture, and you extract facts.

Rules:
- Extract only what the herder actually said. Never infer a symptom that was not described.
- symptoms must come from the allowed list only. If a described sign has no matching entry, leave it out.
- Numbers: duration_days is days since signs began. animals_affected is how many animals show signs. herd_size is the total number of animals owned. Use null when the herder did not say.
- sudden_death is true if any animal died quickly or was found dead.
- bleeding_from_orifices is true if blood was described from nose, mouth, ears or anus, or blood that does not clot.
- You do not diagnose. You do not give advice. You only extract.
Return JSON only."""


def parse_description(text, history=None):
    """history: list of (question_sw, answer) already collected."""
    if MOCK_MODE:
        return coerce_parse(_mock_for(text)["parse"])

    convo = text
    for question, answer in history or []:
        convo += f"\n\nSwali: {question}\nJibu: {answer}"

    user = (
        "Allowed symptom values:\n"
        + ", ".join(PARSE_SCHEMA["properties"]["symptoms"]["items"]["enum"])
        + "\n\nHerder's description:\n"
        + convo
    )
    try:
        raw = _chat(PARSE_SYSTEM, user, PARSE_SCHEMA, temperature=0.0)
    except (ModelUnavailable, ValueError, json.JSONDecodeError):
        # Fail soft. The lexicon backstop in router.py and safety_rules.py runs
        # over the raw text regardless, so a total parse failure still reaches
        # the anthrax check.
        return empty_parse()
    return coerce_parse(raw)


# ---------------------------------------------------------------------------
# Job B - elicit
# ---------------------------------------------------------------------------

ELICIT_SYSTEM = """You write ONE short follow-up question in simple Swahili for a Kenyan herder.
The question asks for exactly one missing piece of information, named below.
Be warm and plain. No greetings, no explanation, no medical advice, no diagnosis.
One sentence. Return JSON only."""


def elicit_question(missing_field, field_label_sw, parsed):
    if MOCK_MODE:
        return MOCKS["elicit_by_field"].get(
            missing_field, "Tafadhali niambie zaidi kuhusu mnyama wako."
        )

    user = (
        f"Missing information: {field_label_sw}\n"
        f"What we already know: {json.dumps(parsed, ensure_ascii=False)}\n"
        "Write the question."
    )
    try:
        return _chat(ELICIT_SYSTEM, user, QUESTION_SCHEMA, temperature=0.4)[
            "question_sw"
        ].strip()
    except Exception:
        return MOCKS["elicit_by_field"].get(
            missing_field, "Tafadhali niambie zaidi kuhusu mnyama wako."
        )


# ---------------------------------------------------------------------------
# Job C - explain
# ---------------------------------------------------------------------------

EXPLAIN_SYSTEM = """You are a translator for a Kenyan livestock triage app.
You are given a verdict that has ALREADY been decided by the app's rules.

Your only job is to say the same thing in warm, plain Swahili a herder with no
formal veterinary training will understand.

Absolute rules:
- Do not change the condition, the instruction, or the urgency.
- Do not add treatments, drug names, dosages, or advice that is not in the input.
- Do not remove or soften any instruction.
- Do not add a greeting or a sign-off.
- 3 to 5 short sentences.
Return JSON only."""


def explain_verdict(payload):
    if MOCK_MODE:
        return _mock_for(payload.get("_source_text", ""))["explain_sw"]
    try:
        return _chat(
            EXPLAIN_SYSTEM,
            json.dumps(payload, ensure_ascii=False, indent=2),
            EXPLAIN_SCHEMA,
            temperature=0.5,
        )["message_sw"].strip()
    except Exception:
        return None  # caller falls back to the English literals


# ---------------------------------------------------------------------------
# mock selection
# ---------------------------------------------------------------------------

def _mock_for(text):
    from lexicon import normalise

    hay = normalise(text)
    for scenario in MOCKS["scenarios"]:
        if any(normalise(k) in hay for k in scenario["match_any"]):
            return scenario
    # No scenario matched. Return a blank parse rather than inheriting the
    # first scenario's symptoms, which would fabricate a diagnosis in MOCK_MODE.
    return MOCKS["default"]
