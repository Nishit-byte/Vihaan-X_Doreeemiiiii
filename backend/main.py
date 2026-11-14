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
from contextlib import asynccontextmanager
import inspect
import io
import os
from pathlib import Path
import struct
import sys
import time
import wave
from typing import Any, Dict, Optional

# Ensure project root is in sys.path so 'backend.xxx' imports resolve when run from inside backend/
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.brain.grader import generate_final_report
from backend.brain.oa_generator import generate_oa_questions
from backend.brain.state_machine import SESSIONS, process_turn, start_session
from backend.ingestion.leetcode_parser import fetch_leetcode_profile
from backend.models.schemas import (
    ASTFunctionSymbol,
    IngestDsaRequest,
    IngestLeetCodeRequest,
    IngestLeetCodeResponse,
    IngestRepoRequest,
    IngestResponse,
    LeetCodeProfileData,
    OAQuestion,
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
    VivaTurnRequest,
)
from backend.voice import voice_router, warm_filler_cache

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await warm_filler_cache()
    except Exception:
        pass
    yield

app = FastAPI(
    title="VivaVoce Modular Monolith API",
    description="Dual-modality AST-grounded & Visual Concept-Map Technical Examiner",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable wide CORS for Vite React frontend (Port 5173) and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount M3 voice router for /api/voice/health, /api/voice/fillers, etc.
app.include_router(voice_router, prefix="/api/voice")


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

    readme_code = (
        f"# {repo_name}\n\n"
        "AST-grounded retrieval and cosine reranking service.\n\n"
        "## Modules\n"
        "- `src/retrieval/scorer.py` — Thresholded cosine similarity reranker\n"
        "- `src/ingestion/chunker.py` — Sliding-window token chunker\n\n"
        "Click **Start Viva** on the right panel when you are ready for Question 1.\n"
    )

    return RepoIndex(
        repo_name=repo_name,
        github_url=github_url,
        files=[
            RepoFile(
                path="README.md",
                content=readme_code,
                language="markdown",
                line_count=len(readme_code.splitlines()),
            ),
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
    from backend.ingestion.paper_breakdown import build_paper_breakdown

    mock_sections = [
        {"title": n.section or n.label, "page_start": idx, "page_end": idx, "text": n.excerpt}
        for idx, n in enumerate(nodes, start=1)
    ]
    mock_pages = [f"{filename.replace('.pdf', '').replace('_', ' ').title()}\n" + "\n".join(n.excerpt for n in nodes)]
    breakdown = build_paper_breakdown(
        page_texts=mock_pages,
        sections=mock_sections,
        paper_nodes=nodes,
        reconstructed_from_headings=True,
    )
    return PaperIndex(
        title=filename.replace(".pdf", "").replace("_", " ").title(),
        mermaid_graph=mermaid_graph,
        nodes=nodes,
        node_excerpts={n.node_id: n.excerpt for n in nodes},
        full_text_summary="Research paper on AST-grounded adaptive technical viva and fluency-blind semantic evaluation.",
        breakdown=breakdown,
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
    """Calls M2's `parse_research_paper(pdf_bytes)` if present, loading demo PDF when `pdf_bytes` is empty."""
    try:
        from backend.ingestion import pdf_parser  # type: ignore

        effective_bytes = pdf_bytes
        if not effective_bytes and hasattr(pdf_parser, "load_demo_paper_bytes"):
            try:
                effective_bytes = pdf_parser.load_demo_paper_bytes()
            except Exception:
                effective_bytes = b""

        if effective_bytes and hasattr(pdf_parser, "parse_research_paper"):
            return pdf_parser.parse_research_paper(effective_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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


async def _invoke_m3_stt(
    audio_bytes: bytes,
    domain_prompt: str = "",
    mime_type: Optional[str] = None,
) -> str:
    """Calls M3's `transcribe_audio` (sync or async) in `backend/voice/stt_service.py`."""
    try:
        from backend.voice import stt_service  # type: ignore

        if hasattr(stt_service, "transcribe_audio"):
            fn = stt_service.transcribe_audio
            sig = inspect.signature(fn)
            kwargs: Dict[str, Any] = {}
            if "domain_prompt" in sig.parameters:
                kwargs["domain_prompt"] = domain_prompt
            if "mime_type" in sig.parameters:
                kwargs["mime_type"] = mime_type
            res = fn(audio_bytes, **kwargs)
            if inspect.isawaitable(res):
                res = await res
            if res:
                return str(res)
    except Exception as exc:
        print(f"[VIVA TURN STT ERROR] {exc}", flush=True)
    return ""


def _build_spoken_text(examiner_message: Optional[str], question: Optional[str]) -> str:
    """Combines examiner_message and question cleanly without duplicating text."""
    try:
        from backend.voice.tts_service import build_spoken_text
        return build_spoken_text(examiner_message or "", question or "")
    except Exception:
        ack = (examiner_message or "").strip()
        q = (question or "").strip()
        if not ack and not q:
            return ""
        if not ack:
            return q
        if not q:
            return ack
        if q.lower() in ack.lower():
            return ack
        if ack.lower() in q.lower():
            return q
        punct = "." if not ack.endswith((".", "!", "?", ";", ":")) else ""
        return f"{ack}{punct} {q}".strip()


def _invoke_m3_tts(text: str) -> str:
    """Calls M3's `synthesize_speech(text)` in `backend/voice/tts_service.py`, with valid WAV base64 fallback."""
    if not text:
        return _generate_silent_wav_base64()
    try:
        from backend.voice import tts_service  # type: ignore

        if hasattr(tts_service, "synthesize_speech_sync"):
            res = tts_service.synthesize_speech_sync(text)
            if res:
                return str(res)

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
                        res = pool.submit(asyncio.run, res).result(timeout=45)
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


@app.post("/api/ingest", response_model=IngestResponse, include_in_schema=True)
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

    # Ensure README.md is included in the file tree if present in the cloned repo
    if repo_index.local_path and not any(
        f.path.lower() == "readme.md" for f in repo_index.files
    ):
        from pathlib import Path

        local_root = Path(repo_index.local_path)
        for candidate_name in ("README.md", "readme.md", "Readme.md"):
            readme_path = local_root / candidate_name
            if readme_path.is_file():
                try:
                    readme_text = readme_path.read_text(encoding="utf-8", errors="replace")[:50_000]
                    repo_index.files.insert(
                        0,
                        RepoFile(
                            path=candidate_name,
                            content=readme_text,
                            language="markdown",
                            line_count=len(readme_text.splitlines()),
                        ),
                    )
                except OSError:
                    pass
                break

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
    Extracts text per page/section with furniture filtering and exact page provenance,
    constructs a validated method pipeline graph, and returns a structured PaperBreakdown.
    """
    pdf_bytes = b""
    filename = "sample_paper.pdf"
    if file is not None:
        filename = file.filename or filename
        pdf_bytes = await file.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Uploaded PDF file is empty.")

    paper_index = _invoke_m2_pdf_ingestion(pdf_bytes=pdf_bytes, filename=filename)

    # Research Paper Explorer does not use spoken voice synthesis; skip slow TTS here
    initial_turn = start_session(
        mode="paper",
        paper_index=paper_index,
        audio_synthesizer=lambda _: "",
    )

    detected_authors: list[str] = []
    if (
        paper_index.breakdown
        and paper_index.breakdown.authors_status == "identified"
        and paper_index.breakdown.authors_and_affiliations
    ):
        detected_authors = [paper_index.breakdown.authors_and_affiliations]

    return IngestResponse(
        session_id=initial_turn.session_id,
        mode="paper",
        title=paper_index.title,
        authors=detected_authors,
        files=[],
        mermaid_graph=paper_index.mermaid_graph,
        paper_nodes=paper_index.nodes,
        paper_breakdown=paper_index.breakdown,
        initial_turn=initial_turn,
    )


@app.post("/api/ingest-dsa", response_model=IngestResponse)
async def ingest_dsa(req: IngestDsaRequest) -> IngestResponse:
    """
    1. Fetches public LeetCode profile stats for `req.leetcode_username`.
    2. Calibrates initial DSA problem for `req.topic` based on solved distribution & weak spots.
    3. Returns a `README.md` diagnostic summary + starter problem file and starts an adaptive DSA Prep session.
    """
    from backend.brain.dsa_coach import fetch_leetcode_profile

    if not req.leetcode_username or not req.leetcode_username.strip():
        raise HTTPException(status_code=400, detail="leetcode_username is required.")

    profile = fetch_leetcode_profile(req.leetcode_username)

    initial_turn = start_session(
        mode="dsa",
        dsa_profile=profile,
        dsa_topic=req.topic,
        audio_synthesizer=_invoke_m3_tts,
    )

    readme_content = (
        f"# DSA Prep — @{profile.username}\n\n"
        f"- **Selected Topic:** {req.topic}\n"
        f"- **LeetCode Profile Source:** {'Live LeetCode GraphQL' if profile.fetched_live else 'Cached / Offline Fallback'}\n"
        f"- **Solved:** {profile.total_solved} total "
        f"(Easy: {profile.easy_solved}, Medium: {profile.medium_solved}, Hard: {profile.hard_solved})\n"
        f"- **Detected Focus Areas:** {', '.join(profile.weak_topics) or req.topic}\n"
        f"- **Recent Submissions:** {', '.join(profile.recent_submissions) or 'N/A'}\n\n"
        "## How Adaptive DSA Prep Works\n"
        "1. Click **Start Viva (Question 1)** on the right panel.\n"
        "2. Explain your approach & time/space complexity by voice or text.\n"
        "3. Edit the starter code in the Monaco IDE and click **Run & Verify**.\n"
        "4. VivaVoce detects gaps (complexity, edge cases, brute force) and serves your next problem adaptively.\n"
    )

    files = [
        RepoFile(
            path="README.md",
            content=readme_content,
            language="markdown",
            line_count=len(readme_content.splitlines()),
        )
    ]
    if initial_turn.coding_challenge:
        files.append(
            RepoFile(
                path=initial_turn.coding_challenge.target_file,
                content=initial_turn.coding_challenge.starter_code,
                language="python",
                line_count=len(initial_turn.coding_challenge.starter_code.splitlines()),
            )
        )

    return IngestResponse(
        session_id=initial_turn.session_id,
        mode="dsa",
        title=f"DSA Prep: @{profile.username} ({req.topic})",
        authors=[],
        files=files,
        mermaid_graph=None,
        paper_nodes=[],
        dsa_profile=profile,
        initial_turn=initial_turn,
    )


@app.post("/api/ingest-leetcode", response_model=IngestLeetCodeResponse)
async def ingest_leetcode(req: IngestLeetCodeRequest) -> IngestLeetCodeResponse:
    """
    1. Fetches public LeetCode telemetry via GraphQL and classifies profile into Category 1 or 2.
    2. Synthesizes 5-6 adaptive OA questions tailored to solved questions or top skill tier tags.
    3. Initializes an adaptive viva session and returns IngestLeetCodeResponse with initial_turn.
    """
    if not req.username_or_url or not req.username_or_url.strip():
        raise HTTPException(status_code=400, detail="username_or_url is required.")

    profile = await fetch_leetcode_profile(req.username_or_url.strip())
    oa_questions = await generate_oa_questions(
        profile=profile,
        num_easy=req.num_easy,
        num_medium=req.num_medium,
        num_hard=req.num_hard,
    )

    initial_turn = start_session(
        mode="dsa",
        leetcode_data=profile,
        oa_questions=oa_questions,
        audio_synthesizer=None,
    )
    initial_turn.audio_base64 = ""

    return IngestLeetCodeResponse(
        session_id=initial_turn.session_id,
        profile=profile,
        oa_questions=oa_questions,
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
    audio_mime: Optional[str] = None

    if "application/json" in content_type:
        body = await request.json()
        turn_req = TurnRequest(**body)
        eff_session_id = turn_req.session_id
        eff_student_text = turn_req.student_text
        eff_selected_author = turn_req.selected_author
        parsed_code_result = turn_req.code_result
        audio_mime = getattr(turn_req, "audio_mime", None) or body.get("audio_mime")
        if turn_req.audio_base64:
            raw_b64 = turn_req.audio_base64
            if not audio_mime and raw_b64.startswith("data:"):
                header = raw_b64.split(",", 1)[0]
                mime_part = header.replace("data:", "").replace(";base64", "").strip()
                if mime_part:
                    audio_mime = mime_part
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            raw_b64 = "".join(raw_b64.split())
            missing_padding = len(raw_b64) % 4
            if missing_padding:
                raw_b64 += "=" * (4 - missing_padding)
            try:
                audio_bytes = base64.b64decode(raw_b64)
            except Exception as b64_err:
                print(f"[VIVA TURN] Failed to decode audio_base64: {b64_err}", flush=True)
                audio_bytes = None
    else:
        eff_session_id = session_id or ""
        eff_student_text = student_text
        eff_selected_author = selected_author
        if audio is not None:
            audio_bytes = await audio.read()
            audio_mime = audio.content_type

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
        transcribed = await _invoke_m3_stt(
            audio_bytes,
            domain_prompt=domain_identifiers,
            mime_type=audio_mime,
        )
        eff_student_text = transcribed or ""

    try:
        response = process_turn(
            session_id=eff_session_id,
            student_text=eff_student_text,
            code_result=parsed_code_result,
            selected_author=eff_selected_author,
            audio_synthesizer=_invoke_m3_tts,
        )
        if audio_bytes and not eff_student_text:
            response.verdict = "no_answer"
            response.student_transcript = "(no speech detected)"
            response.ack_text = (
                "I couldn't hear any speech in that recording. "
                "Please hold Space to speak clearly, then release to submit (or type below)."
            )
            if not response.audio_base64 or response.audio_base64 == _generate_silent_wav_base64(250):
                spoken_text = _build_spoken_text(response.ack_text, response.question_text)
                response.audio_base64 = _invoke_m3_tts(spoken_text)

        print(
            f"[VIVA TURN] audio_bytes={len(audio_bytes) if audio_bytes else 0} "
            f"transcript={response.student_transcript!r} grade={response.verdict}",
            flush=True,
        )
        return response
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        print(f"[VIVA TURN ERROR] {exc}", flush=True)
        raise


@app.post("/api/run-code", response_model=RunCodeResponse)
async def run_code(req: RunCodeRequest) -> RunCodeResponse:
    """
    Executes candidate code either via multi-language stdin/stdout sandbox (OA mode)
    or via isolated 4-second pytest verification (Repo Viva mode).
    """
    session = SESSIONS.get(req.session_id)
    source = req.source_code or req.student_code or ""

    if (
        req.test_cases
        or req.custom_input is not None
        or (req.language and req.language.lower() in ("cpp", "c++", "java", "javascript", "js"))
    ):
        from backend.sandbox.sandbox_runner import execute_multi_language_sandbox

        result = execute_multi_language_sandbox(
            language=req.language or "python",
            source_code=source,
            test_cases=req.test_cases,
            run_hidden=req.run_hidden,
            custom_input=req.custom_input,
        )
    else:
        effective_test_code = req.test_code
        if not effective_test_code and session and session.active_challenge:
            effective_test_code = session.active_challenge.test_code

        result = _invoke_m2_sandbox(
            file_path=req.file_path or "main.py",
            student_code=source,
            test_code=effective_test_code or "",
        )

    if session is not None:
        challenge_desc = (
            session.active_challenge.description
            if session.active_challenge
            else f"Sandbox execution on {req.file_path or 'solution'}"
        )
        session.code_results.append(
            {
                "challenge_description": challenge_desc,
                "target_file": req.file_path or "main.py",
                "passed": result.passed,
                "runtime_ms": result.runtime_ms,
            }
        )

    return result


@app.get("/api/report/{session_id}", response_model=VivaReport)
@app.get("/api/viva/report/{session_id}", response_model=VivaReport)
@app.get("/api/viva/report", response_model=VivaReport)
async def get_viva_report(session_id: Optional[str] = None) -> VivaReport:
    """
    Generates the final Fluency-Blind Competency Report (`VivaReport`) with
    weighted rubric scores, Bloom L1-L4 topic radar items, sandbox verification status,
    a personalized study plan, and synthesized closing spoken remarks.
    """
    eff_id = session_id
    if not eff_id:
        if SESSIONS:
            eff_id = list(SESSIONS.keys())[-1]
        else:
            raise HTTPException(status_code=400, detail="session_id is required.")

    try:
        return generate_final_report(eff_id, audio_synthesizer=_invoke_m3_tts)
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
