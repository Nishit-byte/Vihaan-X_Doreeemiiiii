"""Audio utilities for M3 Voice Pipeline.

Provides format detection via magic bytes, silence checking, WAV PCM16 silence trimming,
audio normalization, and pre-cached examiner filler audio playback.
Implements M3 interface per CONTEXT §5.3.
"""

import array
import base64
import io
import json
import math
import random
import sys
import wave
from typing import Any, Optional

try:
    from . import config, tts_service
    from .config import FILLER_CACHE_DIR, log
except ImportError:
    try:
        from voice import config, tts_service
        from voice.config import FILLER_CACHE_DIR, log
    except ImportError:
        from backend.voice import config, tts_service
        from backend.voice.config import FILLER_CACHE_DIR, log

FILLER_TEXTS: list[str] = [
    "Let me check that line...",
    "Interesting, checking your implementation...",
    "Hmm, give me a second to think about that.",
]

# In-memory filler cache: lazy-loaded on first read
_cached_fillers: Optional[list[dict]] = None


def detect_audio_format(audio_bytes: bytes) -> str:
    """Detect audio format from magic bytes.

    Returns one of: 'webm', 'wav', 'ogg', 'mp4', 'mp3', or 'unknown'.
    """
    if not audio_bytes or not isinstance(audio_bytes, (bytes, bytearray, memoryview)):
        return "unknown"

    raw = bytes(audio_bytes)
    length = len(raw)

    if length < 2:
        return "unknown"

    # MP3: raw frame sync header (0xFF followed by 0xFB, 0xF3, or 0xF2)
    if raw[0] == 0xFF and raw[1] in (0xFB, 0xF3, 0xF2):
        return "mp3"

    # MP3: ID3v2 container header ("ID3")
    if length >= 3 and raw[:3] == b"ID3":
        return "mp3"

    # WebM / Matroska EBML header: 1A 45 DF A3
    if length >= 4 and raw[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"

    # Ogg container header: "OggS"
    if length >= 4 and raw[:4] == b"OggS":
        return "ogg"

    # MP4 / M4A: "ftyp" box at offset 4
    if length >= 8 and raw[4:8] == b"ftyp":
        return "mp4"

    # WAV: "RIFF" at offset 0 and "WAVE" at offset 8
    if length >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return "wav"

    return "unknown"


def is_probably_silent_or_too_short(audio_bytes: bytes, fmt: str | None = None) -> bool:
    """Check if audio bytes represent silence or are too short to contain speech.

    - Empty or < 2 KB -> True
    - WAV: duration < 0.3 s or RMS energy below -40.0 dBFS -> True
    - Non-PCM16 or non-WAV input >= 2 KB -> False
    NEVER raises.
    """
    if not audio_bytes or not isinstance(audio_bytes, (bytes, bytearray, memoryview)):
        return True

    raw = bytes(audio_bytes)
    if len(raw) < 2048:
        return True

    if fmt:
        f = fmt.lower()
        if "wav" in f:
            detected_fmt = "wav"
        elif "webm" in f:
            detected_fmt = "webm"
        elif "ogg" in f or "opus" in f:
            detected_fmt = "ogg"
        elif "mp4" in f or "m4a" in f:
            detected_fmt = "mp4"
        elif "mp3" in f or "mpeg" in f:
            detected_fmt = "mp3"
        else:
            detected_fmt = detect_audio_format(raw)
    else:
        detected_fmt = detect_audio_format(raw)

    if detected_fmt == "wav":
        try:
            with wave.open(io.BytesIO(raw), "rb") as wf:
                framerate = wf.getframerate()
                nframes = wf.getnframes()
                sampwidth = wf.getsampwidth()
                comptype = wf.getcomptype()

                if framerate <= 0 or nframes <= 0:
                    return True

                duration = nframes / float(framerate)
                if duration < 0.3:
                    return True

                # PCM16 calculation
                if sampwidth == 2 and comptype == "NONE":
                    frame_bytes = wf.readframes(nframes)
                    samples = array.array("h")
                    samples.frombytes(frame_bytes)
                    if sys.byteorder == "big":
                        samples.byteswap()

                    if not samples:
                        return True

                    sum_sq = sum(s * s for s in samples)
                    mean_sq = sum_sq / len(samples)
                    rms = math.sqrt(mean_sq)

                    if rms <= 0.0:
                        return True

                    rms_db = 20.0 * math.log10(rms / 32768.0)
                    if rms_db < -40.0:
                        return True

                    return False
                else:
                    # Non-PCM16 WAV: duration >= 0.3s and size >= 2KB
                    return False
        except Exception:
            # Corrupted or unreadable WAV
            return True

    # Other formats (WebM, MP3, Ogg, MP4) with size >= 2048 bytes
    return False


def trim_silence(wav_bytes: bytes, threshold_db: float = -40.0, pad_ms: int = 150) -> bytes:
    """Trim leading and trailing silence from PCM16 WAV audio using stdlib wave and array.

    Non-PCM16 or non-WAV input is returned unchanged. NEVER raises.
    """
    if not wav_bytes or not isinstance(wav_bytes, (bytes, bytearray, memoryview)):
        return wav_bytes

    raw = bytes(wav_bytes)
    if detect_audio_format(raw) != "wav":
        return wav_bytes

    try:
        with wave.open(io.BytesIO(raw), "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            comptype = wf.getcomptype()

            # Only PCM16 is supported for trimming
            if sampwidth != 2 or comptype != "NONE" or nframes == 0 or framerate <= 0:
                return wav_bytes

            raw_frames = wf.readframes(nframes)

        samples = array.array("h")
        samples.frombytes(raw_frames)
        if sys.byteorder == "big":
            samples.byteswap()

        # Window size: 10 ms chunks
        chunk_frames = max(1, int(framerate * 0.010))
        threshold_linear = 32768.0 * (10.0 ** (threshold_db / 20.0))
        num_chunks = (nframes + chunk_frames - 1) // chunk_frames

        # Find first active chunk
        start_chunk = None
        for c in range(num_chunks):
            f_start = c * chunk_frames
            f_end = min(nframes, f_start + chunk_frames)
            c_samples = samples[f_start * nchannels : f_end * nchannels]
            if not c_samples:
                continue
            mean_sq = sum(s * s for s in c_samples) / len(c_samples)
            if math.sqrt(mean_sq) >= threshold_linear:
                start_chunk = c
                break

        # If audio is completely silent, return original unchanged
        if start_chunk is None:
            return wav_bytes

        # Find last active chunk
        end_chunk = start_chunk
        for c in range(num_chunks - 1, start_chunk - 1, -1):
            f_start = c * chunk_frames
            f_end = min(nframes, f_start + chunk_frames)
            c_samples = samples[f_start * nchannels : f_end * nchannels]
            if not c_samples:
                continue
            mean_sq = sum(s * s for s in c_samples) / len(c_samples)
            if math.sqrt(mean_sq) >= threshold_linear:
                end_chunk = c
                break

        pad_frames = max(0, int(framerate * (pad_ms / 1000.0)))
        trim_start_frame = max(0, start_chunk * chunk_frames - pad_frames)
        trim_end_frame = min(nframes, (end_chunk + 1) * chunk_frames + pad_frames)

        # If nothing was trimmed, return unchanged
        if trim_start_frame == 0 and trim_end_frame == nframes:
            return wav_bytes

        trimmed_samples = samples[trim_start_frame * nchannels : trim_end_frame * nchannels]
        if sys.byteorder == "big":
            trimmed_samples.byteswap()

        out_buf = io.BytesIO()
        with wave.open(out_buf, "wb") as out_wf:
            out_wf.setnchannels(nchannels)
            out_wf.setsampwidth(sampwidth)
            out_wf.setframerate(framerate)
            out_wf.writeframes(trimmed_samples.tobytes())

        return out_buf.getvalue()
    except Exception as exc:
        log.warning("trim_silence failed, returning original audio: %s", exc)
        return wav_bytes


def normalize_audio(audio_bytes: bytes, mime_type: str | None = None) -> tuple[bytes, str]:
    """Normalize audio bytes and determine appropriate filename for processing.

    Returns (bytes, filename) e.g. (b"...", "answer.webm").
    Trims silence for PCM16 WAV audio.
    """
    if not isinstance(audio_bytes, (bytes, bytearray, memoryview)):
        audio_bytes = b""
    else:
        audio_bytes = bytes(audio_bytes)

    fmt = detect_audio_format(audio_bytes)
    if fmt == "unknown" and mime_type:
        mt = mime_type.lower()
        if "webm" in mt:
            fmt = "webm"
        elif "wav" in mt:
            fmt = "wav"
        elif "ogg" in mt or "opus" in mt:
            fmt = "ogg"
        elif "mp4" in mt or "m4a" in mt:
            fmt = "mp4"
        elif "mp3" in mt or "mpeg" in mt:
            fmt = "mp3"

    if fmt == "unknown":
        fmt = "wav"

    if fmt == "wav" and audio_bytes:
        audio_bytes = trim_silence(audio_bytes)

    filename = f"answer.{fmt}"
    return (audio_bytes, filename)


def _load_fillers_from_disk() -> list[dict]:
    """Load cached filler audio clips from FILLER_CACHE_DIR into memory."""
    fillers: list[dict] = []
    fillers_json_path = FILLER_CACHE_DIR / "fillers.json"

    entries: list[dict[str, str]] = []
    if fillers_json_path.exists():
        try:
            with open(fillers_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    entries = data
        except Exception as exc:
            log.warning("Could not read fillers.json: %s", exc)

    if not entries:
        entries = [
            {"id": f"filler_{i}", "text": text, "file": f"filler_{i}.mp3"}
            for i, text in enumerate(FILLER_TEXTS, start=1)
        ]

    for entry in entries:
        item_id = entry.get("id", "")
        text = entry.get("text", "")
        filename = entry.get("file", f"{item_id}.mp3")
        mp3_path = FILLER_CACHE_DIR / filename

        if mp3_path.exists() and mp3_path.stat().st_size > 0:
            try:
                raw_bytes = mp3_path.read_bytes()
                b64 = base64.b64encode(raw_bytes).decode("ascii")
                fillers.append({
                    "id": item_id,
                    "text": text,
                    "audio_base64": b64,
                })
            except Exception as exc:
                log.warning("Could not read filler clip %s: %s", mp3_path, exc)

    return fillers


def get_all_fillers() -> list[dict]:
    """Return all cached filler audio clips with metadata and base64 strings."""
    global _cached_fillers
    if _cached_fillers is None:
        _cached_fillers = _load_fillers_from_disk()
    return list(_cached_fillers)


def get_filler_audio() -> str:
    """Return a random pre-cached filler audio as base64 string, or empty string."""
    fillers = get_all_fillers()
    if not fillers:
        return ""
    chosen = random.choice(fillers)
    return chosen.get("audio_base64", "")


async def warm_filler_cache() -> None:
    """Pre-generate and cache filler audio MP3 files via synthesize_speech.

    Creates filler_cache/filler_1.mp3..filler_3.mp3 + fillers.json.
    Skips existing files; NEVER raises.
    """
    global _cached_fillers
    try:
        FILLER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fillers_json_path = FILLER_CACHE_DIR / "fillers.json"

        manifest: list[dict[str, str]] = []
        any_generated = False

        for i, text in enumerate(FILLER_TEXTS, start=1):
            item_id = f"filler_{i}"
            filename = f"filler_{i}.mp3"
            mp3_path = FILLER_CACHE_DIR / filename
            manifest.append({"id": item_id, "text": text, "file": filename})

            if mp3_path.exists() and mp3_path.stat().st_size > 0:
                log.debug("Filler clip already exists, skipping: %s", mp3_path)
                continue

            log.info("Warming filler clip %d: %r", i, text)
            try:
                b64 = await tts_service.synthesize_speech(text)
                if b64:
                    raw_mp3 = base64.b64decode(b64)
                    mp3_path.write_bytes(raw_mp3)
                    any_generated = True
                    log.info("Wrote filler clip %s (%d bytes)", mp3_path, len(raw_mp3))
                else:
                    log.warning("synthesize_speech returned empty for filler %d", i)
            except Exception as exc:
                log.warning("Failed synthesizing filler %d: %s", i, exc)

        if not fillers_json_path.exists() or any_generated:
            try:
                with open(fillers_json_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2)
            except Exception as exc:
                log.warning("Failed writing fillers.json: %s", exc)

        # Refresh in-memory cache
        _cached_fillers = _load_fillers_from_disk()
    except Exception as exc:
        log.warning("Unexpected error warming filler cache: %s", exc)
