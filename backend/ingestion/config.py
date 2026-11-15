"""Configuration and environment settings for VivaVoce M2 ingestion, sandbox & demo modules."""

import logging
import os
import tempfile
from pathlib import Path

# Base paths built strictly from __file__
_BACKEND_DIR_PATH = Path(__file__).resolve().parent.parent
BACKEND_DIR: str = str(_BACKEND_DIR_PATH)
DEMO_CACHE_DIR: str = str(_BACKEND_DIR_PATH / "demo_cache")
REPLAY_DIR: str = str(_BACKEND_DIR_PATH / "demo_cache" / "replay")
WORK_DIR: str = str(Path(tempfile.gettempdir()) / "vivavoce")

# Best-effort dotenv loading (never crashes even if python-dotenv is missing or .env is absent)
try:
    from dotenv import load_dotenv

    _env_file = _BACKEND_DIR_PATH / ".env"
    if _env_file.exists():
        load_dotenv(dotenv_path=_env_file)
except Exception:
    pass


def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or not val.strip():
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Constants from env with defaults
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_TIMEOUT_S: int = _get_int("GEMINI_TIMEOUT_S", 30)
CLONE_TIMEOUT_S: int = _get_int("CLONE_TIMEOUT_S", 45)
CLONE_DEPTH: int = _get_int("CLONE_DEPTH", 50)
FULL_CLONE_MAX_KB: int = _get_int("FULL_CLONE_MAX_KB", 20000)
MAX_INDEXED_FILES: int = _get_int("MAX_INDEXED_FILES", 15)
MAX_FILE_LINES: int = _get_int("MAX_FILE_LINES", 2000)
MAX_REPO_PY_FILES: int = _get_int("MAX_REPO_PY_FILES", 2000)
SANDBOX_TIMEOUT_S: int = _get_int("SANDBOX_TIMEOUT_S", 8)
SANDBOX_OUTPUT_LIMIT: int = _get_int("SANDBOX_OUTPUT_LIMIT", 8000)
DEMO_REPO_URL: str = os.getenv(
    "DEMO_REPO_URL", "https://github.com/shreyas-269/vivavoce-demo-repo"
)
DEMO_REPLAY: bool = _get_bool("DEMO_REPLAY", False)
DEMO_RECORD: bool = _get_bool("DEMO_RECORD", False)

# Logger for ingestion
log: logging.Logger = logging.getLogger("vivavoce.ingestion")
