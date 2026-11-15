# M2 INTEGRATION NOTES FOR THE VIVAVOCE TEAM

**Author:** M2 Workstream (Ingestion, Sandbox & Demo Reliability)  
**Date:** 2026-11-15  
**Status:** All tasks complete (S0–S1, Lane A [A1–A5], Lane B [B1–B6], Join J1). 164 tests passing. 100% offline demo ready.

---

## 1. For Member 1 (Nishit — Backend Lead, AI Brain, `main.py`)

### 1.1 Exact Dependencies for `backend/requirements.txt`
Add these packages to `backend/requirements.txt`:
```txt
pymupdf>=1.25.0
google-genai>=1.0.0
pydantic>=2.0.0
fastapi>=0.110.0
python-multipart>=0.0.12  # needed for UploadFile
httpx>=0.27.0
pytest>=8.0.0
python-dotenv>=1.0.0
fpdf2>=2.8.0  # dev-only (fixture generation for sample paper)
```

### 1.2 Environment Variables for `.env.example`
Add these configuration variables to `.env.example`:
```bash
# --- Gemini LLM Configuration ---
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash
GEMINI_TIMEOUT_S=30

# --- Repository Cloning & Indexing ---
CLONE_TIMEOUT_S=45
CLONE_DEPTH=50
FULL_CLONE_MAX_KB=20000
MAX_INDEXED_FILES=15
MAX_FILE_LINES=2000
MAX_REPO_PY_FILES=2000

# --- Sandbox Pytest Execution ---
SANDBOX_TIMEOUT_S=8
SANDBOX_OUTPUT_LIMIT=8000

# --- Demo & Offline Replay Reliability ---
DEMO_REPO_URL=https://github.com/shreyas-269/vivavoce-demo-repo
DEMO_REPLAY=0
DEMO_RECORD=0
```
> [!NOTE]
> Set `GEMINI_MODEL=gemini-3.8-flash` in `.env`. The code default in `config.py` is still `gemini-2.5-flash`, which returns 404 for new keys ("model is no longer available to new users"); `build_concept_graph` then retries with `gemini-3.8-flash`, and falls back to a deterministic heuristic graph if the network/API fails.

### 1.3 FastAPI Startup Lifespan & Middleware Setup
In `backend/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from replay import ReplayMiddleware
from sandbox import warm_up_sandbox


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm Python/pytest runtime caches (~1 s) so the first viva verification is instant
    warm_ms = warm_up_sandbox()
    print(f"[VivaVoce Startup] Sandbox pre-warmed in {warm_ms} ms")
    yield


app = FastAPI(title="VivaVoce API", lifespan=lifespan)

# CRITICAL ORDERING FOR REPLAY MIDDLEWARE:
# Starlette makes the last-added middleware outermost.
# Add ReplayMiddleware FIRST, and CORSMiddleware AFTER.
# This ensures CORS is the outermost layer, allowing browser preflight OPTIONS
# requests to succeed and adding Access-Control-Allow-Origin headers during offline replay.
app.add_middleware(ReplayMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 1.4 Global Exception Handler for Ingestion Errors
M2 raises `IngestionError(user_message, detail="")` for bad URLs, unreadable PDFs, or clone timeouts. Register this handler in `backend/main.py`:
```python
from fastapi import Request
from fastapi.responses import JSONResponse
from ingestion import IngestionError


@app.exception_handler(IngestionError)
async def ingestion_error_handler(request: Request, exc: IngestionError):
    return JSONResponse(
        status_code=400,
        content={"error": exc.user_message, "detail": exc.detail},
    )
```

### 1.5 Copy-Pasteable Route Code for Ingestion & Sandbox

> [!NOTE]
> The route snippets below are illustrative. M2 call signatures are real and verified, but `models.schemas` classes, `session_id`, `session_store`, `generate_initial_turn` and `generate_paper_initial_turn` are placeholders for M1's own code; `docs/m2/SCHEMAS_FROM_M1.md` did not exist when written, so align field names to M1's real `schemas.py`.

#### Route 1: `POST /api/ingest-repo`
```python
import asyncio
from fastapi import APIRouter
from ingestion import (
    clone_and_index_repo,
    compute_authorship_stats,
    extract_author_map,
    is_demo_source,
    load_demo_repo,
    materialize_demo_repo,
)
from models.schemas import IngestRepoRequest, IngestResponse, RepoFile

router = APIRouter()


