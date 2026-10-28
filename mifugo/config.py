"""Environment configuration. Every knob has a default that runs offline."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BACKEND = os.environ.get("MIFUGO_BACKEND", "ollama")          # ollama | gemma_api | none
OLLAMA_URL = os.environ.get("MIFUGO_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("MIFUGO_MODEL", "gemma4:e4b")
NUM_CTX = int(os.environ.get("MIFUGO_NUM_CTX", "8192"))
GEMMA_API_URL = os.environ.get(
    "MIFUGO_GEMMA_API_URL", "https://generativelanguage.googleapis.com/v1beta"
)
GEMMA_API_KEY = os.environ.get("MIFUGO_GEMMA_API_KEY", "")
GEMMA_API_MODEL = os.environ.get("MIFUGO_GEMMA_MODEL", "gemma-4-26b-a4b-it")
TIMEOUT = int(os.environ.get("MIFUGO_TIMEOUT", "180"))

DB_PATH = Path(os.environ.get("MIFUGO_DB", ROOT / "data" / "mifugo.db"))
UPLOAD_DIR = Path(os.environ.get("MIFUGO_UPLOADS", ROOT / "data" / "uploads"))

# Longest edge, in pixels, of a label photo sent to the model. Small print on
# a drug box needs resolution; 1600 keeps it legible without a slow request.
IMAGE_MAX_EDGE = int(os.environ.get("MIFUGO_IMAGE_MAX_EDGE", "1600"))
