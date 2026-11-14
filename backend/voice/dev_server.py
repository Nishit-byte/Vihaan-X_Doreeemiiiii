"""VivaVoce Voice Pipeline — Dev / Mock Backend Server.

Standalone FastAPI application for Lane B frontend development and end-to-end
testing before integration with M1's full ReAct state machine.
"""

from __future__ import annotations

import base64
import binascii
from contextlib import asynccontextmanager
import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .audio_utils import warm_filler_cache
from .stt_service import transcribe_audio
from .tts_service import build_spoken_text, synthesize_speech
from . import voice_router

# Read-only import of canonical TurnResponse schema for shape validation
try:
    from backend.models.schemas import TurnResponse
except ImportError:
    try:
        from models.schemas import TurnResponse  # type: ignore
    except ImportError:
        TurnResponse = None  # type: ignore

log = logging.getLogger("vivavoce.voice.dev_server")

# 6 canned questions grounded in utils/similarity.py with depths: 1, 1, 2, 3, 4, 4
CANNED_QUESTIONS: List[Dict[str, Any]] = [
    {
        "topic": "Cosine Similarity Definition",
        "depth_level": 1,
        "ack_text": "Welcome to your viva on utils/similarity.py. Let's begin with vector mathematics.",
        "question_text": "In utils/similarity.py, what mathematical formula is used to compute the cosine similarity between two embedding vectors, and what range of values does it return?",
        "highlight": {
            "file_path": "utils/similarity.py",
            "line_start": 12,
            "line_end": 25,
        },
        "diagram_node_id": None,
        "paper_excerpt": None,
        "coding_challenge": None,
        "done": False,
    },
    {
        "topic": "Dot Product Implementation",
        "depth_level": 1,
        "ack_text": "Good start on the mathematical definition.",
        "question_text": "Looking at lines 15 to 20 of utils/similarity.py, how is the dot product implemented and what happens if the input vectors have mismatched dimensions?",
        "highlight": {
            "file_path": "utils/similarity.py",
            "line_start": 15,
            "line_end": 20,
        },
        "diagram_node_id": None,
        "paper_excerpt": None,
        "coding_challenge": None,
        "done": False,
    },
    {
        "topic": "Vector Normalization & Zero-Division",
        "depth_level": 2,
        "ack_text": "Good explanation of vector dimensions.",
        "question_text": "Why does normalize_vector check whether the L2 norm is strictly below 1e-12 before dividing, and what numerical edge case does that prevent?",
        "highlight": {
            "file_path": "utils/similarity.py",
            "line_start": 28,
            "line_end": 42,
        },
        "diagram_node_id": None,
        "paper_excerpt": None,
        "coding_challenge": None,
        "done": False,
    },
    {
        "topic": "Batch Similarity & Memory Trade-offs",
        "depth_level": 3,
        "ack_text": "Solid point on zero-division and underflow prevention.",
        "question_text": "Looking at batch_cosine_similarity in lines 45 to 68, what is the memory complexity trade-off of computing the full pairwise similarity matrix in RAM versus streaming chunk-by-chunk for 50,000 vectors?",
        "highlight": {
            "file_path": "utils/similarity.py",
            "line_start": 45,
            "line_end": 68,
        },
        "diagram_node_id": None,
        "paper_excerpt": None,
        "coding_challenge": None,
        "done": False,
    },
    {
        "topic": "Mutation & Sparse Vector Challenge",
        "depth_level": 4,
        "ack_text": "Thoughtful analysis of the RAM and streaming trade-offs.",
        "question_text": "In lines 95 to 110 of utils/similarity.py, there is a bug where sparse vectors fail because indices are assumed contiguous. How would you refactor this to support dictionary-based sparse embeddings?",
        "highlight": {
            "file_path": "utils/similarity.py",
            "line_start": 95,
            "line_end": 110,
        },
        "diagram_node_id": None,
        "paper_excerpt": None,
        "coding_challenge": {
            "description": "Fix sparse dot product index assumption in utils/similarity.py",
            "target_file": "utils/similarity.py",
            "starter_code": "def sparse_cosine_similarity(vec_a: dict[int, float], vec_b: dict[int, float]) -> float:\n    # Fix: only multiply overlapping keys\n    pass\n",
            "test_code": "def test_sparse_cosine():\n    assert sparse_cosine_similarity({0: 1.0, 5: 2.0}, {0: 1.0, 2: 3.0}) > 0\n",
        },
        "done": False,
    },
    {
        "topic": "Evaluation & Wrap-up",
        "depth_level": 4,
        "ack_text": "Great job completing the technical viva on utils/similarity.py.",
        "question_text": "You demonstrated strong comprehension of vector operations, memory trade-offs, and edge cases. Your technical evaluation is complete.",
        "highlight": None,
        "diagram_node_id": None,
        "paper_excerpt": None,
        "coding_challenge": None,
        "done": True,
    },
]

