"""VivaVoce Voice Pipeline package."""

from fastapi import APIRouter

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

# APIRouter for voice endpoints (stubbed for A1, fully implemented in A5)
voice_router = APIRouter()

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

