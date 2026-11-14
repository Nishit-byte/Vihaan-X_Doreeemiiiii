"""Text-to-Speech (TTS) service with Edge-TTS, ElevenLabs fallback, and caching.

Implements M3 voice synthesis interface per CONTEXT §5.2.
"""

import asyncio
import base64
import collections
import re
import time
from typing import Optional

import edge_tts
import httpx

try:
    from . import config
except ImportError:
    try:
        from voice import config
    except ImportError:
        from backend.voice import config

# In-memory LRU cache: (voice, rate, speakable_text) -> base64_mp3
_CACHE_MAX_ENTRIES = 128
_tts_cache: collections.OrderedDict[tuple[str, str, str], str] = collections.OrderedDict()


def _get_from_cache(key: tuple[str, str, str]) -> Optional[str]:
    """Retrieve item from LRU cache, updating its access order."""
    if key in _tts_cache:
        _tts_cache.move_to_end(key)
        return _tts_cache[key]
    return None


def _put_to_cache(key: tuple[str, str, str], value: str) -> None:
    """Insert item into LRU cache, evicting the oldest entry if full."""
    if key in _tts_cache:
        _tts_cache.move_to_end(key)
    else:
        if len(_tts_cache) >= _CACHE_MAX_ENTRIES:
            _tts_cache.popitem(last=False)
    _tts_cache[key] = value


def _clear_cache() -> None:
    """Clear the in-memory TTS cache (primarily for tests)."""
    _tts_cache.clear()


def _get_cache_size() -> int:
    """Return the current number of cached items."""
    return len(_tts_cache)


def to_speakable(text: str) -> str:
    """Format and sanitize technical text for spoken audio output.

    Removes code formatting, markdown markup, converts line ranges to
    natural speech, strips empty parentheses after identifiers, converts
    snake_case to spaces, collapses whitespace, and caps length at ~600 chars.
    """
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 1. Strip markdown backticks
    text = text.replace("`", "")

    # 2. Strip empty parentheses after identifiers (e.g. compute_cosine_similarity() -> compute_cosine_similarity)
    text = re.sub(r"(\b[A-Za-z0-9_]+)\s*\(\s*\)", r"\1", text)

    # 3. Line range normalization: 'L12-L20', 'lines 12-20', 'line 12-20' -> 'lines 12 to 20'
    # Must NOT mangle single Bloom level indicators (e.g. 'L4 Evaluation') or version numbers ('Python 3.11')
    text = re.sub(
        r"\b(?:lines?|L)\s*(\d+)\s*[-–—]\s*(?:lines?|L)?\s*(\d+)\b",
        r"lines \1 to \2",
        text,
        flags=re.IGNORECASE,
    )

    # 4. Strip markdown links [link text](url) -> link text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # 5. Snake_case underscores -> spaces (guarantees no underscores in output)
    text = text.replace("_", " ")

    # 6. "C#" -> "C sharp" before stripping markdown chars
    text = re.sub(r"(?<=[A-Za-z])#", " sharp", text)

    # 6b. Strip other markdown formatting: *, #, >, ~
    for char in ("*", "#", ">", "~"):
        text = text.replace(char, " ")

    # 7. Collapse whitespace and strip leading/trailing spaces
    text = re.sub(r"\s+", " ", text).strip()

    # 8. Cap at ~600 characters cleanly on sentence or word boundary
    if len(text) > 600:
        truncated = text[:600]
        last_punct = max(truncated.rfind("."), truncated.rfind("?"), truncated.rfind("!"))
        if last_punct > 400:
            text = truncated[: last_punct + 1]
        else:
            last_space = truncated.rfind(" ")
            if last_space > 400:
                text = truncated[:last_space]
            else:
                text = truncated

    return text


def build_spoken_text(ack_text: str, question_text: str) -> str:
    """Combine acknowledgment and question text with clean punctuation for speech without duplication."""
    ack = (ack_text or "").strip()
    question = (question_text or "").strip()

    if not ack and not question:
        return ""
    if not ack:
        return to_speakable(question)
    if not question:
        return to_speakable(ack)

    # Deduplicate if question is already inside ack or ack is inside question
    norm_ack = re.sub(r"[.!?]+$", "", ack).strip()
    norm_q = re.sub(r"[.!?]+$", "", question).strip()
    if norm_q and norm_q.lower() in norm_ack.lower():
        return to_speakable(ack)
    if norm_ack and norm_ack.lower() in norm_q.lower():
        return to_speakable(question)

    # Ensure clean punctuation between acknowledgment and question
    if not ack.endswith((".", "!", "?", ";", ":")):
        ack = ack + "."

    combined = f"{ack} {question}"
    return to_speakable(combined)


