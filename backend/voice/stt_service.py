"""Groq Whisper STT service for M3 Voice Pipeline.

Provides low-latency speech transcription using Groq's whisper-large-v3-turbo model,
domain vocabulary conditioning for code-switching and technical identifiers,
pre-flight audio checks to prevent unnecessary API calls, and Whisper hallucination filtering.
"""

import asyncio
import inspect
import re
import sys
import time
from typing import Any

import groq
import httpx

from . import config
from .audio_utils import is_probably_silent_or_too_short, normalize_audio

# Known Whisper hallucinations on silent or low-volume background noise
WHISPER_SILENCE_PHRASES: set[str] = {
    "",
    "thank you for watching",
    "thanks for watching",
    "thank you for watching this video",
    "thanks for watching this video",
    "thank you",
    "thanks",
    "thank you very much",
    "thank you so much",
    "you",
    "subtitles by",
    "subtitles by the amara org community",
    "subtitles by the amara.org community",
    "subtitles by amara org",
    "subtitles",
    "translated by",
    "please subscribe",
    "like and subscribe",
    "subscribe",
    "see you next time",
    "see you in the next video",
    "see you soon",
    "see you",
    "bye",
    "goodbye",
    "the end",
    "watching",
    "so",
    "silence",
    "music",
}

# Module-level state for client caching and single-warning tracking
_client: groq.AsyncGroq | None = None
_client_key: str | None = None
_warned_missing_key: bool = False


def _get_api_key() -> str:
    """Retrieve Groq API key from config or environment."""
    return getattr(config, "GROQ_API_KEY", "") or ""


def _get_groq_client(api_key: str) -> groq.AsyncGroq:
    """Get or create cached AsyncGroq client for the given API key and event loop."""
    global _client, _client_key
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    client_loop = getattr(_client, "_bound_loop", None) if _client else None
    if _client is None or _client_key != api_key or (current_loop is not None and client_loop != current_loop):
        _client = groq.AsyncGroq(api_key=api_key)
        _client_key = api_key
        if current_loop is not None:
            setattr(_client, "_bound_loop", current_loop)
    return _client


def _sanitize_log_message(msg: str, key: str) -> str:
    """Ensure the API key is never exposed in log outputs."""
    if key and key in msg:
        msg = msg.replace(key, "[REDACTED]")
    return msg


def _clean_for_filter(text: str) -> str:
    """Normalize transcript text for hallucination matching: lowercase, strip punctuation and whitespace."""
    if not text:
        return ""
    # Strip all non-alphanumeric and non-whitespace characters
    t = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(t.split())


def _filter_hallucinations(transcript: str) -> str:
    """Filter known Whisper silence hallucinations if the WHOLE transcript matches.

    Returns empty string if the whole transcript is a silence artifact.
    Does NOT filter words inside longer, valid student answers.
    """
    if not transcript:
        return ""

    cleaned = _clean_for_filter(transcript)
    if not cleaned:
        return ""

    if cleaned in WHISPER_SILENCE_PHRASES:
        return ""

    # Common subtitle trailer hallucinations like 'subtitles by ...' or 'translated by ...'
    words = cleaned.split()
    if cleaned.startswith("subtitles by") and len(words) <= 8:
        return ""
    if cleaned.startswith("translated by") and len(words) <= 8:
        return ""

    return transcript.strip()


def build_domain_prompt(domain_terms: list[str] | None = None) -> str:
    """Build a Hinglish-friendly style sentence + technical domain prompt for Whisper.

    Includes code-switching cues and up to 40 domain identifiers, keeping
    the total prompt length under ~600 characters (Whisper prompt window limit).
    """
    base_prompt = (
        "Technical viva. The student may mix Hindi and English, like "
        "'haan, toh basically yeh function cosine similarity return karta hai'."
    )
    if not domain_terms:
        return base_prompt

    if isinstance(domain_terms, str):
        raw_list = [t.strip() for t in domain_terms.split(",") if t.strip()]
    elif isinstance(domain_terms, (list, tuple, set)):
        raw_list = [str(t).strip() for t in domain_terms if t and str(t).strip()]
    else:
        return base_prompt

    # Extract up to 40 unique identifiers preserving order
    clean_terms: list[str] = []
    seen: set[str] = set()
    for item in raw_list:
        if item not in seen:
            seen.add(item)
            clean_terms.append(item)
            if len(clean_terms) >= 40:
                break

    if not clean_terms:
        return base_prompt

    prompt = base_prompt + " Terms: "
    added = 0
    for term in clean_terms:
        sep = ", " if added > 0 else ""
        candidate = f"{sep}{term}"
        # Keep comfortably under 600 characters limit
        if len(prompt) + len(candidate) + 1 > 590:
            break
        prompt += candidate
        added += 1

    if added > 0 and not prompt.endswith("."):
        prompt += "."

    return prompt


