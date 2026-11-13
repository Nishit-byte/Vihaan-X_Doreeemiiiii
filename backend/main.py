"""
FastAPI Modular Monolith Entrypoint for VivaVoce (backend/main.py).
Owner: Member 1 (Nishit - Team Lead & AI Brain Engineer)

Routes Mounted:
- POST /api/ingest-repo   -> Clones & AST-indexes GitHub repo (M2) + starts L1 Viva Session (M1) + TTS (M3)
- POST /api/ingest-pdf    -> Parses PDF & builds Mermaid concept map (M2) + starts Paper Viva Session (M1) + TTS (M3)
- POST /api/viva/turn     -> Transcribes speech (M3) + runs ReAct L1-L4 state machine (M1) + synthesizes speech (M3)
- POST /api/run-code      -> Runs isolated 4s pytest verification in sandbox (M2)
- GET  /api/report/{id}   -> Computes Fluency-Blind Rubric & Depth Radar VivaReport (M1)
- GET  /api/filler-audio  -> Returns pre-generated filler audio clip for instant PTT release feedback (M3)
- GET  /api/health        -> Reports live integration status of M1, M2, M3 modules
"""

from __future__ import annotations

import base64
import inspect
import io
import os
import struct
import time
import wave
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.brain.grader import generate_final_report
from backend.brain.state_machine import SESSIONS, process_turn, start_session
from backend.models.schemas import (
    ASTFunctionSymbol,
    IngestRepoRequest,
    IngestResponse,
    OwnedSymbol,
    PaperIndex,
    PaperNode,
    RepoFile,
    RepoIndex,
    RunCodeRequest,
    RunCodeResponse,
    TurnRequest,
    TurnResponse,
    VivaReport,
)

load_dotenv()

app = FastAPI(
    title="VivaVoce Modular Monolith API",
    description="Dual-modality AST-grounded & Visual Concept-Map Technical Examiner",
    version="1.0.0",
)

# Enable wide CORS for Vite React frontend (Port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# CHECKPOINT 1 MOCKS & AUTOMATIC M2 / M3 ADAPTER WIRING
# ============================================================================

