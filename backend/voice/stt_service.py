"""STT service stub for M3 Voice Pipeline."""

from typing import Optional, List


async def transcribe_audio(
    audio_bytes: bytes,
    lang: str | None = "en",
    domain_terms: list[str] | None = None,
    mime_type: str | None = None,
) -> str:
    """Transcribe audio bytes to text using Groq Whisper."""
    return ""


def build_domain_prompt(domain_terms: list[str] | None = None) -> str:
    """Build a Hinglish and technical domain prompt for Whisper transcription."""
    return ""


def transcribe_audio_sync(
    audio_bytes: bytes,
    lang: str | None = "en",
    domain_terms: list[str] | None = None,
    mime_type: str | None = None,
) -> str:
    """Synchronous wrapper for transcribe_audio for use in scripts."""
    return ""