async def transcribe_audio(
    audio_bytes: bytes,
    lang: str | None = "en",
    domain_terms: list[str] | None = None,
    mime_type: str | None = None,
) -> str:
    """Transcribe audio bytes to text using Groq Whisper.

    Features:
    - Pre-checks with audio_utils: empty / silent / too short returns "" with zero API calls.
    - normalize_audio provides format detection, silence trimming, and proper file extension.
    - Domain conditioning via build_domain_prompt(domain_terms).
    - Timeout protection via STT_TIMEOUT_S with one retry on timeout or 5xx server errors.
    - Missing GROQ_API_KEY logs a warning once and returns "".
    - NEVER raises exceptions under any failure mode; never logs API keys.
    - Hallucination filter removes known Whisper silence artifacts when they form the entire transcript.
    """
    global _warned_missing_key

    # 1. Pre-flight checks: empty / silent / too short -> return "" without calling API
    if not audio_bytes or not isinstance(audio_bytes, (bytes, bytearray, memoryview)):
        return ""

    raw_bytes = bytes(audio_bytes)
    if is_probably_silent_or_too_short(raw_bytes, fmt=mime_type):
        return ""

    norm_bytes, filename = normalize_audio(raw_bytes, mime_type=mime_type)
    if not norm_bytes or len(norm_bytes) < 32:
        return ""

    # Re-check normalized/trimmed audio
    ext = filename.split(".")[-1] if "." in filename else None
    if is_probably_silent_or_too_short(norm_bytes, fmt=ext):
        return ""

    # 2. Check Groq API key: missing -> warn once, return "" without raising
    api_key = _get_api_key()
    if not api_key:
        if not _warned_missing_key:
            config.log.warning("GROQ_API_KEY is not set. STT transcription is disabled and will return empty string.")
            _warned_missing_key = True
        return ""

    # 3. Prepare request parameters
    model = getattr(config, "GROQ_STT_MODEL", "whisper-large-v3-turbo")
    timeout_s = getattr(config, "STT_TIMEOUT_S", 10.0)
    prompt = build_domain_prompt(domain_terms)

    req_kwargs: dict[str, Any] = {
        "file": (filename, norm_bytes),
        "model": model,
        "prompt": prompt,
        "temperature": 0.0,
        "response_format": "json",
    }
    if lang is not None:
        req_kwargs["language"] = lang

    client = _get_groq_client(api_key)

    # 4. Execute with timeout and retry once on timeout or 5xx server error
    raw_transcript = ""
    for attempt in (1, 2):
        t0 = time.perf_counter()
        try:
            coro = client.audio.transcriptions.create(**req_kwargs)
            resp = await asyncio.wait_for(coro, timeout=timeout_s)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            if hasattr(resp, "text"):
                raw_transcript = str(resp.text or "")
            elif isinstance(resp, dict):
                raw_transcript = str(resp.get("text", "") or "")
            else:
                raw_transcript = str(resp or "")

            break

        except (asyncio.TimeoutError, groq.APITimeoutError):
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            if attempt == 1:
                config.log.warning(
                    "STT Groq timeout on attempt 1 after %.1fms (limit=%.1fs), retrying once...",
                    elapsed_ms,
                    timeout_s,
                )
                continue
            else:
                config.log.warning(
                    "STT Groq timeout on attempt 2 after %.1fms (limit=%.1fs). Aborting.",
                    elapsed_ms,
                    timeout_s,
                )
                return ""

        except (groq.APIStatusError, httpx.HTTPStatusError) as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            status_code = getattr(exc, "status_code", None)
            sanitized_msg = _sanitize_log_message(str(exc), api_key)

            if status_code and status_code >= 500:
                if attempt == 1:
                    config.log.warning(
                        "STT Groq 5xx server error (%s) on attempt 1 after %.1fms: %s. Retrying once...",
                        status_code,
                        elapsed_ms,
                        sanitized_msg,
                    )
                    continue
                else:
                    config.log.warning(
                        "STT Groq 5xx server error (%s) on attempt 2 after %.1fms: %s. Aborting.",
                        status_code,
                        elapsed_ms,
                        sanitized_msg,
                    )
                    return ""
            else:
                # 4xx error (e.g. 401 Unauthorized, 400 Bad Request) - do not retry
                config.log.warning(
                    "STT Groq API client error (%s) after %.1fms: %s",
                    status_code,
                    elapsed_ms,
                    sanitized_msg,
                )
                return ""

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            sanitized_msg = _sanitize_log_message(str(exc), api_key)
            config.log.error(
                "STT Groq unexpected error after %.1fms: %s",
                elapsed_ms,
                sanitized_msg,
            )
            return ""

    # 5. Post-process: strip and filter Whisper silence hallucinations
    final_text = _filter_hallucinations(raw_transcript)

    if final_text:
        config.log.info(
            "STT success model=%s latency=%.1fms chars=%d",
            model,
            elapsed_ms,
            len(final_text),
        )
    else:
        if raw_transcript.strip():
            config.log.info(
                "STT dropped hallucination: %.60r",
                raw_transcript.strip(),
            )

    return final_text


def transcribe_audio_sync(
    audio_bytes: bytes,
    lang: str | None = "en",
    domain_terms: list[str] | None = None,
    mime_type: str | None = None,
) -> str:
    """Synchronous wrapper for transcribe_audio for use in scripts only. NEVER raises."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                timeout_val = getattr(config, "STT_TIMEOUT_S", 10.0) * 2 + 4
                return pool.submit(
                    asyncio.run,
                    transcribe_audio(
                        audio_bytes=audio_bytes,
                        lang=lang,
                        domain_terms=domain_terms,
                        mime_type=mime_type,
                    ),
                ).result(timeout=timeout_val)
        else:
            return asyncio.run(
                transcribe_audio(
                    audio_bytes=audio_bytes,
                    lang=lang,
                    domain_terms=domain_terms,
                    mime_type=mime_type,
                )
            )
    except Exception as exc:
        config.log.warning("STT transcribe_audio_sync failed: %s", exc)
        return ""
