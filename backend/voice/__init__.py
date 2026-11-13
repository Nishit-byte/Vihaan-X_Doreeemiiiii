"""VivaVoce Voice Pipeline package.

Re-exports core speech-to-text, text-to-speech, and audio utility functions,
along with the standalone FastAPI voice_router for M1 integration.
"""

from __future__ import annotations

import base64
import binascii
import time
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .audio_utils import (
    FILLER_TEXTS,
    detect_audio_format,
    get_all_fillers,
    get_filler_audio,
    is_probably_silent_or_too_short,
    normalize_audio,
    trim_silence,
    warm_filler_cache,
)
from .config import GROQ_API_KEY
from .stt_service import (
    build_domain_prompt,
    transcribe_audio,
    transcribe_audio_sync,
)
from .tts_service import (
    build_spoken_text,
    synthesize_speech,
    synthesize_speech_sync,
    to_speakable,
)

# APIRouter for voice endpoints (JSON only — no multipart dependency)
voice_router = APIRouter()


class TranscribeRequest(BaseModel):
    """Local schema for audio transcription request."""

    audio_base64: str = Field(..., description="Base64 encoded audio payload")
    mime_type: Optional[str] = Field(default=None, description="Optional MIME type, e.g. audio/webm")
    lang: Optional[str] = Field(default="en", description="Spoken language code")
    domain_terms: Optional[List[str]] = Field(default=None, description="Technical vocabulary terms")


class SpeakRequest(BaseModel):
    """Local schema for speech synthesis request."""

    text: str = Field(..., description="Text to synthesize to speech")


@voice_router.get("/health")
async def voice_health() -> dict[str, Any]:
    """Report readiness of voice components (STT, TTS, Fillers)."""
    return {
        "stt_ready": bool(GROQ_API_KEY and GROQ_API_KEY.strip()),
        "tts_provider": "edge-tts",
        "fillers": len(get_all_fillers()),
    }


@voice_router.get("/fillers")
async def list_fillers() -> list[dict[str, Any]]:
    """Return all cached filler audio clips with metadata and base64 strings."""
    return get_all_fillers()


@voice_router.post("/transcribe")
async def transcribe_endpoint(req: TranscribeRequest) -> dict[str, Any]:
    """Transcribe base64 encoded audio using Groq Whisper."""
    raw_b64 = req.audio_base64.strip() if req.audio_base64 else ""
    if not raw_b64:
        return {"text": "", "ms": 0}

    if "," in raw_b64 and "base64" in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]

    try:
        audio_bytes = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid base64 audio data: {exc}",
        )

    t0 = time.perf_counter()
    transcript = await transcribe_audio(
        audio_bytes=audio_bytes,
        lang=req.lang,
        domain_terms=req.domain_terms,
        mime_type=req.mime_type,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return {"text": transcript, "ms": elapsed_ms}


@voice_router.post("/speak")
async def speak_endpoint(req: SpeakRequest) -> dict[str, Any]:
    """Synthesize speech from text using Edge-TTS (with fallback)."""
    t0 = time.perf_counter()
    audio_b64 = await synthesize_speech(req.text)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return {"audio_base64": audio_b64, "ms": elapsed_ms}


__all__ = [
    "synthesize_speech",
    "synthesize_speech_sync",
    "to_speakable",
    "build_spoken_text",
    "transcribe_audio",
    "transcribe_audio_sync",
    "build_domain_prompt",
    "get_filler_audio",
    "get_all_fillers",
    "warm_filler_cache",
    "voice_router",
]