# Track question index per session_id
session_positions: Dict[str, int] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm filler cache and pre-synthesize canned questions on startup."""
    log.info("Warming filler audio cache...")
    await warm_filler_cache()
    log.info("Pre-warming TTS cache for canned questions...")
    for q in CANNED_QUESTIONS:
        spoken = build_spoken_text(q["ack_text"], q["question_text"])
        await synthesize_speech(spoken)
    yield


app = FastAPI(
    title="VivaVoce Voice Dev Server",
    description="Standalone mock backend for M3 voice pipeline development and testing",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Vite dev servers on ports 5173 and 5174
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount voice pipeline router at /api/voice
app.include_router(voice_router, prefix="/api/voice")


class DevTurnRequest(BaseModel):
    """Local schema for turn requests accepted by dev server."""

    session_id: str = Field(..., description="Active viva session identifier")
    student_text: Optional[str] = Field(default=None, description="Direct text answer")
    audio_base64: Optional[str] = Field(default=None, description="Base64 encoded audio answer")
    audio_mime: Optional[str] = Field(default=None, description="Audio MIME type, e.g. audio/webm")
    selected_author: Optional[str] = Field(default=None, description="Optional author filter")
    code_result: Optional[Any] = Field(default=None, description="Optional sandbox test result")

    model_config = {"extra": "ignore"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "VivaVoce Voice Dev Server", "status": "running"}


@app.get("/api/dev/start")
async def dev_start(session_id: Optional[str] = None) -> dict[str, Any]:
    """Start or reset a viva session, returning the opening TurnResponse."""
    sid = session_id or f"dev-{uuid.uuid4().hex[:8]}"
    session_positions[sid] = 0

    q = CANNED_QUESTIONS[0]
    spoken = build_spoken_text(q["ack_text"], q["question_text"])
    audio_b64 = await synthesize_speech(spoken)

    turn_dict: Dict[str, Any] = {
        "session_id": sid,
        "student_transcript": "",
        "verdict": "start",
        "ack_text": q["ack_text"],
        "question_text": q["question_text"],
        "audio_base64": audio_b64,
        "topic": q["topic"],
        "depth_level": q["depth_level"],
        "highlight": q.get("highlight"),
        "diagram_node_id": q.get("diagram_node_id"),
        "paper_excerpt": q.get("paper_excerpt"),
        "coding_challenge": q.get("coding_challenge"),
        "done": False,
    }

    if TurnResponse is not None:
        try:
            return TurnResponse(**turn_dict).model_dump()
        except Exception as exc:
            log.warning("TurnResponse validation warning: %s", exc)

    return turn_dict


@app.post("/api/viva/turn")
async def mock_viva_turn(req: DevTurnRequest) -> dict[str, Any]:
    """Mock implementation of M1's POST /api/viva/turn endpoint."""
    sid = req.session_id

    # 1. Transcribe audio if provided, else use student_text
    student_transcript = ""
    if req.audio_base64 and req.audio_base64.strip():
        raw_b64 = req.audio_base64.strip()
        if raw_b64:
            if "," in raw_b64 and "base64" in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            try:
                audio_bytes = base64.b64decode(raw_b64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid base64 audio data: {exc}",
                )

            student_transcript = await transcribe_audio(
                audio_bytes=audio_bytes,
                mime_type=req.audio_mime or "audio/webm",
                domain_terms=["similarity", "cosine", "vector", "embedding", "normalize"],
            )
    elif req.student_text:
        student_transcript = req.student_text.strip()

    # 2. Verdict rule: empty -> no_answer, > 40 chars -> strong, else partial
    clean = student_transcript.strip()
    if not clean:
        verdict = "no_answer"
    elif len(clean) > 40:
        verdict = "strong"
    else:
        verdict = "partial"

    # 3. Advance question index for this session
    curr_pos = session_positions.get(sid, 0)
    next_pos = min(curr_pos + 1, len(CANNED_QUESTIONS) - 1)
    session_positions[sid] = next_pos
    q = CANNED_QUESTIONS[next_pos]

    ack = q["ack_text"]
    spoken = build_spoken_text(ack, q["question_text"])
    audio_b64 = await synthesize_speech(spoken)

    turn_dict: Dict[str, Any] = {
        "session_id": sid,
        "student_transcript": student_transcript,
        "verdict": verdict,
        "ack_text": ack,
        "question_text": q["question_text"],
        "audio_base64": audio_b64,
        "topic": q["topic"],
        "depth_level": q["depth_level"],
        "highlight": q.get("highlight"),
        "diagram_node_id": q.get("diagram_node_id"),
        "paper_excerpt": q.get("paper_excerpt"),
        "coding_challenge": q.get("coding_challenge"),
        "done": q.get("done", False),
    }

    if TurnResponse is not None:
        try:
            return TurnResponse(**turn_dict).model_dump()
        except Exception as exc:
            log.warning("TurnResponse validation warning: %s", exc)

    return turn_dict