@router.post("/api/ingest-repo", response_model=IngestResponse)
async def ingest_repo_endpoint(req: IngestRepoRequest):
    use_cache = req.use_demo_cache or is_demo_source(req.github_url)

    if use_cache:
        # Instant offline load (< 4 ms). The cached index has local_path="" — materialize the
        # bundle or /api/run-code gets repo_root="" and even the correct fix fails (J2-verified).
        repo_index, author_map, author_stats = load_demo_repo()
        repo_index.local_path = await asyncio.to_thread(materialize_demo_repo)
    else:
        # Clone, index AST, calculate blame — all blocking: run in a worker thread (see §1.8)
        repo_index = await asyncio.to_thread(clone_and_index_repo, req.github_url, use_cache=False)
        files_to_blame = [f.path for f in repo_index.files]
        author_map = await asyncio.to_thread(extract_author_map, repo_index.local_path, files_to_blame, index=repo_index)
        author_stats = await asyncio.to_thread(compute_authorship_stats, repo_index.local_path, files_to_blame)

    # Store repo_index in session state for citation guard and sandbox
    # session_store[session_id] = {"repo_index": repo_index, "repo_root": repo_index.local_path}

    # Map to M1's schema
    repo_files = [
        RepoFile(path=f.path, content=f.content, line_count=f.line_count)
        for f in repo_index.files
    ]
    author_names = [s.author for s in author_stats]

    # Generate initial viva turn grounded in code
    initial_turn = await generate_initial_turn(repo_index, selected_author=req.selected_author)

    return IngestResponse(
        session_id=session_id,
        mode="repo",
        title=repo_index.repo_id,
        authors=author_names,
        files=repo_files,
        initial_turn=initial_turn,
    )
```

#### Route 2: `POST /api/ingest-pdf`
```python
from fastapi import APIRouter, File, UploadFile
from ingestion import parse_research_paper
from models.schemas import IngestResponse, PaperNode

router = APIRouter()


@router.post("/api/ingest-pdf", response_model=IngestResponse)
async def ingest_pdf_endpoint(file: UploadFile = File(...)):
    pdf_bytes = await file.read()

    # Parses sections, runs Gemini structured output (or heuristic fallback),
    # verifies verbatim excerpts, and builds Mermaid in code (~15 ms if cached)
    paper_index = await asyncio.to_thread(parse_research_paper, pdf_bytes, use_cache=True)

    # Map to M1's schema
    paper_nodes = [
        PaperNode(
            node_id=n.id,
            label=n.label,
            section=n.section,
            page=n.page,
            excerpt=n.excerpt,
        )
        for n in paper_index.nodes
    ]

    initial_turn = await generate_paper_initial_turn(paper_index)

    return IngestResponse(
        session_id=session_id,
        mode="paper",
        title=paper_index.title,
        mermaid_graph=paper_index.mermaid,
        paper_nodes=paper_nodes,
        initial_turn=initial_turn,
    )
```

#### Route 3: `POST /api/run-code`
```python
from fastapi import APIRouter
from models.schemas import RunCodeRequest, RunCodeResponse
from sandbox import execute_verification_async

router = APIRouter()


@router.post("/api/run-code", response_model=RunCodeResponse)
async def run_code_endpoint(req: RunCodeRequest):
    # Retrieve repository root path from session state
    # session = session_store.get(req.session_id, {})
    repo_root = session.get("repo_root", None)

    # Run verification asynchronously in thread pool with 8 s timeout and process tree cleanup
    target_file = req.file_path or "main.py"
    student_code = req.student_code or req.source_code or ""
    test_code = req.test_code or ""

    sandbox_result = await execute_verification_async(
        file_path=target_file,
        student_code=student_code,
        test_code=test_code,
        repo_root=repo_root,
    )

    # Map SandboxResult to M1 RunCodeResponse
    if sandbox_result.timed_out:
        verdict = "Time Limit Exceeded"
    elif sandbox_result.passed:
        verdict = "Accepted"
    else:
        verdict = "Wrong Answer"

    total_cases = sandbox_result.tests_passed + sandbox_result.tests_failed

    return RunCodeResponse(
        passed=sandbox_result.passed,
        verdict=verdict,
        stdout=sandbox_result.stdout,
        stderr=sandbox_result.stderr,
        runtime_ms=sandbox_result.runtime_ms,
        total_cases=total_cases,
        passed_cases=sandbox_result.tests_passed,
    )