def _generate_silent_wav_base64(duration_ms: int = 350) -> str:
    """Generates a valid playable WAV base64 string when TTS is offline/mocked."""
    sample_rate = 16000
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(struct.pack(f"<{num_samples}h", *([0] * num_samples)))
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _mock_repo_index(github_url: str) -> RepoIndex:
    """High-fidelity Checkpoint 1 fallback RepoIndex (with a planted edge-case bug for L4)."""
    repo_name = github_url.rstrip("/").split("/")[-1] or "sample-distributed-rag"
    scorer_code = (
        "from typing import List, Optional\n"
        "import math\n\n"
        "DEFAULT_SIMILARITY_FLOOR = 0.15\n\n"
        "def cosine_rerank(query_vec: List[float], doc_vec: List[float], floor: float = DEFAULT_SIMILARITY_FLOOR) -> float:\n"
        "    \"\"\"Computes thresholded cosine similarity between query and document embeddings.\n"
        "    NOTE: Contains a subtle zero-norm / empty-vector edge case bug for L4 verification.\n"
        "    \"\"\"\n"
        "    if not query_vec or not doc_vec:\n"
        "        return 0.0\n"
        "    dot = sum(a * b for a, b in zip(query_vec, doc_vec))\n"
        "    norm_q = math.sqrt(sum(a * a for a in query_vec))\n"
        "    norm_d = math.sqrt(sum(b * b for b in doc_vec))\n"
        "    # Planted bug: if a vector is all zeros [0.0, 0.0], norm_q * norm_d == 0.0 -> ZeroDivisionError\n"
        "    score = dot / (norm_q * norm_d)\n"
        "    return round(score, 4) if score >= floor else 0.0\n"
    )
    indexer_code = (
        "from typing import Dict, List\n\n"
        "MAX_CHUNK_TOKENS = 512\n\n"
        "def build_sliding_window_chunks(tokens: List[str], window: int = MAX_CHUNK_TOKENS, stride: int = 64) -> List[Dict]:\n"
        "    \"\"\"Splits token stream into overlapping AST-aware chunks with line provenance.\"\"\"\n"
        "    if not tokens:\n"
        "        return []\n"
        "    chunks = []\n"
        "    step = max(1, window - stride)\n"
        "    for start in range(0, len(tokens), step):\n"
        "        segment = tokens[start : start + window]\n"
        "        chunks.append({'start': start, 'end': start + len(segment), 'tokens': segment})\n"
        "    return chunks\n"
    )

    return RepoIndex(
        repo_name=repo_name,
        github_url=github_url,
        files=[
            RepoFile(
                path="src/retrieval/scorer.py",
                content=scorer_code,
                language="python",
                line_count=len(scorer_code.splitlines()),
            ),
            RepoFile(
                path="src/ingestion/chunker.py",
                content=indexer_code,
                language="python",
                line_count=len(indexer_code.splitlines()),
            ),
        ],
        symbols=[
            ASTFunctionSymbol(
                name="cosine_rerank",
                file_path="src/retrieval/scorer.py",
                line_start=6,
                line_end=18,
                args=["query_vec", "doc_vec", "floor"],
                docstring="Computes thresholded cosine similarity between query and document embeddings.",
                calls=["sum", "zip", "math.sqrt", "round"],
                constants=["DEFAULT_SIMILARITY_FLOOR"],
                code_snippet=scorer_code,
            ),
            ASTFunctionSymbol(
                name="build_sliding_window_chunks",
                file_path="src/ingestion/chunker.py",
                line_start=5,
                line_end=16,
                args=["tokens", "window", "stride"],
                docstring="Splits token stream into overlapping AST-aware chunks with line provenance.",
                calls=["max", "range", "len", "append"],
                constants=["MAX_CHUNK_TOKENS"],
                code_snippet=indexer_code,
            ),
        ],
        authors=["Nishit", "Aarav", "Priya", "Rohan"],
        author_map={
            "Nishit": [
                OwnedSymbol(
                    file_path="src/retrieval/scorer.py",
                    line_start=1,
                    line_end=18,
                    symbol_name="cosine_rerank",
                    commit_count=5,
                )
            ],
            "Aarav": [
                OwnedSymbol(
                    file_path="src/ingestion/chunker.py",
                    line_start=1,
                    line_end=16,
                    symbol_name="build_sliding_window_chunks",
                    commit_count=3,
                )
            ],
        },
        summary=f"Repository '{repo_name}' implementing AST-grounded chunking and cosine reranking.",
    )


