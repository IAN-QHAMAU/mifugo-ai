"""Text normalisation shared by every deterministic matcher."""

import re
import unicodedata


def normalise(text):
    """Lowercase, strip accents, collapse apostrophe variants and whitespace."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9':\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()