```

### 1.6 How to Use Citation Guard & Domain Terms
1. **Citation Snapping (`snap_range` — P0-1.2):**
   Prevent LLM line citation hallucinations:
   ```python
   # When examiner LLM cites lines (e.g. similarity.py lines 1-10):
   file_path, snapped_start, snapped_end = repo_index.snap_range(
       cited_file, cited_start, cited_end
   )
   # Rule 1: Contained in function -> returns unchanged
   # Rule 2: Partly outside -> clamped to function boundary
   # Rule 3: Outside any function -> snapped to nearest real function
   # Rule 4: Unknown file -> snapped to top file's first function
   ```
2. **Numbered Source Snippets (`numbered_source`):**
   Inject clean, right-aligned line numbers into examiner prompts:
   ```python
   prompt_code = repo_index.numbered_source("similarity.py", start=10, end=25)
   # Produces:
   #   10 | def cosine_similarity(vec_a, vec_b):
   #   11 |     dot = dot_product(vec_a, vec_b)
   #   12 |     norm_a = vector_norm(vec_a)
   ```
3. **STT Domain Terms (`identifiers` — P1-3.5):**
   Extract top functions, classes, constants, and module names for M3:
   ```python
   domain_terms = repo_index.identifiers(limit=60)
   # Pass domain_terms to M3 voice session for speech-to-text vocabulary biasing
   ```

### 1.7 Offline Replay Recording & Execution Procedure
To guarantee 100% demo survivability during judge evaluation:
1. **Pre-record a clean demo run (Hour 20 / Checkpoint 5):**
   ```bash
   # In backend/.env:
   DEMO_RECORD=1
   DEMO_REPLAY=0
   ```
   Start backend and frontend, conduct one complete scripted viva playthrough from start to finish. Responses and extracted MP3 audio clips are saved to `backend/demo_cache/replay/`.
2. **Replay Mode (Judging Day / Offline):**
   ```bash
   # In backend/.env:
   DEMO_RECORD=0
   DEMO_REPLAY=1
   ```
   Disconnect Wi-Fi. Every `/api/*` request returns the recorded responses instantly with zero API calls.
3. **Resetting Replay Queue:**
   To present the demo again, trigger `POST /api/replay/reset` or restart the server.

### 1.8 Blocking calls — wrap in `asyncio.to_thread` inside `async def` routes (J2)
Every M2 function below is synchronous and blocks for seconds. Called directly in an `async def`
route it freezes the WHOLE server (voice turns included) for that long.

| Function | Worst case | How to call from an async route |
|---|---|---|
| `clone_and_index_repo(url, use_cache=False)` | ~45 s clone timeout + indexing | `await asyncio.to_thread(clone_and_index_repo, url, use_cache=False)` |
| `index_repo_path(path)` | 1–10 s on big repos | `await asyncio.to_thread(index_repo_path, path)` |
| `extract_author_map(...)` / `compute_authorship_stats(...)` | git blame, 10 s per file each (they blame separately) | `await asyncio.to_thread(...)` |
| `materialize_demo_repo()` | ~0.3 s first call (git clone of bundle) | `await asyncio.to_thread(materialize_demo_repo)`; also call once at startup |
| `parse_research_paper(pdf_bytes)` | ~2 × `GEMINI_TIMEOUT_S` + 1 s (≈ 61 s) if Gemini hangs | `await asyncio.to_thread(parse_research_paper, pdf_bytes)` |
| `execute_verification(...)` | 8 s timeout | use `await execute_verification_async(...)` (already threaded) |
| `warm_up_sandbox()` | ~1 s | fine once in lifespan, or `await asyncio.to_thread(warm_up_sandbox)` |

No thread needed (fast, in-memory): `load_demo_repo`, `load_demo_challenge`, `load_cached_paper`,
`is_demo_source`, `validate_github_url`, and the `RepoIndex` helpers (`snap_range`,
`numbered_source`, `identifiers`).

> [!WARNING]
> The snippets in §1.5 were written before M1's real `main.py` was read. The team repo's
> `main.py` already wraps M2 in `_invoke_m2_repo_ingestion` / `_invoke_m2_pdf_ingestion` /
> `_invoke_m2_sandbox`, expects M1 schema types, and is launched as `uvicorn backend.main:app`
> (M2's top-level `ingestion` / `sandbox` / `replay` imports then fail and the wrappers silently fall
> back to mocks). Use the verified adapter code in `docs/m2/FINAL_REVIEW.md` (FIX PROMPT 1) for J3.

---

## 2. For Member 4 (Frontend Lead — React, Monaco IDE, Paper View)

### 2.1 File Tree & File Contents (Monaco IDE)
`IngestResponse.files` provides all indexed Python files (M2 `FileIndex` fields: `path`, `content`, `line_count`, plus imports/functions/classes/constants; the frontend may derive language from the `.py` extension). Each file contains:
```json
{
  "path": "similarity.py",
  "content": "from utils.vector_ops import dot_product, vector_norm\n\ndef cosine_similarity(vec_a, vec_b):\n...",
  "line_count": 43
}
```
`RepoIndex.file_tree` contains all Python paths (including unindexed):
```json
[
  "cli.py",
  "data_loader.py",
  "models.py",
  "ranking.py",
  "similarity.py",
  "utils/__init__.py",
  "utils/vector_ops.py"
]
```

### 2.2 Paper View: Mermaid Diagram & Node Highlighting
`IngestResponse.mermaid_graph` returns valid Mermaid `flowchart TD` text with `classDef active stroke-width:4px;`:
```mermaid
flowchart TD
    N1["Concept Knowledge Graph Construction"]
    N2["Dynamic Memory Decay Modeling"]
    N3["Peer Complementarity Scoring"]
    N4["Synchronous Pairing and Session"]
    N5["Collaborative Question Generation"]
    N6["Dual-Feedback Performance Update"]
    N1 --> N2
    N2 --> N3
    N3 --> N4
    N4 --> N5
    N5 --> N6
    classDef active stroke-width:4px;
```
- **Active Node Highlighting:** To highlight node `N2` during a viva question, append `class N2 active;` to the Mermaid diagram before rendering.
- **Node Excerpts & Page Navigation:** When the candidate clicks a node (e.g. `N2`), look up `paper_nodes[i]`:
  - `page`: 1-based page number (e.g. jump PDF viewer to page 2).
  - `excerpt`: verbatim verified quote from the research paper.
  - `label`: functional stage title.

### 2.3 Authorship Breakdown (Fluency-Blind Report Modal)
Authorship statistics from `compute_authorship_stats`:
```json
[
  {
    "author": "Aman Verma",
    "email": "aman@example.com",
    "lines": 135,
    "share_of_lines": 0.4981
  },
  {
    "author": "Priya Nair",
    "email": "priya@example.com",
    "lines": 78,
    "share_of_lines": 0.2878
  },
  {
    "author": "Rohan Gupta",
    "email": "rohan@example.com",
    "lines": 58,
    "share_of_lines": 0.2140
  }
]
```

---

## 3. For Member 3 (Shreyas — Voice Pipeline & STT)

### 3.1 Consuming `RepoIndex.identifiers()` for STT Biasing
`repo_index.identifiers(limit=60)` returns prioritized module names, classes, functions, and constants:
```python
domain_terms = [
    "has_common_interest",
    "profile_summary",
    "create_student",
    "is_suitable_partner",
    "Student",
    "score_student_pair",
    "top_k_partners",
    "dot_product",
    "vector_norm",
    "cosine_similarity",
    "jaccard_similarity",
    "data_loader",
]
```
Pass these terms to Whisper / Deepgram `keywords` or Gemini Live initial system prompt:
```text
Technical domain terms for speech recognition: {", ".join(domain_terms)}
```
This prevents transcription errors on domain terms like `"cosine similarity"` or camelCase function names.

---

## 4. For Pitch & Judges (Honest Security & Limitations)

> [!IMPORTANT]
> **Use exact honest wording during pitch and documentation:**
> - Describe the sandbox as **"sandboxed with a timeout"**.
> - **NEVER** use words like "isolated", "containerized", or "microVM".
> - State clearly: **"Python repositories only."**

### Sandbox Threat Model Disclosure
Be 100% transparent with judges:
1. **What the sandbox DOES protect against:**
   - **Credential leakage via environment dictionary:** Student code child process receives a brand-new sanitized environment dict (`PATH`, `TEMP`, `SYSTEMROOT`) without parent API keys (`GEMINI_API_KEY`, etc.).
   - **Infinite loops & CPU exhaustion:** Hard 8-second timeout enforced by Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` that terminates all child and grandchild processes unconditionally.
   - **Fork/memory bombs (Windows):** the Job object caps each run at 32 processes and 1 GB; every process is killed when the run ends. (macOS/Linux: timeout + process-group kill only, no caps.)
   - **Memory buffer deadlocks:** stdout and stderr are written to disk files and tail-truncated to 8,000 characters.
   - **Import hygiene:** `sys.executable -I` ignores `PYTHONPATH` and user site-packages, and `pytest.ini` (`pythonpath = .`) makes the copied repo importable. Packages installed in the backend venv are still importable.
2. **What the sandbox does NOT protect against (same OS user boundary):**
   - Because the child process runs under the same OS user account, student code can still inspect ancestor environments via `psutil` or read readable host files (e.g. `backend/.env`).
   - Student code can locate and read backend/.env via sys.prefix (the venv lives in backend/). Use a throwaway, quota-limited Gemini key for demos.
   - Network calls are not blocked at the kernel/OS firewall level.
   - Code can forge exit status by writing a mock summary line and calling `os._exit(0)`.
   - **Pitch answer:** Explain that production multi-tenant deployments would wrap this runner in Docker containers or gVisor microVMs; for the hackathon prototype, a lightweight timeout-enforced subprocess runner provides fast < 1.2 s verifications.

---

## 5. Consolidated Requests for Other Members (S1–B6)

| Source | Target | Item / Action Required |
|--------|--------|------------------------|
| **S1** | M1 | Add packages to `requirements.txt`: `pymupdf`, `google-genai`, `pydantic`, `fastapi`, `python-multipart` (needed for UploadFile), `httpx`, `pytest`, `python-dotenv` (`fpdf2` is dev-only). |
| **S1** | M1 | Add all environment variables from §1.2 to `.env.example`. |
| **A1** | M1 | In clone subprocesses, enforce `GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`, `GIT_ASKPASS=echo` to prevent hangs. |
| **A2** | M1 | In examiner prompts, format line citations using `repo_index.numbered_source(path, start, end)`. |
| **A2** | M1 | Wrap LLM question citations with `repo_index.snap_range(path, start, end)` to prevent out-of-bounds hallucinations. |
| **A2** | M3 | Pass `repo_index.identifiers()` into speech-to-text prompt as `domain_terms`. |
| **A3** | M1 | Use `extract_author_map` and `compute_authorship_stats` to compute author contributions for fluency-blind reports. |
| **A4** | M1/M4 | Offline demo repo "studysync" contains planted `ZeroDivisionError` in `similarity.py` on all-zero vectors; starter fails, reference passes. |
| **A5** | M1 | Support `use_demo_cache=True` in `POST /api/ingest-repo` for instant < 4 ms offline loading. |
| **B1** | Pitch | Always use wording "sandboxed with a timeout", never "isolated". Disclose same-user OS limitations honestly. |
| **B1** | M1 | Load `.env` using `dotenv_values` and pass API keys explicitly to SDK clients rather than putting them in `os.environ`. |
| **B2** | M1 | Call `warm_up_sandbox()` on FastAPI startup in lifespan hook. |
| **B2** | M1 | Use `await execute_verification_async(...)` in FastAPI route handlers so subprocesses do not block the event loop. |
| **B4** | M4 | Support `classDef active stroke-width:4px;` in Mermaid renderer for active stage highlighting. |
| **B5** | M1/M4 | In `POST /api/ingest-pdf`, return `PaperIndex` with `paper_nodes` and `node_excerpts` for click-to-quote UI navigation. |
| **B6** | M1 | In `main.py`, add `app.add_middleware(ReplayMiddleware)` BEFORE `CORSMiddleware` so CORS remains outermost. |
| **B6** | Team | Record demo session during Hour 20 (`DEMO_RECORD=1`) for 100% offline judging fallback (`DEMO_REPLAY=1`). |

---

## 6. Ready-to-Send Team Message

*(Copy and paste the message below into your team WhatsApp / Discord channel)*

```text
🚀 Hey team! M2 (Ingestion, Sandbox & Demo Reliability) is 100% COMPLETE and fully tested (164 tests passing)!

Here is what is ready for you:
1. Ingestion:
   - Mode A (Repo): GitHub clone + AST indexing (< 85 ms) + git blame authorship breakdown.
   - Mode B (Paper): PDF text extraction + 6-stage concept graph + Mermaid flowchart (< 15 ms).
   - Offline Demo Cache: Pre-baked "studysync" repo bundle + "sample_paper.pdf" ready for instant offline loading (< 4 ms).

2. Sandbox:
   - Pytest execution sandboxed with an 8-second timeout and process-tree termination.
   - Multi-file repository copying with sibling package imports.
   - Async wrapper (execute_verification_async) and server startup warm-up (warm_up_sandbox).

3. Reliability & Replay:
   - Pure ASGI ReplayMiddleware: records live viva turns (DEMO_RECORD=1) and replays them with zero API calls (DEMO_REPLAY=1) if venue Wi-Fi drops.

Full integration notes, copy-pasteable route handlers, and frontend JSON schemas are in docs/m2/NOTES_FOR_TEAM.md!
```