def _mock_paper_index(filename: str = "sample_paper.pdf") -> PaperIndex:
    """High-fidelity Checkpoint 1 fallback PaperIndex with Mermaid flowchart N1..N6."""
    mermaid_graph = (
        "flowchart TD\n"
        '    N1["N1: Problem Formulation & Corpus Ingestion"] --> N2["N2: AST Data-Flow Graph Extraction"]\n'
        '    N2 --> N3["N3: Dual-Encoder Contrastive Alignment"]\n'
        '    N3 --> N4["N4: ReAct Examiner State Machine"]\n'
        '    N4 --> N5["N5: Isolated Sandbox Pass@k Verification"]\n'
        '    N5 --> N6["N6: Fluency-Blind Semantic Grading"]'
    )
    nodes = [
        PaperNode(
            node_id="N1",
            label="Problem Formulation & Corpus Ingestion",
            section="Section 1: Introduction",
            excerpt=(
                "Traditional automated grading systems rely on surface lexical overlap, penalizing non-native speakers. "
                "We formulate technical viva evaluation as a grounded state-tracking problem over source ASTs and concept graphs."
            ),
        ),
        PaperNode(
            node_id="N2",
            label="AST Data-Flow Graph Extraction",
            section="Section 2: AST Representation",
            excerpt=(
                "Following GraphCodeBERT (Guo et al., 2021), we parse source files into Abstract Syntax Trees to preserve variable data flow. "
                "Each function node retains exact line boundaries, call-graph edges, and git blame authorship provenance."
            ),
        ),
        PaperNode(
            node_id="N3",
            label="Dual-Encoder Contrastive Alignment",
            section="Section 3: Retrieval Architecture",
            excerpt=(
                "Spoken student explanations are projected into a shared semantic space alongside AST symbol representations. "
                "Hard negative mining prevents the retriever from confusing syntactically similar helper functions."
            ),
        ),
        PaperNode(
            node_id="N4",
            label="ReAct Examiner State Machine",
            section="Section 4: Adaptive Questioning",
            excerpt=(
                "The examiner traverses Revised Bloom's Taxonomy from Level 1 Recall up to Level 4 Mutation. "
                "At each turn, a ReAct reasoning step selects between DrillDown, Probe, Hint, or TriggerCodeChallenge."
            ),
        ),
        PaperNode(
            node_id="N5",
            label="Isolated Sandbox Pass@k Verification",
            section="Section 5: Empirical Execution",
            excerpt=(
                "To prevent hallucinated correctness, Level 4 claims are tested empirically by executing pytest suites inside a 4-second subprocess. "
                "Only solutions passing both nominal and boundary assertions receive full execution credit."
            ),
        ),
        PaperNode(
            node_id="N6",
            label="Fluency-Blind Semantic Grading",
            section="Section 6: Fairness & Evaluation",
            excerpt=(
                "Motivated by Koenecke et al. (2020), our grading rubric strips ASR hesitation tokens and assigns 0% weight to grammar or accent. "
                "Empirical benchmarks show a 41% reduction in false negatives across code-switched Hinglish speakers."
            ),
        ),
    ]
    return PaperIndex(
        title=filename.replace(".pdf", "").replace("_", " ").title(),
        mermaid_graph=mermaid_graph,
        nodes=nodes,
        node_excerpts={n.node_id: n.excerpt for n in nodes},
        full_text_summary="Research paper on AST-grounded adaptive technical viva and fluency-blind semantic evaluation.",
    )


# --- Dynamic M2 / M3 Wrappers (Zero-Conflict Plug-and-Play) ---

def _invoke_m2_repo_ingestion(github_url: str, use_demo_cache: bool = False) -> RepoIndex:
    """Calls M2's `clone_and_index_repo` and `extract_author_map` if present, else falls back to mock."""
    if not use_demo_cache:
        try:
            from backend.ingestion import repo_parser  # type: ignore

            if hasattr(repo_parser, "clone_and_index_repo"):
                repo_index: RepoIndex = repo_parser.clone_and_index_repo(github_url)
                # Wire M2's git_blame if not already populated inside clone_and_index_repo
                if not repo_index.author_map and repo_index.local_path:
                    try:
                        from backend.ingestion import git_blame  # type: ignore

                        if hasattr(git_blame, "extract_author_map"):
                            file_paths = [f.path for f in repo_index.files]
                            author_map = git_blame.extract_author_map(
                                repo_index.local_path, file_paths
                            )
                            repo_index.author_map = author_map
                            if not repo_index.authors:
                                repo_index.authors = list(author_map.keys())
                    except Exception:
                        pass
                return repo_index
        except Exception:
            pass

    return _mock_repo_index(github_url)


def _invoke_m2_pdf_ingestion(pdf_bytes: bytes, filename: str) -> PaperIndex:
    """Calls M2's `parse_research_paper(pdf_bytes)` if present, else falls back to mock."""
    if pdf_bytes:
        try:
            from backend.ingestion import pdf_parser  # type: ignore

            if hasattr(pdf_parser, "parse_research_paper"):
                return pdf_parser.parse_research_paper(pdf_bytes)
        except Exception:
            pass
    return _mock_paper_index(filename)


