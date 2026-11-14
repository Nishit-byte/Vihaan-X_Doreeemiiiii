"""VivaVoce M3 Voice Pipeline — Comprehensive Self-Test & Hardening Suite.

Executes end-to-end regression, performance, resilience, and API tests
across all M3 voice components (TTS, STT, Audio Utils, voice_router, dev_server).
Prints a PASS/FAIL/SKIP results table and exits with code 1 on any failure.

Usage:
    cd backend
    python -m voice.selftest
"""

from __future__ import annotations

import array
import asyncio
import base64
import concurrent.futures
import gc
import io
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Coroutine, List, Tuple
import warnings
import wave

# Suppress deprecation and transport cleanup warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*testclient.*")

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from voice import (
    FILLER_TEXTS,
    audio_utils,
    build_domain_prompt,
    build_spoken_text,
    config,
    detect_audio_format,
    get_all_fillers,
    get_filler_audio,
    is_probably_silent_or_too_short,
    normalize_audio,
    stt_service,
    synthesize_speech,
    synthesize_speech_sync,
    to_speakable,
    transcribe_audio,
    transcribe_audio_sync,
    trim_silence,
    voice_router,
    warm_filler_cache,
)

try:
    from voice.dev_server import app as dev_server_app
except Exception:
    dev_server_app = None


# ---------------------------------------------------------------------------
# Synthetic Audio Helpers (stdlib only, < 5ms)
# ---------------------------------------------------------------------------

def _make_tone_wav(duration_s: float = 1.0, freq: float = 440.0, framerate: int = 16000) -> bytes:
    """Generate a clean PCM16 mono sine tone WAV in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        n_samples = int(duration_s * framerate)
        samples = [int(16000.0 * math.sin(2.0 * math.pi * freq * i / framerate)) for i in range(n_samples)]
        wf.writeframes(array.array("h", samples).tobytes())
    return buf.getvalue()


def _make_silent_wav(duration_s: float = 1.0, framerate: int = 16000) -> bytes:
    """Generate a PCM16 mono zero-amplitude silent WAV in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(b"\x00\x00" * int(duration_s * framerate))
    return buf.getvalue()