# Backward-compatible and canonical helper alias for INT-2
_build_spoken_text = build_spoken_text


async def _synthesize_edge_tts(text: str, voice: str, rate: str) -> bytes:
    """Synthesize speech using Microsoft Edge TTS via websocket stream with retry."""
    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            audio_chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio_chunks.append(chunk["data"])
            audio_bytes = b"".join(audio_chunks)
            if audio_bytes:
                return audio_bytes
            raise RuntimeError("edge-tts produced 0 audio bytes")
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(0.3 * (attempt + 1))
    raise last_exc or RuntimeError("edge-tts failed after retries")


async def _synthesize_elevenlabs(text: str, voice_id: str, api_key: str) -> bytes:
    """Synthesize speech using ElevenLabs HTTP API as fallback."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_flash_v2_5",
    }
    async with httpx.AsyncClient(timeout=config.TTS_TIMEOUT_S) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        if not response.content:
            raise RuntimeError("ElevenLabs returned empty audio response")
        return response.content


async def synthesize_speech(text: str) -> str:
    """Synthesize speech from text returning base64 MP3, or empty string on failure.

    Provider chain: edge-tts (TTS_VOICE, TTS_RATE) -> ElevenLabs (only if keys set) -> ""
    In-memory LRU cache keyed by (voice, rate, speakable_text), max 128 entries.
    Each provider wrapped in asyncio.wait_for(TTS_TIMEOUT_S); logs provider + milliseconds.
    Empty text returns "" with no network call. NEVER raises.
    """
    try:
        if not text or not text.strip():
            return ""

        speakable = to_speakable(text)
        if not speakable or not speakable.strip():
            return ""

        voice = config.TTS_VOICE
        rate = config.TTS_RATE
        cache_key = (voice, rate, speakable)

        # 1. Check LRU Cache
        cached_b64 = _get_from_cache(cache_key)
        if cached_b64 is not None:
            config.log.info("TTS cache hit for voice='%s', rate='%s' (0 ms)", voice, rate)
            return cached_b64

        audio_bytes: Optional[bytes] = None

        # 2. Try Edge-TTS
        t0 = time.perf_counter()
        try:
            audio_bytes = await asyncio.wait_for(
                _synthesize_edge_tts(speakable, voice, rate),
                timeout=config.TTS_TIMEOUT_S,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            config.log.info(
                "TTS provider=edge-tts voice='%s' rate='%s' status=success latency=%.1fms bytes=%d",
                voice,
                rate,
                elapsed_ms,
                len(audio_bytes),
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            config.log.warning(
                "TTS provider=edge-tts voice='%s' rate='%s' status=failed latency=%.1fms error=%s",
                voice,
                rate,
                elapsed_ms,
                exc,
            )
            audio_bytes = None

        # 3. Try ElevenLabs fallback (only if credentials configured and edge-tts failed)
        if audio_bytes is None and config.ELEVENLABS_API_KEY and config.ELEVENLABS_VOICE_ID:
            t0 = time.perf_counter()
            try:
                audio_bytes = await asyncio.wait_for(
                    _synthesize_elevenlabs(speakable, config.ELEVENLABS_VOICE_ID, config.ELEVENLABS_API_KEY),
                    timeout=config.TTS_TIMEOUT_S,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                config.log.info(
                    "TTS provider=elevenlabs voice_id='%s' status=success latency=%.1fms bytes=%d",
                    config.ELEVENLABS_VOICE_ID,
                    elapsed_ms,
                    len(audio_bytes),
                )
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                config.log.warning(
                    "TTS provider=elevenlabs voice_id='%s' status=failed latency=%.1fms error=%s",
                    config.ELEVENLABS_VOICE_ID,
                    elapsed_ms,
                    exc,
                )
                audio_bytes = None

        # 4. If all providers failed, log warning and return ""
        if not audio_bytes:
            config.log.warning(
                "TTS all providers failed for text: %.60r",
                speakable,
            )
            return ""

        # 5. Convert to base64, save to LRU cache, and return
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        _put_to_cache(cache_key, audio_b64)
        return audio_b64

    except Exception as exc:
        config.log.error("TTS unexpected error in synthesize_speech: %s", exc)
        return ""


def synthesize_speech_sync(text: str) -> str:
    """Synchronous wrapper for synthesize_speech for use in scripts only. NEVER raises."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, synthesize_speech(text)).result(
                    timeout=config.TTS_TIMEOUT_S * 2 + 2
                )
        else:
            return asyncio.run(synthesize_speech(text))
    except Exception as exc:
        config.log.warning("TTS synthesize_speech_sync failed: %s", exc)
        return ""