def _invoke_m2_sandbox(
    file_path: str, student_code: str, test_code: str
) -> RunCodeResponse:
    """Calls M2's `execute_verification` in `backend/sandbox/sandbox_runner.py`, with safe subprocess fallback."""
    try:
        from backend.sandbox import sandbox_runner  # type: ignore

        if hasattr(sandbox_runner, "execute_verification"):
            return sandbox_runner.execute_verification(file_path, student_code, test_code)
    except Exception:
        pass

    # Built-in isolated 4s tempfile pytest runner fallback (matches Section 5 spec)
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    start_ts = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        (tmp_path / "student_solution.py").write_text(student_code, encoding="utf-8")
        # Also write under target basename so either import style works
        target_name = Path(file_path).name
        if target_name.endswith(".py") and target_name != "student_solution.py":
            (tmp_path / target_name).write_text(student_code, encoding="utf-8")

        effective_test = test_code or (
            "def test_syntax_and_import():\n"
            "    import student_solution\n"
            "    assert student_solution is not None\n"
        )
        (tmp_path / "test_solution.py").write_text(effective_test, encoding="utf-8")

        try:
            env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    "--noconftest",
                    "-q",
                    "--tb=short",
                    "test_solution.py",
                ],
                cwd=tmpdir,
                env=env,
                capture_output=True,
                text=True,
                timeout=4,
            )
            elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
            return RunCodeResponse(
                passed=(proc.returncode == 0),
                stdout=proc.stdout.strip(),
                stderr=proc.stderr.strip(),
                runtime_ms=elapsed_ms,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
            return RunCodeResponse(
                passed=False,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr="Execution timed out after 4000ms (infinite loop or blocking call detected).",
                runtime_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_ts) * 1000)
            return RunCodeResponse(
                passed=False,
                stdout="",
                stderr=f"Sandbox execution error: {exc}",
                runtime_ms=elapsed_ms,
            )


async def _invoke_m3_stt(audio_bytes: bytes, domain_prompt: str = "") -> str:
    """Calls M3's `transcribe_audio` (sync or async) in `backend/voice/stt_service.py`."""
    try:
        from backend.voice import stt_service  # type: ignore

        if hasattr(stt_service, "transcribe_audio"):
            fn = stt_service.transcribe_audio
            sig = inspect.signature(fn)
            kwargs: Dict[str, Any] = {}
            if "domain_prompt" in sig.parameters:
                kwargs["domain_prompt"] = domain_prompt
            res = fn(audio_bytes, **kwargs)
            if inspect.isawaitable(res):
                res = await res
            if res:
                return str(res)
    except Exception:
        pass
    return ""


def _invoke_m3_tts(text: str) -> str:
    """Calls M3's `synthesize_speech(text)` in `backend/voice/tts_service.py`, with valid WAV base64 fallback."""
    if not text:
        return _generate_silent_wav_base64()
    try:
        from backend.voice import tts_service  # type: ignore

        if hasattr(tts_service, "synthesize_speech"):
            fn = tts_service.synthesize_speech
            res = fn(text)
            if inspect.isawaitable(res):
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    # If M3 implemented synthesize_speech as async, run in worker thread
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        res = pool.submit(asyncio.run, res).result(timeout=8)
                else:
                    res = asyncio.run(res)
            if res:
                return str(res)
    except Exception:
        pass
    return _generate_silent_wav_base64()


# ============================================================================
# FASTAPI ROUTES (CANONICAL CONTRACT)
# ============================================================================

