"""VivaVoce Voice Pipeline package.

Re-exports core speech-to-text, text-to-speech, and audio utility functions,
along with the standalone FastAPI voice_router for M1 integration.
"""

from fastapi import APIRouter

from .config import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    FILLER_CACHE_DIR,
    GROQ_API_KEY,
    GROQ_STT_MODEL,
    STT_TIMEOUT_S,
    TTS_RATE,
    TTS_TIMEOUT_S,
    TTS_VOICE,
    log,
)

# APIRouter for voice endpoints (stubbed for scaffold, endpoints mounted in voice router subtask)
voice_router = APIRouter()
