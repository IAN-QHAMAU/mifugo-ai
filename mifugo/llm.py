"""
The only file that talks to a model.

Two backends serve the same Gemma calls:

  * ollama     Gemma on the laptop or a field box. No internet needed.
  * gemma_api  Google-hosted Gemma, for the public live demo.

`none` runs the app with no model at all: label photos cannot be read, so the
farmer types the period from the box, and the Swahili log falls back to the
deterministic matchers. That is a degraded mode, not a fake one.

Every call is constrained to a JSON schema. Ollama enforces it during
decoding; the hosted API is given the schema and the reply is still parsed and
validated by the caller, because no transport is trusted to be well-formed.
"""

import base64
import io
import json
import re
import urllib.error
import urllib.request

from mifugo import config


class ModelUnavailable(Exception):
    pass


def _post(url, payload, headers=None, timeout=None):
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout or config.TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise ModelUnavailable(f"HTTP {exc.code} from {url.split('?')[0]}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise ModelUnavailable(f"cannot reach {url.split('?')[0]}: {exc}") from exc


def loads_json(content):
    """Extract one JSON object from model text, tolerating code fences."""
    content = (content or "").strip()
    start, end = content.find("{"), content.rfind("}")
    if start == -1 or end < start:
        raise ValueError(f"no JSON object in model output: {content[:200]!r}")
    raw = content[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(raw)


def encode_image(data, max_edge=None):
    """Bytes of any common image -> base64 JPEG, downscaled for the model."""
    from PIL import Image, ImageOps

    max_edge = max_edge or config.IMAGE_MAX_EDGE
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_edge, max_edge))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return base64.b64encode(out.getvalue()).decode("ascii")


class Backend:
    name = "base"

    def available(self):
        raise NotImplementedError

    def chat(self, system, user, schema, images=None, temperature=0.0):
        """Returns a parsed dict. Raises ModelUnavailable or ValueError."""
        raise NotImplementedError

    def describe(self):
        return self.name


class OllamaBackend(Backend):
    name = "ollama"

    def __init__(self, url=None, model=None):
        self.url = (url or config.OLLAMA_URL).rstrip("/")
        self.model = model or config.OLLAMA_MODEL
        self._think_flag = True

    def describe(self):
        return f"Ollama · {self.model} (offline)"

    def available(self):
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=3):
                return True
        except Exception:
            return False

    def chat(self, system, user, schema, images=None, temperature=0.0):
        message = {"role": "user", "content": user}
        if images:
            message["images"] = images
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, message],
            "stream": False,
            "format": schema,
            "options": {"num_ctx": config.NUM_CTX, "temperature": temperature},
        }
        # Thinking traces break strict JSON and cost seconds on E4B.
        if self._think_flag:
            payload["think"] = False
        try:
            result = _post(self.url + "/api/chat", payload)
        except ModelUnavailable as exc:
            if self._think_flag and "HTTP 400" in str(exc):
                self._think_flag = False
                payload.pop("think")
                result = _post(self.url + "/api/chat", payload)
            else:
                raise
        return loads_json((result.get("message") or {}).get("content", ""))


class GemmaAPIBackend(Backend):
    """Google-hosted Gemma through the Generative Language API."""

    name = "gemma_api"

    def __init__(self, api_url=None, model=None, api_key=None):
        self.api_url = (api_url or config.GEMMA_API_URL).rstrip("/")
        self.model = model or config.GEMMA_API_MODEL
        self.api_key = api_key or config.GEMMA_API_KEY
        self._use_schema = True

    def describe(self):
        return f"Gemma API · {self.model} (online)"

    def available(self):
        return bool(self.api_key)

    def chat(self, system, user, schema, images=None, temperature=0.0):
        # Gemma on this API does not take a separate system instruction, so the
        # instruction and the schema travel in the user turn.
        text = (
            f"{system}\n\nReturn one JSON object that matches this JSON schema:\n"
            f"{json.dumps(schema)}\n\n{user}"
        )
        parts = [{"text": text}]
        for b64 in images or []:
            parts.append({"inlineData": {"mimeType": "image/jpeg", "data": b64}})
        gen = {"temperature": temperature}
        if self._use_schema:
            gen["responseMimeType"] = "application/json"
        payload = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}
        url = f"{self.api_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key}
        try:
            result = _post(url, payload, headers)
        except ModelUnavailable as exc:
            if self._use_schema and "HTTP 400" in str(exc):
                self._use_schema = False   # model does not support JSON mode
                payload["generationConfig"].pop("responseMimeType")
                result = _post(url, payload, headers)
            else:
                raise
        parts = ((result.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return loads_json("".join(p.get("text", "") for p in parts))


class NoModel(Backend):
    name = "none"

    def describe(self):
        return "No model (manual entry)"

    def available(self):
        return False

    def chat(self, system, user, schema, images=None, temperature=0.0):
        raise ModelUnavailable("no model configured (MIFUGO_BACKEND=none)")


class ScriptedBackend(Backend):
    """
    For tests only. Replies come from a function you supply, so a test states
    exactly what the model returned and checks what Python did with it.
    """

    name = "scripted"

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def available(self):
        return True

    def chat(self, system, user, schema, images=None, temperature=0.0):
        self.calls.append({"system": system, "user": user, "images": images or []})
        result = self.reply(system, user, images or [])
        if isinstance(result, Exception):
            raise result
        return result


_backend = None


def make_backend(name=None):
    name = (name or config.BACKEND).lower()
    if name == "ollama":
        return OllamaBackend()
    if name == "gemma_api":
        return GemmaAPIBackend()
    if name == "none":
        return NoModel()
    raise ValueError(f"unknown MIFUGO_BACKEND {name!r}")


def backend():
    global _backend
    if _backend is None:
        _backend = make_backend()
    return _backend


def set_backend(b):
    global _backend
    _backend = b
