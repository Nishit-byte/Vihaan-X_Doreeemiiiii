"""Audio utilities stub for M3 Voice Pipeline."""

from typing import Optional, Tuple, List, Dict, Any

FILLER_TEXTS: list[str] = [
    "Let me check that line...",
    "Interesting, checking your implementation...",
    "Hmm, give me a second to think about that.",
]


def detect_audio_format(audio_bytes: bytes) -> str:
    """Detect audio format from magic bytes, returning webm, wav, ogg, mp4, mp3, or unknown."""
    return "unknown"


def is_probably_silent_or_too_short(audio_bytes: bytes, fmt: str | None = None) -> bool:
    """Check if audio bytes represent silence or are too short to contain speech."""
    return False


def trim_silence(wav_bytes: bytes, threshold_db: float = -40.0, pad_ms: int = 150) -> bytes:
    """Trim leading and trailing silence from PCM16 WAV audio."""
    return wav_bytes


def normalize_audio(audio_bytes: bytes, mime_type: str | None = None) -> tuple[bytes, str]:
    """Normalize audio bytes and determine appropriate filename for processing."""
    return (audio_bytes, "answer.wav")


async def warm_filler_cache() -> None:
    """Pre-generate and cache filler audio MP3 files."""
    return None


def get_filler_audio() -> str:
    """Return a random pre-cached filler audio as base64 string, or empty string."""
    return ""


def get_all_fillers() -> list[dict]:
    """Return all cached filler audio clips with metadata and base64 strings."""
    return []