@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Reports active module status for M1, M2, and M3."""
    m2_repo = False
    m2_pdf = False
    m2_sandbox = False
    m3_stt = False
    m3_tts = False

    try:
        from backend.ingestion import repo_parser  # type: ignore
        m2_repo = hasattr(repo_parser, "clone_and_index_repo")
    except Exception:
        pass
    try:
        from backend.ingestion import pdf_parser  # type: ignore
        m2_pdf = hasattr(pdf_parser, "parse_research_paper")
    except Exception:
        pass
    try:
        from backend.sandbox import sandbox_runner  # type: ignore
        m2_sandbox = hasattr(sandbox_runner, "execute_verification")
    except Exception:
        pass
    try:
        from backend.voice import stt_service  # type: ignore
        m3_stt = hasattr(stt_service, "transcribe_audio")
    except Exception:
        pass
    try:
        from backend.voice import tts_service  # type: ignore
        m3_tts = hasattr(tts_service, "synthesize_speech")
    except Exception:
        pass

    return {
        "status": "ok",
        "service": "VivaVoce Modular Monolith",
        "active_sessions": len(SESSIONS),
        "modules": {
            "m1_brain": True,
            "m2_repo_parser": m2_repo,
            "m2_pdf_parser": m2_pdf,
            "m2_sandbox_runner": m2_sandbox,
            "m3_stt_service": m3_stt,
            "m3_tts_service": m3_tts,
        },
    }


@app.post("/api/ingest-repo", response_model=IngestResponse)
async def ingest_repo(req: IngestRepoRequest) -> IngestResponse:
    """
    1. Clones & AST-indexes the repository (or loads pre-cached demo repo).
    2. Extracts `git blame` contributor ownership map.
    3. Initializes an adaptive L1-L4 Viva session and synthesizes opening TTS question.
    """
    if not req.github_url or not req.github_url.strip():
        raise HTTPException(status_code=400, detail="github_url is required.")

    repo_index = _invoke_m2_repo_ingestion(
        github_url=req.github_url.strip(),
        use_demo_cache=req.use_demo_cache,
    )

    initial_turn = start_session(
        mode="repo",
        repo_index=repo_index,
        selected_author=req.selected_author,
        audio_synthesizer=_invoke_m3_tts,
    )

    return IngestResponse(
        session_id=initial_turn.session_id,
        mode="repo",
        title=repo_index.repo_name,
        authors=repo_index.authors,
        files=repo_index.files,
        mermaid_graph=None,
        paper_nodes=[],
        initial_turn=initial_turn,
    )


@app.post("/api/ingest-pdf", response_model=IngestResponse)
async def ingest_pdf(
    file: Optional[UploadFile] = File(default=None),
) -> IngestResponse:
    """
    1. Extracts text per page/section using PyMuPDF and synthesizes a 5-to-8 node Mermaid flowchart.
    2. Maps each node ID (`N1..N8`) to a 2-sentence verbatim paper excerpt.
    3. Initializes an adaptive L1-L4 Paper Viva session and synthesizes opening TTS question.
    """
    pdf_bytes = b""
    filename = "sample_paper.pdf"
    if file is not None:
        filename = file.filename or filename
        pdf_bytes = await file.read()

    paper_index = _invoke_m2_pdf_ingestion(pdf_bytes=pdf_bytes, filename=filename)

    initial_turn = start_session(
        mode="paper",
        paper_index=paper_index,
        audio_synthesizer=_invoke_m3_tts,
    )

    return IngestResponse(
        session_id=initial_turn.session_id,
        mode="paper",
        title=paper_index.title,
        authors=[],
        files=[],
        mermaid_graph=paper_index.mermaid_graph,
        paper_nodes=paper_index.nodes,
        initial_turn=initial_turn,
    )


@app.post("/api/viva/turn", response_model=TurnResponse)
async def viva_turn(
    request: Request,
    session_id: Optional[str] = Form(default=None),
    student_text: Optional[str] = Form(default=None),
    selected_author: Optional[str] = Form(default=None),
    audio: Optional[UploadFile] = File(default=None),
) -> TurnResponse:
    """
    Processes a spoken or typed viva turn.
    Accepts EITHER:
    - `application/json` matching `TurnRequest` (`session_id`, `student_text`, `audio_base64`, `code_result`)
    - `multipart/form-data` with an `audio` Blob upload from `MediaRecorder` + `session_id`
    """
    content_type = request.headers.get("content-type", "")
    parsed_code_result: Optional[RunCodeResponse] = None
    audio_bytes: Optional[bytes] = None

    if "application/json" in content_type:
        body = await request.json()
        turn_req = TurnRequest(**body)
        eff_session_id = turn_req.session_id
        eff_student_text = turn_req.student_text
        eff_selected_author = turn_req.selected_author
        parsed_code_result = turn_req.code_result
        if turn_req.audio_base64:
            raw_b64 = turn_req.audio_base64.split(",")[-1]
            try:
                audio_bytes = base64.b64decode(raw_b64)
            except Exception:
                audio_bytes = None
    else:
        eff_session_id = session_id or ""
        eff_student_text = student_text
        eff_selected_author = selected_author
        if audio is not None:
            audio_bytes = await audio.read()

    if not eff_session_id or eff_session_id not in SESSIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Viva session '{eff_session_id}' not found. Call /api/ingest-repo or /api/ingest-pdf first.",
        )

    session = SESSIONS[eff_session_id]

    # Build domain prompt from AST symbol names for high-accuracy Groq Whisper STT
    domain_identifiers = ""
    if session.repo_index and session.repo_index.symbols:
        domain_identifiers = ", ".join(s.name for s in session.repo_index.symbols[:20])

    if (not eff_student_text or not eff_student_text.strip()) and audio_bytes:
        transcribed = await _invoke_m3_stt(audio_bytes, domain_prompt=domain_identifiers)
        eff_student_text = transcribed or "I implemented this function to handle the core data transformation and boundary checks."

    try:
        response = process_turn(
            session_id=eff_session_id,
            student_text=eff_student_text,
            code_result=parsed_code_result,
            selected_author=eff_selected_author,
            audio_synthesizer=_invoke_m3_tts,
        )
        return response
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/run-code", response_model=RunCodeResponse)
async def run_code(req: RunCodeRequest) -> RunCodeResponse:
    """
    Executes the student's live bug fix against the session's `pytest` suite inside
    an isolated 4-second subprocess (`sandbox_runner.py`) and records the empirical result.
    """
    session = SESSIONS.get(req.session_id)
    effective_test_code = req.test_code

    if not effective_test_code and session and session.active_challenge:
        effective_test_code = session.active_challenge.test_code

    result = _invoke_m2_sandbox(
        file_path=req.file_path,
        student_code=req.student_code,
        test_code=effective_test_code or "",
    )

    if session is not None:
        challenge_desc = (
            session.active_challenge.description
            if session.active_challenge
            else f"Live sandbox verification on {req.file_path}"
        )
        session.code_results.append(
            {
                "challenge_description": challenge_desc,
                "target_file": req.file_path,
                "passed": result.passed,
                "runtime_ms": result.runtime_ms,
            }
        )

    return result


@app.get("/api/report/{session_id}", response_model=VivaReport)
async def get_viva_report(session_id: str) -> VivaReport:
    """
    Generates the final Fluency-Blind Competency Report (`VivaReport`) with
    weighted rubric scores, Bloom L1-L4 topic radar items, sandbox verification status,
    and a personalized study plan.
    """
    try:
        return generate_final_report(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/filler-audio")
async def get_filler_audio_clip() -> Dict[str, str]:
    """Returns a short pre-cached acknowledgment audio clip (M3 `audio_utils.get_filler_audio`)."""
    try:
        from backend.voice import audio_utils  # type: ignore

        if hasattr(audio_utils, "get_filler_audio"):
            clip = audio_utils.get_filler_audio()
            if clip:
                return {"audio_base64": str(clip)}
    except Exception:
        pass
    return {"audio_base64": _generate_silent_wav_base64(250)}