def _make_padded_tone_wav(tone_s: float = 1.0, pad_s: float = 0.5, freq: float = 440.0, framerate: int = 16000) -> bytes:
    """Generate a tone WAV padded with leading and trailing silence."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(b"\x00\x00" * int(pad_s * framerate))
        n_samples = int(tone_s * framerate)
        samples = [int(16000.0 * math.sin(2.0 * math.pi * freq * i / framerate)) for i in range(n_samples)]
        wf.writeframes(array.array("h", samples).tobytes())
        wf.writeframes(b"\x00\x00" * int(pad_s * framerate))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test Definition Data Structure
# ---------------------------------------------------------------------------

class TestResult:
    def __init__(self, index: int, name: str, status: str, details: str, elapsed_ms: float = 0.0):
        self.index = index
        self.name = name
        self.status = status  # 'PASS' | 'FAIL' | 'SKIP'
        self.details = details
        self.elapsed_ms = elapsed_ms


# ---------------------------------------------------------------------------
# Synchronous Test Checks
# ---------------------------------------------------------------------------

def test_to_speakable_cases(idx: int) -> TestResult:
    """Check 1: to_speakable sanitization, line ranges, and markdown stripping."""
    t0 = time.perf_counter()
    test_cases = [
        ("`compute_cosine_similarity()`", "compute cosine similarity"),
        ("L12-L20", "lines 12 to 20"),
        ("lines 12-20", "lines 12 to 20"),
        ("line 12-20", "lines 12 to 20"),
        ("L12 - L20", "lines 12 to 20"),
        ("L4 Evaluation", "L4 Evaluation"),
        ("Python 3.11", "Python 3.11"),
        ("C#", "C sharp"),
        ("F#", "F sharp"),
        ("In lines 12-20, why did you call `compute_cosine_similarity()`?", "In lines 12 to 20, why did you call compute cosine similarity?"),
        ("### Question 1: **Analysis** of `find_matches()`", "Question 1: Analysis of find matches"),
        ("> Look at L1-L5 in utils.py", "Look at lines 1 to 5 in utils.py"),
        ("[click here](https://example.com/api)", "click here"),
        ("~strikethrough~", "strikethrough"),
        ("", ""),
        (None, ""),
    ]

    for raw, expected in test_cases:
        actual = to_speakable(raw)
        if actual != expected:
            return TestResult(
                idx,
                "to_speakable text sanitization",
                "FAIL",
                f"Mismatch for {raw!r}: got {actual!r}, expected {expected!r}",
                (time.perf_counter() - t0) * 1000,
            )
        # Ensure no forbidden markdown characters remain in output
        if any(c in actual for c in ("`", "*", "#", "_")):
            return TestResult(
                idx,
                "to_speakable text sanitization",
                "FAIL",
                f"Forbidden markdown char found in output {actual!r}",
                (time.perf_counter() - t0) * 1000,
            )

    # Test length truncation at ~600 chars
    long_input = "In lines 12 to 20, the compute cosine similarity function calculates the angle. " * 20
    truncated = to_speakable(long_input)
    if len(truncated) > 600:
        return TestResult(
            idx,
            "to_speakable text sanitization",
            "FAIL",
            f"Length truncation failed: length {len(truncated)} exceeds 600 chars",
            (time.perf_counter() - t0) * 1000,
        )

    elapsed = (time.perf_counter() - t0) * 1000
    return TestResult(
        idx,
        "to_speakable text sanitization",
        "PASS",
        f"{len(test_cases) + 1}/{len(test_cases) + 1} cases passed; 0 forbidden markdown chars",
        elapsed,
    )


def test_build_spoken_text_cases(idx: int) -> TestResult:
    """Check 2: build_spoken_text combination and punctuation normalization."""
    t0 = time.perf_counter()
    cases = [
        ("Good point on cosine similarity", "How would you optimize `compute_cosine_similarity()` in lines 12-20?",
         "Good point on cosine similarity. How would you optimize compute cosine similarity in lines 12 to 20?"),
        ("Good point on cosine similarity.", "How would you optimize `compute_cosine_similarity()` in lines 12-20?",
         "Good point on cosine similarity. How would you optimize compute cosine similarity in lines 12 to 20?"),
        ("", "How would you optimize `compute_cosine_similarity()`?",
         "How would you optimize compute cosine similarity?"),
        ("Good point on cosine similarity.", "",
         "Good point on cosine similarity."),
        ("", "", ""),
    ]

    for ack, q, expected in cases:
        actual = build_spoken_text(ack, q)
        if actual != expected:
            return TestResult(
                idx,
                "build_spoken_text combination",
                "FAIL",
                f"Mismatch for ack={ack!r}, q={q!r}: got {actual!r}, expected {expected!r}",
                (time.perf_counter() - t0) * 1000,
            )

    elapsed = (time.perf_counter() - t0) * 1000
    return TestResult(
        idx,
        "build_spoken_text combination",
        "PASS",
        f"{len(cases)}/{len(cases)} punctuation & merge cases verified",
        elapsed,
    )


def test_format_detection_headers(idx: int) -> TestResult:
    """Check 6: detect_audio_format for webm, wav, ogg, mp4, mp3, and unknown."""
    t0 = time.perf_counter()
    cases = [
        (b"\x1a\x45\xdf\xa3\x01\x02\x03\x04", "webm"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00", "wav"),
        (b"OggS\x00\x02\x00\x00\x00\x00\x00\x00", "ogg"),
        (b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00", "mp4"),
        (b"ID3\x04\x00\x00\x00\x00\x00\x20", "mp3"),
        (b"\xff\xfb\x90\x64\x00\x00\x00\x00", "mp3"),
        (b"\xff\xf3\x40\xc4\x00\x00\x00\x00", "mp3"),
        (b"\xff\xf2\x40\xc4\x00\x00\x00\x00", "mp3"),
        (b"UNKNOWN_BINARY_HEADER", "unknown"),
        (b"\x00", "unknown"),
        (b"", "unknown"),
    ]

    for raw, expected in cases:
        actual = detect_audio_format(raw)
        if actual != expected:
            return TestResult(
                idx,
                "Audio format detection",
                "FAIL",
                f"Mismatch for header {raw[:8]!r}: got {actual!r}, expected {expected!r}",
                (time.perf_counter() - t0) * 1000,
            )

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "Audio format detection",
        "PASS",
        f"{len(cases)}/{len(cases)} formats matched (webm, wav, ogg, mp4, mp3, unknown)",
        elapsed,
    )


def test_hallucination_filter(idx: int) -> TestResult:
    """Check 8: Whisper hallucination filter drops silence artifacts while preserving real speech."""
    t0 = time.perf_counter()
    from voice.stt_service import _filter_hallucinations

    silence_cases = [
        "",
        ".",
        "   ...   ",
        "Thank you for watching.",
        "Thanks for watching!",
        "thank you for watching this video",
        "You.",
        "Subtitles by the Amara.org community",
        "Subtitles by Jane Doe",
        "Translated by John Smith",
        "Thank you.",
        "Thanks.",
        "Please subscribe",
        "Like and subscribe",
        "The end",
    ]

    for phrase in silence_cases:
        res = _filter_hallucinations(phrase)
        if res != "":
            return TestResult(
                idx,
                "Whisper hallucination filter",
                "FAIL",
                f"Failed to drop hallucination {phrase!r}, returned {res!r}",
                (time.perf_counter() - t0) * 1000,
            )

    # Valid speech containing trigger words must be preserved
    valid_cases = [
        "Thank you for asking. In lines 12 to 20 we compute cosine similarity.",
        "Haan, basically you should compute cosine similarity for embedding comparison.",
        "So this function handles dot products.",
        "You can see the vector dimension check in lines 15 to 20.",
    ]

    for sentence in valid_cases:
        res = _filter_hallucinations(sentence)
        if res != sentence:
            return TestResult(
                idx,
                "Whisper hallucination filter",
                "FAIL",
                f"Valid speech was incorrectly mutated: {sentence!r} -> {res!r}",
                (time.perf_counter() - t0) * 1000,
            )

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "Whisper hallucination filter",
        "PASS",
        f"{len(silence_cases)} artifacts dropped; {len(valid_cases)} valid answers preserved",
        elapsed,
    )


def test_voice_router_endpoints(idx: int) -> TestResult:
    """Check 11: voice_router endpoints (/health, /fillers, /speak, /transcribe) via TestClient."""
    t0 = time.perf_counter()
    test_app = FastAPI()
    test_app.include_router(voice_router, prefix="/api/voice")
    client = TestClient(test_app)

    # 1. GET /api/voice/health
    r_health = client.get("/api/voice/health")
    if r_health.status_code != 200:
        return TestResult(idx, "voice_router TestClient endpoints", "FAIL", f"GET /health returned status {r_health.status_code}")
    h_data = r_health.json()
    if "stt_ready" not in h_data or "tts_provider" not in h_data or "fillers" not in h_data:
        return TestResult(idx, "voice_router TestClient endpoints", "FAIL", f"GET /health response missing required keys: {h_data}")

    # 2. GET /api/voice/fillers
    r_fillers = client.get("/api/voice/fillers")
    if r_fillers.status_code != 200:
        return TestResult(idx, "voice_router TestClient endpoints", "FAIL", f"GET /fillers returned status {r_fillers.status_code}")
    f_data = r_fillers.json()
    if not isinstance(f_data, list) or len(f_data) != 3:
        return TestResult(idx, "voice_router TestClient endpoints", "FAIL", f"GET /fillers expected 3 clips, got {len(f_data)}")

    # 3. POST /api/voice/speak
    r_speak = client.post("/api/voice/speak", json={"text": "Testing voice router speak endpoint."})
    if r_speak.status_code != 200:
        return TestResult(idx, "voice_router TestClient endpoints", "FAIL", f"POST /speak returned status {r_speak.status_code}")
    sp_data = r_speak.json()
    if not sp_data.get("audio_base64"):
        return TestResult(idx, "voice_router TestClient endpoints", "FAIL", "POST /speak returned empty audio_base64")

    # 4. POST /api/voice/transcribe (empty payload)
    r_trans_empty = client.post("/api/voice/transcribe", json={"audio_base64": ""})
    if r_trans_empty.status_code != 200 or r_trans_empty.json().get("text") != "":
        return TestResult(idx, "voice_router TestClient endpoints", "FAIL", f"POST /transcribe empty audio failed: {r_trans_empty.json()}")

    # 5. POST /api/voice/transcribe (bad base64 -> 400 Bad Request)
    r_trans_bad = client.post("/api/voice/transcribe", json={"audio_base64": "invalid!@#$base64"})
    if r_trans_bad.status_code != 400:
        return TestResult(idx, "voice_router TestClient endpoints", "FAIL", f"POST /transcribe bad base64 expected 400, got {r_trans_bad.status_code}")

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "voice_router TestClient endpoints",
        "PASS",
        f"All 4 endpoints verified: /health (200), /fillers (200), /speak (200), /transcribe (200/400)",
        elapsed,
    )


def test_dev_server_endpoints(idx: int) -> TestResult:
    """Check 12: dev_server endpoints (/api/dev/start, /api/viva/turn) via TestClient."""
    t0 = time.perf_counter()
    if dev_server_app is None:
        return TestResult(idx, "dev_server TestClient endpoints", "FAIL", "dev_server.app could not be imported")

    client = TestClient(dev_server_app)

    # 1. GET /api/dev/start
    r_start = client.get("/api/dev/start")
    if r_start.status_code != 200:
        return TestResult(idx, "dev_server TestClient endpoints", "FAIL", f"GET /api/dev/start returned {r_start.status_code}")

    start_data = r_start.json()
    if start_data.get("verdict") != "start" or start_data.get("depth_level") != 1:
        return TestResult(idx, "dev_server TestClient endpoints", "FAIL", f"GET /api/dev/start invalid shape: {start_data}")
    if not start_data.get("audio_base64"):
        return TestResult(idx, "dev_server TestClient endpoints", "FAIL", "GET /api/dev/start returned empty audio_base64")

    sid = start_data.get("session_id", "test-session")

    # 2. POST /api/viva/turn (text answer)
    turn_payload = {
        "session_id": sid,
        "student_text": "We calculate cosine similarity using the dot product divided by L2 norms.",
    }
    r_turn = client.post("/api/viva/turn", json=turn_payload)
    if r_turn.status_code != 200:
        return TestResult(idx, "dev_server TestClient endpoints", "FAIL", f"POST /api/viva/turn returned {r_turn.status_code}")

    turn_data = r_turn.json()
    if turn_data.get("verdict") != "strong":
        return TestResult(idx, "dev_server TestClient endpoints", "FAIL", f"POST /api/viva/turn expected strong verdict, got {turn_data.get('verdict')}")
    if not turn_data.get("audio_base64"):
        return TestResult(idx, "dev_server TestClient endpoints", "FAIL", "POST /api/viva/turn returned empty audio_base64")

    # 3. POST /api/viva/turn (invalid base64 -> 400 Bad Request)
    r_bad_turn = client.post("/api/viva/turn", json={"session_id": sid, "audio_base64": "invalid_base64!!!"})
    if r_bad_turn.status_code != 400:
        return TestResult(idx, "dev_server TestClient endpoints", "FAIL", f"POST /api/viva/turn bad base64 expected 400, got {r_bad_turn.status_code}")

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "dev_server TestClient endpoints",
        "PASS",
        f"Verified /api/dev/start (start turn) and /api/viva/turn (text + audio + validation)",
        elapsed,
    )


def test_sync_outside_loop(idx: int) -> TestResult:
    """Check 13: Synchronous wrappers called outside any running event loop."""
    t0 = time.perf_counter()

    b64_sync = synthesize_speech_sync("Synchronous wrapper outside event loop test.")
    if not b64_sync or detect_audio_format(base64.b64decode(b64_sync)) != "mp3":
        return TestResult(idx, "Synchronous wrappers (outside loop)", "FAIL", "synthesize_speech_sync failed outside event loop")

    stt_sync_res = transcribe_audio_sync(b"")
    if stt_sync_res != "":
        return TestResult(idx, "Synchronous wrappers (outside loop)", "FAIL", f"transcribe_audio_sync(b'') returned {stt_sync_res!r}")

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "Synchronous wrappers (outside loop)",
        "PASS",
        "synthesize_speech_sync & transcribe_audio_sync work cleanly in standard threads",
        elapsed,
    )


def test_windows_event_loop_sanity(idx: int) -> TestResult:
    """Check 14: Windows event loop sanity — zero 'Event loop is closed' unhandled errors."""
    t0 = time.perf_counter()

    old_stderr = sys.stderr
    captured_err = io.StringIO()
    sys.stderr = captured_err

    try:
        # Rapidly create and tear down multiple event loops
        for i in range(3):
            async def _quick_task(step: int):
                await synthesize_speech(f"Quick loop test {step}")
            asyncio.run(_quick_task(i))

        # Force garbage collection to trigger any lingering transport __del__
        gc.collect()
    finally:
        sys.stderr = old_stderr

    stderr_output = captured_err.getvalue()
    if "Event loop is closed" in stderr_output:
        return TestResult(
            idx,
            "Windows event-loop sanity",
            "FAIL",
            f"Detected 'Event loop is closed' noise in stderr:\n{stderr_output}",
            (time.perf_counter() - t0) * 1000,
        )

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "Windows event-loop sanity",
        "PASS",
        "Multiple event-loop teardowns & GC cycles; zero 'Event loop is closed' warnings",
        elapsed,
    )


# ---------------------------------------------------------------------------
# Asynchronous Test Checks
# ---------------------------------------------------------------------------

async def test_tts_latency(idx: int) -> TestResult:
    """Check 3: TTS cold call vs cached latency, empty bypass, and MP3 header."""
    t0 = time.perf_counter()
    from voice.tts_service import _clear_cache

    _clear_cache()
    prompt = "In lines 12 to 20, what mathematical formula is used to compute cosine similarity?"

    # 1. Cold Call
    tc0 = time.perf_counter()
    b64_cold = await synthesize_speech(prompt)
    cold_ms = (time.perf_counter() - tc0) * 1000.0

    if not b64_cold:
        return TestResult(idx, "TTS cold & cached latency", "FAIL", "Cold synthesis returned empty string", cold_ms)

    audio_bytes = base64.b64decode(b64_cold)
    fmt = detect_audio_format(audio_bytes)
    if fmt != "mp3":
        return TestResult(idx, "TTS cold & cached latency", "FAIL", f"Expected mp3 format, got {fmt!r}", cold_ms)

    # 2. Cached Call
    tc1 = time.perf_counter()
    b64_cached = await synthesize_speech(prompt)
    cached_ms = (time.perf_counter() - tc1) * 1000.0

    if b64_cached != b64_cold:
        return TestResult(idx, "TTS cold & cached latency", "FAIL", "Cached audio payload did not match cold payload", cached_ms)

    # 3. Empty text bypass (0 network calls)
    te0 = time.perf_counter()
    b64_empty = await synthesize_speech("")
    empty_ms = (time.perf_counter() - te0) * 1000.0

    if b64_empty != "":
        return TestResult(idx, "TTS cold & cached latency", "FAIL", f"Empty text returned {b64_empty!r} instead of ''", empty_ms)

    total_ms = (time.perf_counter() - t0) * 1000.0
    details = f"Cold: {cold_ms:.0f}ms, Cached: {cached_ms:.2f}ms ({len(audio_bytes)} bytes MP3), Empty: {empty_ms:.2f}ms"
    return TestResult(idx, "TTS cold & cached latency", "PASS", details, total_ms)


async def test_concurrent_tts(idx: int) -> TestResult:
    """Check 4: 3 concurrent synthesize_speech calls without deadlocks or collisions."""
    t0 = time.perf_counter()
    questions = [
        "First question: Explain how reference counting and garbage collection work in Python.",
        "Second question: What is the algorithmic time complexity of quicksort and mergesort?",
        "Third question: How do ACID transaction isolation levels prevent dirty reads in SQL?",
    ]

    results = await asyncio.gather(*(synthesize_speech(q) for q in questions))
    elapsed = (time.perf_counter() - t0) * 1000.0

    if len(results) != 3:
        return TestResult(idx, "3 concurrent TTS syntheses", "FAIL", f"Expected 3 results, got {len(results)}", elapsed)

    for i, r in enumerate(results, 1):
        if not r:
            return TestResult(idx, "3 concurrent TTS syntheses", "FAIL", f"Concurrent task {i} returned empty string", elapsed)
        raw = base64.b64decode(r)
        if detect_audio_format(raw) != "mp3":
            return TestResult(idx, "3 concurrent TTS syntheses", "FAIL", f"Task {i} output was not valid MP3", elapsed)

    # Ensure different prompts yielded different audio streams
    if len({results[0], results[1], results[2]}) != 3:
        return TestResult(idx, "3 concurrent TTS syntheses", "FAIL", "Distinct inputs produced identical audio outputs", elapsed)

    return TestResult(
        idx,
        "3 concurrent TTS syntheses",
        "PASS",
        f"All 3 finished concurrently in {elapsed:.0f}ms; valid distinct MP3 streams",
        elapsed,
    )


async def test_filler_cache_system(idx: int) -> TestResult:
    """Check 5: Filler cache files on disk, get_all_fillers, and warm_filler_cache."""
    t0 = time.perf_counter()
    from voice.config import FILLER_CACHE_DIR

    # 1. Warm cache (idempotent, skips existing files)
    await warm_filler_cache()

    # 2. Check disk files
    manifest_path = FILLER_CACHE_DIR / "fillers.json"
    if not manifest_path.exists() or manifest_path.stat().st_size == 0:
        return TestResult(idx, "Filler cache & get_all_fillers", "FAIL", f"Manifest {manifest_path} missing or empty")

    for i in range(1, 4):
        mp3_path = FILLER_CACHE_DIR / f"filler_{i}.mp3"
        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            return TestResult(idx, "Filler cache & get_all_fillers", "FAIL", f"Filler clip {mp3_path} missing or empty")

    # 3. Test get_all_fillers
    fillers = get_all_fillers()
    if len(fillers) != 3:
        return TestResult(idx, "Filler cache & get_all_fillers", "FAIL", f"Expected 3 fillers, got {len(fillers)}")

    for item in fillers:
        for k in ("id", "text", "audio_base64"):
            if k not in item or not item[k]:
                return TestResult(idx, "Filler cache & get_all_fillers", "FAIL", f"Filler missing key or empty value: {k}")
        raw = base64.b64decode(item["audio_base64"])
        if detect_audio_format(raw) != "mp3":
            return TestResult(idx, "Filler cache & get_all_fillers", "FAIL", f"Filler {item['id']} has invalid MP3 audio")

    # 4. Test get_filler_audio
    rnd = get_filler_audio()
    if not rnd or len(rnd) < 1000:
        return TestResult(idx, "Filler cache & get_all_fillers", "FAIL", "get_filler_audio returned invalid payload")

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "Filler cache & get_all_fillers",
        "PASS",
        f"3/3 clips present on disk; manifest valid; random filler ready ({len(rnd)} b64 chars)",
        elapsed,
    )


async def test_silence_and_prechecks(idx: int) -> TestResult:
    """Check 7: Silence detection, WAV trimming, and 0-API-call pre-checks."""
    t0 = time.perf_counter()

    # 1. is_probably_silent_or_too_short checks
    if not is_probably_silent_or_too_short(b""):
        return TestResult(idx, "Silence & duration pre-checks", "FAIL", "Empty bytes failed silence check")

    if not is_probably_silent_or_too_short(b"x" * 500):
        return TestResult(idx, "Silence & duration pre-checks", "FAIL", "Payload under 2KB failed short check")

    silent_wav = _make_silent_wav(duration_s=1.0)
    if not is_probably_silent_or_too_short(silent_wav):
        return TestResult(idx, "Silence & duration pre-checks", "FAIL", "Silent WAV failed silence check")

    tone_wav = _make_tone_wav(duration_s=1.0)
    if is_probably_silent_or_too_short(tone_wav):
        return TestResult(idx, "Silence & duration pre-checks", "FAIL", "Active 440Hz tone WAV incorrectly marked as silent")

    # 2. Silence trimming on padded WAV (0.5s silence + 1.0s tone + 0.5s silence = 2.0s)
    padded_wav = _make_padded_tone_wav(tone_s=1.0, pad_s=0.5)
    trimmed_wav = trim_silence(padded_wav, threshold_db=-40.0, pad_ms=150)

    with wave.open(io.BytesIO(trimmed_wav), "rb") as wf:
        dur = wf.getnframes() / float(wf.getframerate())

    # Expected trimmed duration: 1.0s tone + 2 * 150ms padding = ~1.30s
    if not (1.20 <= dur <= 1.40):
        return TestResult(
            idx,
            "Silence & duration pre-checks",
            "FAIL",
            f"trim_silence output duration {dur:.2f}s outside expected window [1.20s, 1.40s]",
        )

    # 3. transcribe_audio returns "" immediately on silent/empty inputs (0 API calls)
    t_pre0 = time.perf_counter()
    r_empty = await transcribe_audio(b"")
    r_short = await transcribe_audio(b"x" * 500)
    r_silent = await transcribe_audio(silent_wav)
    precheck_elapsed_ms = (time.perf_counter() - t_pre0) * 1000.0

    if r_empty != "" or r_short != "" or r_silent != "":
        return TestResult(
            idx,
            "Silence & duration pre-checks",
            "FAIL",
            f"transcribe_audio did not return empty string for silent inputs: empty={r_empty!r}, short={r_short!r}, silent={r_silent!r}",
        )

    if precheck_elapsed_ms > 200.0:
        return TestResult(
            idx,
            "Silence & duration pre-checks",
            "FAIL",
            f"Pre-checks took too long ({precheck_elapsed_ms:.1f}ms); API might have been called",
        )

    total_ms = (time.perf_counter() - t0) * 1000.0
    details = f"Empty/short/silent WAV -> '' in {precheck_elapsed_ms:.1f}ms (0 API calls); Trim: 2.0s -> {dur:.2f}s"
    return TestResult(idx, "Silence & duration pre-checks", "PASS", details, total_ms)


async def test_stt_round_trip(idx: int) -> TestResult:
    """Check 9: End-to-end STT round-trip (Edge-TTS -> Groq Whisper) or SKIP if no key."""
    t0 = time.perf_counter()
    api_key = getattr(config, "GROQ_API_KEY", "") or ""
    if not api_key.strip():
        return TestResult(
            idx,
            "STT round-trip transcription",
            "SKIP",
            "No GROQ_API_KEY configured in backend/.env",
            0.0,
        )

    # Synthesize sample audio
    technical_text = "In lines 12 to 20, the compute cosine similarity function calculates the dot product."
    b64 = await synthesize_speech(technical_text)
    if not b64:
        return TestResult(idx, "STT round-trip transcription", "FAIL", "Failed to generate speech for round-trip test")

    audio_bytes = base64.b64decode(b64)

    t_stt = time.perf_counter()
    transcript = await transcribe_audio(
        audio_bytes=audio_bytes,
        domain_terms=["compute_cosine_similarity", "dot product"],
        mime_type="audio/mp3",
    )
    stt_latency_ms = (time.perf_counter() - t_stt) * 1000.0

    if not transcript:
        return TestResult(idx, "STT round-trip transcription", "FAIL", "Groq Whisper returned empty transcript")

    clean_trans = transcript.lower()
    if not ("cosine" in clean_trans or "similarity" in clean_trans or "dot" in clean_trans):
        return TestResult(
            idx,
            "STT round-trip transcription",
            "FAIL",
            f"Transcript {transcript!r} missed technical keywords",
            stt_latency_ms,
        )

    total_ms = (time.perf_counter() - t0) * 1000.0
    details = f"Transcribed in {stt_latency_ms:.0f}ms -> {transcript!r}"
    return TestResult(idx, "STT round-trip transcription", "PASS", details, total_ms)


async def test_bogus_key_resilience(idx: int) -> TestResult:
    """Check 10: Bogus-key path cleanly returns '' without raising exceptions."""
    import logging
    t0 = time.perf_counter()
    real_key = getattr(config, "GROQ_API_KEY", "")

    # Non-silent audio payload that passes pre-checks
    active_audio = _make_tone_wav(duration_s=1.0)

    # Temporarily suppress log warning for the expected intentional 401 test
    voice_logger = logging.getLogger("vivavoce.voice")
    prev_level = voice_logger.level
    voice_logger.setLevel(logging.CRITICAL)

    try:
        config.GROQ_API_KEY = "gsk_bogus_key_selftest_99999999999999999999"
        res = await transcribe_audio(active_audio, mime_type="audio/wav")

        if res != "":
            return TestResult(
                idx,
                "Bogus-key STT resilience",
                "FAIL",
                f"Expected empty string on bogus key, got {res!r}",
                (time.perf_counter() - t0) * 1000,
            )
    except Exception as exc:
        return TestResult(
            idx,
            "Bogus-key STT resilience",
            "FAIL",
            f"Bogus key raised an unhandled exception: {exc}",
            (time.perf_counter() - t0) * 1000,
        )
    finally:
        config.GROQ_API_KEY = real_key
        voice_logger.setLevel(prev_level)

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "Bogus-key STT resilience",
        "PASS",
        "HTTP 401 client error cleanly caught; returned '' without raising",
        elapsed,
    )


async def test_sync_inside_loop(idx: int) -> TestResult:
    """Check 15: Synchronous wrappers called from inside an already running event loop."""
    t0 = time.perf_counter()

    b64_in_loop = synthesize_speech_sync("Synchronous wrapper inside active event loop test.")
    if not b64_in_loop or detect_audio_format(base64.b64decode(b64_in_loop)) != "mp3":
        return TestResult(idx, "Synchronous wrappers (inside loop)", "FAIL", "synthesize_speech_sync failed inside running event loop")

    elapsed = (time.perf_counter() - t0) * 1000.0
    return TestResult(
        idx,
        "Synchronous wrappers (inside loop)",
        "PASS",
        "synthesize_speech_sync dispatches via worker thread without event-loop collision",
        elapsed,
    )


# ---------------------------------------------------------------------------
# Runner & Table Formatter
# ---------------------------------------------------------------------------

def print_results_table(results: List[TestResult]) -> int:
    """Format and print the results table, returning the count of failed tests."""
    col_w_idx = 3
    col_w_name = 37
    col_w_status = 6
    col_w_details = 75

    sep_line = "=" * (col_w_idx + col_w_name + col_w_status + col_w_details + 10)
    thin_line = "-" * (col_w_idx + col_w_name + col_w_status + col_w_details + 10)

    print()
    print(sep_line)
    header_title = "VivaVoce M3 Voice Pipeline — System Self-Test"
    print(header_title.center(len(sep_line)))
    print(sep_line)
    print(f" {'#':<{col_w_idx}} | {'Check Name':<{col_w_name}} | {'Status':<{col_w_status}} | {'Details':<{col_w_details}}")
    print(thin_line)

    n_pass = 0
    n_fail = 0
    n_skip = 0

    for r in results:
        if r.status == "PASS":
            n_pass += 1
            status_str = "PASS"
        elif r.status == "SKIP":
            n_skip += 1
            status_str = "SKIP"
        else:
            n_fail += 1
            status_str = "FAIL"

        details_truncated = r.details if len(r.details) <= col_w_details else r.details[: col_w_details - 3] + "..."
        print(f" {r.index:<{col_w_idx}} | {r.name:<{col_w_name}} | {status_str:<{col_w_status}} | {details_truncated:<{col_w_details}}")

    print(thin_line)
    exit_code = 1 if n_fail > 0 else 0
    summary = f"Summary: {len(results)} checks ran — {n_pass} PASSED, {n_fail} FAILED, {n_skip} SKIPPED (Exit code: {exit_code})"
    print(summary)
    print(sep_line)
    print()

    return n_fail


def main() -> int:
    """Self-test entry point."""
    results: List[TestResult] = []

    # 1. Run sync checks outside any event loop
    results.append(test_to_speakable_cases(1))
    results.append(test_build_spoken_text_cases(2))
    results.append(test_format_detection_headers(6))
    results.append(test_hallucination_filter(8))
    results.append(test_voice_router_endpoints(11))
    results.append(test_dev_server_endpoints(12))
    results.append(test_sync_outside_loop(13))
    results.append(test_windows_event_loop_sanity(14))

    # 2. Run async checks inside an isolated event loop
    async def _run_async_suite() -> List[TestResult]:
        async_res: List[TestResult] = []
        async_res.append(await test_tts_latency(3))
        async_res.append(await test_concurrent_tts(4))
        async_res.append(await test_filler_cache_system(5))
        async_res.append(await test_silence_and_prechecks(7))
        async_res.append(await test_stt_round_trip(9))
        async_res.append(await test_bogus_key_resilience(10))
        async_res.append(await test_sync_inside_loop(15))
        return async_res

    async_results = asyncio.run(_run_async_suite())
    results.extend(async_results)

    # Sort checks by index 1..15
    results.sort(key=lambda r: r.index)

    n_fail = print_results_table(results)
    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
