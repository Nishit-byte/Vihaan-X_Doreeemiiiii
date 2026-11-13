"""TTS service stub for M3 Voice Pipeline."""

from typing import Optional


async def synthesize_speech(text: str) -> str:
    """Synthesize speech from text returning base64 MP3, or empty string on failure."""
    return ""


def synthesize_speech_sync(text: str) -> str:
    """Synchronous wrapper for synthesize_speech for use in scripts."""
    return ""


def to_speakable(text: str) -> str:
    """Format and sanitize technical text for spoken audio output."""
    return ""


def build_spoken_text(ack_text: str, question_text: str) -> str:
    """Combine acknowledgment and question text with clean punctuation for speech."""
    return ""

