"""M3 Voice Pipeline configuration and environment loader."""

import logging
import os
from pathlib import Path

# Best-effort dotenv load of backend/.env, wrapped in try/except so it never crashes
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
try:
    from dotenv import load_dotenv

    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH)
except Exception:
    pass

# Groq STT
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_STT_MODEL: str = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
try:
    STT_TIMEOUT_S: float = float(os.getenv("STT_TIMEOUT_S", "10"))
except ValueError:
    STT_TIMEOUT_S = 10.0

# Edge-TTS
TTS_VOICE: str = os.getenv("TTS_VOICE", "en-US-AndrewNeural")
TTS_RATE: str = os.getenv("TTS_RATE", "+0%")
try:
    TTS_TIMEOUT_S: float = float(os.getenv("TTS_TIMEOUT_S", "8"))
except ValueError:
    TTS_TIMEOUT_S = 8.0

# ElevenLabs (optional fallback)
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")

# Filler audio cache directory
FILLER_CACHE_DIR: Path = Path(os.getenv("FILLER_CACHE_DIR", str(Path(__file__).resolve().parent / "filler_cache")))

# Logger
log = logging.getLogger("vivavoce.voice")

# Hardening for Windows asyncio proactor pipe transport teardown
# Prevents noisy "RuntimeError: Event loop is closed" on unclosed transport __del__
if os.name == "nt":
    try:
        from asyncio.proactor_events import _ProactorBasePipeTransport

        _orig_del = _ProactorBasePipeTransport.__del__

        def _silenced_del(self, *args, **kwargs):
            try:
                _orig_del(self, *args, **kwargs)
            except RuntimeError:
                pass

        _ProactorBasePipeTransport.__del__ = _silenced_del
    except Exception:
        pass


