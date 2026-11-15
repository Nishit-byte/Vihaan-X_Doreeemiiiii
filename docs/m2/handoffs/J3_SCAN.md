# TASK J3-SCAN: Comprehensive Pre-Port Read-Only Scan Report

**Author:** Antigravity (Scan Agent)  
**Date:** 2026-11-15  
**Target:** Porting M2 (`C:\personal\shreyas\workOS\hackathons\vihaan\m2`) into Team Repo (`C:\personal\shreyas\workOS\hackathons\vihaan\team-repo`)  
**Scope:** Read-only inspection of source M2 repo, team repository state, import topology, inventory of old M2 files, dependent modules, schema compatibility, live endpoints, and risk analysis.

---

## 1. Source State (M2 Repo)

- **Repository Path:** `C:\personal\shreyas\workOS\hackathons\vihaan\m2` (remote: `github.com/shreyas-269/vivavoce-m2`)
- **Git Branch & Status:** Branch `main`, working tree clean, exactly up-to-date with `origin/main` (`df15e38`).
- **Context & Readiness Review:**
  - `docs/m2/CONTEXT.md`: §3 strict ownership (M2 owns `ingestion/`, `sandbox/`, `replay/`, `demo_cache/`, `tests_m2/`, `docs/m2/`), §5 interface specifications.
  - `docs/m2/FINAL_REVIEW.md`: J2 readiness PASS (164 tests passing / 2 skipped offline; 166 passed with network). Documented blockers B1 (top-level imports fail under `backend.main:app`), B2 (schema mismatches + missing `repo_root`), B3 (overwriting team code in M2 folders), B4 (demo challenge requires materializing local bundle).
  - `docs/m2/STATUS.md`: All tasks S0–S1, A1–A5, B1–B6, J1–J2 completed with PASS.
- **Exported Public Interfaces:**
  - `backend/ingestion/__init__.py`:
    - Functions: `clone_and_index_repo`, `index_repo_path`, `validate_github_url`, `extract_author_map`, `compute_authorship_stats`, `list_authors`, `parse_research_paper`, `is_demo_source`, `load_demo_repo`, `materialize_demo_repo`, `load_demo_challenge`, `load_cached_paper`
    - Classes: `IngestionError`, `RepoIndex`, `PaperIndex`
  - `backend/sandbox/__init__.py`:
    - Functions: `execute_verification`, `execute_verification_async`, `warm_up_sandbox`
    - Classes: `SandboxResult`
  - `backend/replay/__init__.py`:
    - Functions: `is_replay_enabled`, `is_record_enabled`
    - Classes: `ReplayStore`, `ReplayMiddleware`
- **Internal Import Pattern Inside M2:**
  Every file in M2 imports itself via **top-level package names**:
  - `from ingestion.config import ...`
  - `from ingestion.models import ...`
  - `from ingestion.repo_parser import ...`
  - `from ingestion.git_blame import ...`
  - `from ingestion.demo_loader import ...`
  - `from ingestion.pdf_parser import ...`
  - `from sandbox.sandbox_runner import ...`
  - `from replay.middleware import ...`
  - `from replay.store import ...`
  *(Zero occurrences of `from backend.ingestion...` or relative imports like `from .config import ...`).*

---

## 2. Team Repo State

- **Repository Path:** `C:\personal\shreyas\workOS\hackathons\vihaan\team-repo` (remote: `https://github.com/Nishit-byte/Vihaan.git`)
- **Git Status:** Clean working tree.
  - Newly generated directories: `backend/.venv`, `backend/.env`, and `frontend/node_modules` are properly matched and ignored by `.gitignore` (verified via `git check-ignore -v`).
  - No modified or untracked files present.
- **Branches:**
  - Current Local Branch: `main`
  - Default Branch: `main` (`remotes/origin/HEAD -> origin/main`)
  - Up to date: Yes (`Your branch is up to date with 'origin/main'`).
  - Local Branches: `* main`
  - Remote Branches:
    - `origin/HEAD -> origin/main`
    - `origin/feat/m2-ingestion`
    - `origin/feat/m4-frontend`
    - `origin/fix/viva-start-and-schema-sync`
    - `origin/m3-voice`
    - `origin/main`
- **Last 10 Commits on `main`:**
  1. `9f4a547` | Vidit Maheshwari | 2026-11-15 | fix(oa,proctor): enforce fullscreen mode, spoken plagiarism warning, and auto-exit in OA round
  2. `6fa83e5` | Vidit Maheshwari | 2026-11-15 | fix(proctor,dsa): speak anti-plagiarism voice warning on fullscreen exit and cleanly end OA session
  3. `f1dbb9a` | Vidit Maheshwari | 2026-11-15 | fix(frontend,fullscreen): trigger fullscreen synchronously on click to preserve user gesture token and handle document.fullscreenEnabled restrictions
  4. `0bb14c3` | Vidit Maheshwari | 2026-11-15 | fix(compiler,sandbox): resolve C++ undefined reference to WinMain with safe driver assembly, session lookup, and fallback main generation
  5. `a3dade2` | Vidit Maheshwari | 2026-11-15 | fix(compiler,fullscreen): strip class Solution redefinition from driver_code and auto-enable fullscreen on start with armed anti-plagiarism gate
  6. `f5f046d` | Vidit Maheshwari | 2026-11-14 | fix(compiler,dsa): sanitize C++ preprocessor directives and add dedicated Full Screen proctoring controls in DSA
  7. `53d965f` | Vidit Maheshwari | 2026-11-14 | feat(dsa,proctor): implement LeetCode compiler workspace, authentic class Solution templates, and anti-plagiarism fullscreen proctoring
  8. `da067c4` | Vidit Maheshwari | 2026-11-14 | Merge branch 'origin/main' into feat/leetcode-adaptive-oa
  9. `983e598` | Vidit Maheshwari | 2026-11-14 | feat(dsa): implement LeetCode profile ingestion, adaptive OA generator, and multi-language compiler workspace
  10. `ec3c761` | Shreyas Chaudhry | 2026-11-14 | fix(voice): harden spacebar push-to-talk and empty-audio handling
- **GitHub Permissions:** `unknown` (`gh` CLI not installed/configured in environment).

---

## 3. How the Backend Runs + Import Style

- **Launch Command:** `uvicorn backend.main:app` executed from the repository root (`C:\personal\shreyas\workOS\hackathons\vihaan\team-repo`).
- **`backend/__init__.py`:** Exists (`True`).
- **Team Import Topology:**
  - `backend/main.py` imports internal modules prefixed with `backend.`:
    - `from backend.brain.grader import generate_final_report`
    - `from backend.brain.oa_generator import generate_oa_questions`
    - `from backend.brain.state_machine import SESSIONS, process_turn, start_session`
    - `from backend.ingestion.leetcode_parser import fetch_leetcode_profile`
    - `from backend.models.schemas import ...`
    - `from backend.voice import voice_router, warm_filler_cache`
  - In `backend/main.py` lines 30–32, `sys.path` is modified:
    ```python
    PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    ```
    Only the project root is added to `sys.path`. `backend/` is NOT added.
  - Configuration files: No `pytest.ini`, `pyproject.toml`, or `conftest.py` setting `pythonpath` in the project root.
- **Import Style Conclusion:**
  > **One-Line Conclusion:** M2's `"from ingestion.xxx import ..."` style will **NOT** work out-of-the-box when started as `uvicorn backend.main:app` from the repo root because only the project root is on `sys.path` — but adding `sys.path.insert(0, str(Path(__file__).resolve().parent))` right after `PROJECT_ROOT` in `backend/main.py` solves this completely.
- **Read-Only Test Evidence (from repo root via `backend\.venv\Scripts\python.exe`):**
  1. `& "backend\.venv\Scripts\python.exe" -c "import backend.main"` -> Exit Code 0 (Success).
  2. `& "backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'backend'); import ingestion"` -> Exit Code 0 (Success).
  3. `& "backend\.venv\Scripts\python.exe" -c "import ingestion"` -> Exit Code 1 (`ModuleNotFoundError: No module named 'ingestion'`).

---

## 4. Old M2 Inventory

### 4.1 Files Under M2 Paths in Team Repo

| File Path | Lines | Type | One-Line Reason / Purpose | Last Git Commit (Hash \| Author \| Date \| Message) |
|---|---|---|---|---|
| `backend/ingestion/.gitkeep` | 0 | Stub | Placeholder directory anchor | `49886bb` \| Nishit-byte \| 2026-11-13 \| `feat(m1): lock schemas.py, AI brain state machine, grader, and FastAPI routes` |
| `backend/ingestion/__init__.py` | 12 | Stub / Export | Exports `PaperIndex`, `RepoIndex`, `clone_and_index_repo`, `load_demo_repo_index`, `parse_research_paper` | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/ingestion/git_blame.py` | 109 | Real | Subprocess `git blame --line-porcelain`, line attribution, `extract_author_map` | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/ingestion/leetcode_parser.py` | 271 | **TEAM CODE** | LeetCode profile GraphQL scraper + telemetry + offline fallback (Vidit / DSA mode) | `983e598` \| Vidit Maheshwari \| 2026-11-14 \| `feat(dsa): implement LeetCode profile ingestion, adaptive OA generator, and multi-language compiler workspace` |
| `backend/ingestion/paper_breakdown.py` | 1107 | **TEAM CODE** | Watermark-safe extraction, 12 section extractors, evidence references (Nishit / Paper explorer) | `b8b87b6` \| Nishit-byte \| 2026-11-14 \| `feat(research): rebuild full-width Research Paper Explorer with watermark-safe extraction and page-cited evidence` |
| `backend/ingestion/pdf_parser.py` | 769 | Real | PyMuPDF text & layout extraction + Gemini method graph + fallback, plus `load_demo_paper_bytes()` | `b8b87b6` \| Nishit-byte \| 2026-11-14 \| `feat(research): rebuild full-width Research Paper Explorer with watermark-safe extraction and page-cited evidence` |
| `backend/ingestion/repo_parser.py` | 391 | Real | Git clone + multi-language AST/symbol indexer (Py, TS, JS) + ranking + `load_demo_repo_index()` | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/sandbox/.gitkeep` | 0 | Stub | Placeholder directory anchor | `49886bb` \| Nishit-byte \| 2026-11-13 \| `feat(m1): lock schemas.py, AI brain state machine, grader, and FastAPI routes` |
| `backend/sandbox/__init__.py` | 5 | Stub / Export | Exports `execute_verification` | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/sandbox/sandbox_runner.py` | 662 | Real + **TEAM CODE** | Contains basic `execute_verification` (3 args) AND `execute_multi_language_sandbox` (C++, Java, JS, Python runner for DSA OA) | `0bb14c3` \| Vidit Maheshwari \| 2026-11-15 \| `fix(compiler,sandbox): resolve C++ undefined reference to WinMain with safe driver assembly, session lookup, and fallback main generation` |
| `backend/replay/` | — | Non-existent | Directory does not exist in team repo | — |
| `backend/demo_cache/.gitkeep` | 0 | Stub | Placeholder directory anchor | `49886bb` \| Nishit-byte \| 2026-11-13 \| `feat(m1): lock schemas.py, AI brain state machine, grader, and FastAPI routes` |
| `backend/demo_cache/sample_paper.pdf` | 3173 B | Fixture | Binary sample PDF document | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/demo_cache/sample_repo_index.json` | 34 | Fixture / Mock | Hardcoded JSON index for old demo repo | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/demo_cache/sample_repo/analysis.py` | 16 | Fixture | Python helper in old sample repo | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/demo_cache/sample_repo/config.py` | 9 | Fixture | Python config in old sample repo | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/demo_cache/sample_repo/loader.py` | 13 | Fixture | Python loader in old sample repo | `1c43ed3` \| Aayush Grover \| 2026-11-13 \| `feat(m2): implement ingestion and sandbox modules` |
| `backend/tests_m2/` | — | Non-existent | Directory does not exist in team repo | — |
| `docs/m2/` | — | Non-existent | Directory does not exist in team repo | — |

### 4.2 M2-Like Code Outside M2 Folders

- `backend/main.py`: Contains fallback mock implementations (`_mock_repo_index`, `_mock_paper_index`), dynamic invoke wrappers (`_invoke_m2_repo_ingestion`, `_invoke_m2_pdf_ingestion`, `_invoke_m2_sandbox`), built-in subprocess fallback runner, and route handlers.
- `backend/models/schemas.py`: Defines Pydantic contract types (`ASTFunctionSymbol`, `OwnedSymbol`, `RepoFile`, `RepoIndex`, `PaperNode`, `PaperBreakdown`, `PaperIndex`, `RunCodeRequest`, `RunCodeResponse`).
- `backend/requirements.txt`: Specifies dependencies (`GitPython`, `PyMuPDF`, `pytest`).
- `frontend/src/types/api.ts` & `frontend/src/services/apiClient.ts`: Defines TypeScript interfaces matching the backend API contract.

---

## 5. Dependents + Compatibility Table

### 5.1 Call Sites Outside M2 Modules

| Call Site (File:Line) | Old Name & Signature | My M2 Equivalent | Status | What a Thin Adapter Must Do |
|---|---|---|---|---|
| `backend/main.py:333` in `_invoke_m2_repo_ingestion` | `repo_parser.clone_and_index_repo(github_url: str) -> RepoIndex` (schema) | `clone_and_index_repo(github_url: str, *, use_cache=True) -> ingestion.models.RepoIndex` | **DIFFERENT RETURN SHAPE** | M2 returns internal `RepoIndex` (no `.author_map`). Adapter calls `extract_author_map` + `compute_authorship_stats`, formats `ASTFunctionSymbol` with `numbered_source()`, and maps to `models.schemas.RepoIndex`. |
| `backend/main.py:341` in `_invoke_m2_repo_ingestion` | `git_blame.extract_author_map(repo_path: str, files: list[str]) -> dict[str, list[schemas.OwnedSymbol]]` | `extract_author_map(repo_path: str, files: list[str], index=None, alias_map=None) -> dict[str, list[ingestion.models.OwnedSymbol]]` | **DIFFERENT RETURN SHAPE** | Map M2's `OwnedSymbol` (`line_start`, `line_end`, `symbol`) to schema's `OwnedSymbol(symbol_name=s.symbol)`. |
| `backend/main.py:364` in `_invoke_m2_pdf_ingestion` | `pdf_parser.load_demo_paper_bytes() -> bytes` | Missing in M2 (M2 uses `parse_research_paper(..., use_cache=True)`) | **MISSING IN MINE** | Add helper `load_demo_paper_bytes() -> bytes` to `pdf_parser.py` that reads `DEMO_CACHE_DIR / "sample_paper.pdf"`. |
| `backend/main.py:369` in `_invoke_m2_pdf_ingestion` | `pdf_parser.parse_research_paper(effective_bytes: bytes) -> schemas.PaperIndex` | `parse_research_paper(pdf_bytes: bytes, *, use_gemini=True, use_cache=True) -> ingestion.models.PaperIndex` | **DIFFERENT RETURN SHAPE** | M2 returns `PaperIndex` with `.mermaid` (not `.mermaid_graph`), `.excerpts` (not `.node_excerpts`), and nodes have `.id` (not `.node_id`). Adapter maps fields into `schemas.PaperIndex`. |
| `backend/main.py:385` in `_invoke_m2_sandbox` | `sandbox_runner.execute_verification(file_path: str, student_code: str, test_code: str) -> RunCodeResponse` | `execute_verification(file_path: str, student_code: str, test_code: str, repo_root=None) -> ingestion.models.SandboxResult` | **DIFFERENT RETURN SHAPE & MISSING ARGS** | Team call passes no `repo_root` (breaking sibling imports). Adapter passes `repo_root=session.repo_index.local_path`, maps `SandboxResult` to `schemas.RunCodeResponse` (`passed`, `verdict`, `runtime_ms`, `total_cases`, `passed_cases`). |
| `backend/main.py:958` in `POST /api/run-code` | `from backend.sandbox.sandbox_runner import execute_multi_language_sandbox` | Missing in M2 | **MISSING IN MINE** | Must preserve `execute_multi_language_sandbox` and its helper functions inside `backend/sandbox/sandbox_runner.py`. |
| `backend/ingestion/__init__.py:4` | `load_demo_repo_index() -> RepoIndex` | `load_demo_repo() -> tuple[RepoIndex, dict, list]` | **MISSING IN MINE** | Add backward-compatible `load_demo_repo_index()` to `repo_parser.py` and re-export in `ingestion/__init__.py`. |
| `backend/main.py:41` | `from backend.ingestion.leetcode_parser import fetch_leetcode_profile` | Team-created file | **MISSING IN MINE** | Must NOT overwrite or delete `backend/ingestion/leetcode_parser.py`. |
| `backend/main.py:301` | `from backend.ingestion.paper_breakdown import build_paper_breakdown` | Team-created file | **MISSING IN MINE** | Must NOT overwrite or delete `backend/ingestion/paper_breakdown.py`. |

### 5.2 Frontend Expected JSON Field Names

Inspected from `frontend/src/types/api.ts` and `frontend/src/services/apiClient.ts`:

1. **`POST /api/ingest-repo` -> `IngestResponse`:**
   - `session_id` (string)
   - `mode` ("repo")
   - `title` (string, optional)
   - `authors` (string[], optional)
   - `files` (array of `{ path: string, content: string, language?: string, line_count?: number }`)
   - `initial_turn` or `first_turn` (`TurnResponse` object)
2. **`POST /api/ingest-pdf` -> `IngestResponse`:**
   - `session_id` (string)
   - `mode` ("paper")
   - `title` (string, optional)
   - `mermaid_graph` (string | null)
   - `paper_nodes` (array of `{ node_id: string, label: string, summary?: string|null, section?: string|null, page?: number, excerpt: string }`)
   - `paper_breakdown` (`Record<string, unknown>` | null)
   - `initial_turn` or `first_turn` (`TurnResponse` object)
3. **`POST /api/run-code` -> `RunCodeResponse`:**
   - `passed` (boolean)
   - `verdict` (string, optional: e.g. "Accepted", "Wrong Answer", "Time Limit Exceeded")
   - `stdout` (string)
   - `stderr` (string)
   - `runtime_ms` (number)
   - `test_results` (array of `TestCaseResult`, optional)
   - `total_cases` (number, optional)
   - `passed_cases` (number, optional)

---

## 6. Live API Routes & Health

Verified via read-only GET requests to running server (`http://127.0.0.1:8000`):

### 6.1 `GET /api/health` Response
```json
{
  "status": "ok",
  "service": "VivaVoce Modular Monolith",
  "active_sessions": 1,
  "modules": {
    "m1_brain": true,
    "m2_repo_parser": true,
    "m2_pdf_parser": true,
    "m2_sandbox_runner": true,
    "m3_stt_service": true,
    "m3_tts_service": true
  }
}
```

### 6.2 All Routes from `openapi.json`
| HTTP Method | Route Path | Request Schema | Response Schema (200) |
|---|---|---|---|
| `GET` | `/api/health` | None | `Response Health Check Api Health Get` |
| `GET` | `/api/filler-audio` | None | `Response Get Filler Audio Clip Api Filler Audio Get` |
| `POST` | `/api/ingest` | `application/json: IngestRepoRequest` | `IngestResponse` |
| `POST` | `/api/ingest-dsa` | `application/json: IngestDsaRequest` | `IngestResponse` |
| `POST` | `/api/ingest-leetcode` | `application/json: IngestLeetCodeRequest` | `IngestLeetCodeResponse` |
| `POST` | `/api/ingest-pdf` | `multipart/form-data: Body_ingest_pdf...` | `IngestResponse` |
| `POST` | `/api/ingest-repo` | `application/json: IngestRepoRequest` | `IngestResponse` |
| `GET` | `/api/report/{session_id}` | None | `VivaReport` |
| `POST` | `/api/run-code` | `application/json: RunCodeRequest` | `RunCodeResponse` |
| `GET` | `/api/viva/report` | None | `VivaReport` |
| `GET` | `/api/viva/report/{session_id}` | None | `VivaReport` |
| `POST` | `/api/viva/terminate` | `application/json: TerminateSessionRequest` | `Response Terminate Viva Session...` |
| `POST` | `/api/viva/turn` | `multipart/form-data: Body_viva_turn...` | `TurnResponse` |
| `GET` | `/api/voice/fillers` | None | `Response List Fillers Api Voice Fillers Get` |
| `GET` | `/api/voice/health` | None | `Response Voice Health Api Voice Health Get` |
| `POST` | `/api/voice/speak` | `application/json: SpeakRequest` | `Response Speak Endpoint Api Voice Speak Post` |
| `POST` | `/api/voice/transcribe` | `application/json: TranscribeRequest` | `Response Transcribe Endpoint Api Voice Transcribe Post` |

---

## 7. Team Setup Files

### 7.1 M2-Touching Models in `backend/models/schemas.py`

```python
class ASTFunctionSymbol(BaseModel):
    name: str
    file_path: str
    line_start: int
    line_end: int
    args: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    calls: List[str] = Field(default_factory=list)
    constants: List[str] = Field(default_factory=list)
    code_snippet: Optional[str] = None

class OwnedSymbol(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    symbol_name: Optional[str] = None
    commit_count: int = 1

class RepoFile(BaseModel):
    path: str
    content: str
    language: str = "python"
    line_count: int = 0

class RepoIndex(BaseModel):
    repo_name: str
    github_url: str
    local_path: Optional[str] = None
    files: List[RepoFile] = Field(default_factory=list)
    symbols: List[ASTFunctionSymbol] = Field(default_factory=list)
    authors: List[str] = Field(default_factory=list)
    author_map: Dict[str, List[OwnedSymbol]] = Field(default_factory=dict)
    summary: str = ""

class PaperNode(BaseModel):
    node_id: str = Field(..., description="Mermaid node ID, e.g. N1..N8")
    label: str = Field(..., description="Short human-readable functional stage title")
    summary: Optional[str] = Field(default=None, description="Plain-language explanation of what this stage does")
    section: Optional[str] = None
    page: int = Field(default=1, ge=1, description="1-based PDF page number")
    excerpt: str = Field(..., description="Verbatim supporting excerpt from the paper")

class PaperIndex(BaseModel):
    title: str
    mermaid_graph: str = Field(..., description="Mermaid flowchart TD definition with N1..N8")
    nodes: List[PaperNode] = Field(default_factory=list)
    node_excerpts: Dict[str, str] = Field(default_factory=dict)
    full_text_summary: str = ""
    breakdown: Optional[PaperBreakdown] = None

class RunCodeRequest(BaseModel):
    session_id: str
    question_id: Optional[str] = None
    file_path: Optional[str] = "main.py"
    student_code: Optional[str] = None
    source_code: Optional[str] = None
    language: str = "python"
    test_code: Optional[str] = None
    test_cases: List[OATestCase] = Field(default_factory=list)
    run_hidden: bool = False
    custom_input: Optional[str] = None
    driver_code: Optional[str] = None

class RunCodeResponse(BaseModel):
    passed: bool
    verdict: str = "Accepted"
    stdout: str
    stderr: str
    runtime_ms: int
    test_results: List[TestCaseResult] = Field(default_factory=list)
    total_cases: int = 0
    passed_cases: int = 0

class IngestRepoRequest(BaseModel):
    github_url: str
    selected_author: Optional[str] = None
    use_demo_cache: bool = False

class IngestResponse(BaseModel):
    session_id: str
    mode: Literal["repo", "paper", "dsa"]
    title: str
    authors: List[str] = Field(default_factory=list)
    files: List[RepoFile] = Field(default_factory=list)
    mermaid_graph: Optional[str] = None
    paper_nodes: List[PaperNode] = Field(default_factory=list)
    paper_breakdown: Optional[PaperBreakdown] = None
    dsa_profile: Optional[LeetCodeProfileSummary] = None
    initial_turn: TurnResponse
    first_turn: Optional[TurnResponse] = None
    paper: Optional[Any] = None
```
*(Note: There is no dedicated `AuthorshipStat` class in `schemas.py`; `authors` is a `List[str]`, and `author_map` maps `str` to `List[OwnedSymbol]`. There is also no custom Error schema; errors return standard JSON/HTTPException).*

### 7.2 Dependency Audit in `backend/requirements.txt`
- `pymupdf`: **PRESENT** (`PyMuPDF>=1.24.13`)
- `google-genai`: **PRESENT** (`google-genai>=1.0.0`)
- `pydantic`: **PRESENT** (`pydantic>=2.9.0`)
- `fastapi`: **PRESENT** (`fastapi>=0.115.0`)
- `httpx`: **PRESENT** (`httpx>=0.27.2`)
- `pytest`: **PRESENT** (`pytest>=8.3.3`)
- `python-dotenv`: **PRESENT** (`python-dotenv>=1.0.1`)
- `fpdf2`: **NOT PRESENT** (Dev-only dependency for generating synthetic sample papers; not needed in production).

### 7.3 Git Ignore Check
Verified via `git check-ignore -v`:
- `.env` and `backend/.env`: Ignored by line 12 (`.env`).
- `backend/.venv`: Ignored by line 5 (`.venv/`).
- `frontend/node_modules`: Ignored by line 16 (`node_modules/`).
- `__pycache__` and `*.pyc`: Ignored by line 2 (`__pycache__/`).

### 7.4 Environment Variables Audit
- `.env.example`: Does **not** exist in team repo.
- `backend/.env`: Variable names and status:
  - `GEMINI_API_KEY`: **BLANK**
  - `GEMINI_MODEL`: **SET**
  - `GROQ_API_KEY`: **BLANK**
  - `GROQ_STT_MODEL`: **SET**
  - `TTS_PROVIDER`: **SET**
  - `EDGE_TTS_VOICE`: **SET**
  - `ELEVENLABS_API_KEY`: **BLANK**
  - `BACKEND_PORT`: **SET**
  - `OFFLINE_DEMO_FALLBACK`: **SET**
- **Offline / Mock Mode Behavior:**
  Whenever API keys are blank or external APIs fail, the backend automatically engages heuristic fallbacks:
  - `state_machine.py` generates deterministic AST/Paper heuristic questions.
  - `paper_breakdown.py` generates heuristic section breakdowns.
  - `dsa_coach.py` returns deterministic LeetCode profile data.
  - `main.py` returns pre-rendered audio / synthetic WAV.
  - `_invoke_m2_*` wrappers catch unhandled exceptions and return `_mock_repo_index` / `_mock_paper_index`.

### 7.5 Server Startup Code & Middleware
In `backend/main.py`:
- Lifespan startup:
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI):
      try:
          await warm_filler_cache()
      except Exception:
          pass
      yield
  ```
- Middleware: Only `CORSMiddleware` is configured.
- Neither `warm_up_sandbox` nor `ReplayMiddleware` is wired yet.

### 7.6 Team Test Files
- Tests outside `tests_m2`: Only `backend/voice/selftest.py` exists (M3 comprehensive self-test suite).
- How it is run: `cd backend; python -m voice.selftest`. *(Not run during this scan).*

---

## 8. Risks (What Would Break if Old M2 is Blindly Replaced 1:1)

1. **Destruction of Team-Owned Ingestion Code (CRITICAL):**
   - `backend/ingestion/leetcode_parser.py` (271 lines, Vidit): If deleted, `/api/ingest-leetcode` fails with `ModuleNotFoundError` and OA profile ingestion is destroyed.
   - `backend/ingestion/paper_breakdown.py` (1107 lines, Nishit): If deleted, `main.py` fails on import and the frontend Research Paper Explorer loses all breakdown data.
2. **Destruction of Multi-Language OA Sandbox (CRITICAL):**
   - `backend/sandbox/sandbox_runner.py` in team repo holds `execute_multi_language_sandbox` (supporting C++, Java, JS, Python for LeetCode mode). Overwriting this file with M2's file without appending this function breaks DSA code submission completely (`POST /api/run-code`).
3. **Silent Fallback to Mock Data Due to Top-Level Imports (CRITICAL):**
   - Because `uvicorn backend.main:app` is run from project root and `backend/` is not on `sys.path`, M2 modules (`from ingestion.config import ...`) fail to import.
   - The team's `_invoke_m2_*` wrappers catch all exceptions with `except Exception: pass` and quietly serve `_mock_repo_index` and `_mock_paper_index`. The app will appear to work, but judges will only ever see mock data!
4. **Schema Incompatibility in `_invoke_m2_*` Wrappers (HIGH):**
   - `_invoke_m2_repo_ingestion` accesses `repo_index.author_map`. M2's `RepoIndex` does not have this attribute. An `AttributeError` is raised and caught, silently serving mock data.
   - `_invoke_m2_pdf_ingestion` reads `.mermaid_graph` and `.node_excerpts`, while M2's `PaperIndex` has `.mermaid` and `.excerpts`.
   - `_invoke_m2_sandbox` returns M2's `SandboxResult` where `models.schemas.RunCodeResponse` is expected.
5. **Sandbox Multi-File Challenge Failure (HIGH):**
   - The current `_invoke_m2_sandbox` passes **no `repo_root`**. Without `repo_root`, student fixes cannot import sibling modules (e.g., `similarity.py` importing `utils.vector_ops`), so the demo's reference solution fails with `ModuleNotFoundError`.
6. **Event Loop Freezing (HIGH):**
   - All three `_invoke_m2_*` wrappers currently call M2 synchronously inside `async def` routes. Git clone (~45s timeout) or a Gemini timeout (~30-60s) will freeze the entire FastAPI event loop, blocking all voice turns and incoming HTTP requests.
7. **Missing Convenience Exports (MEDIUM):**
   - `pdf_parser.load_demo_paper_bytes()` and `repo_parser.load_demo_repo_index()` are expected by `main.py` and `ingestion/__init__.py`. If omitted, fallback demo loads raise errors.

---

## 9. Questions & Recommendations for Shreyas

1. **Approval for FIX PROMPT 1 in `backend/main.py`:**
   - Are you ready to update `backend/main.py` using FIX PROMPT 1 (from `FINAL_REVIEW.md`), which adds `sys.path.insert(0, BACKEND_DIR)`, mounts `ReplayMiddleware`, runs `warm_up_sandbox` and `materialize_demo_repo` in `lifespan`, registers the `IngestionError` exception handler, and installs the verified `_m2_repo_to_schema`, `_invoke_m2_repo_ingestion`, `_invoke_m2_pdf_ingestion`, and `_invoke_m2_sandbox` adapters?
2. **Approval for FIX PROMPT 2 Merge Strategy:**
   - Confirm that when copying M2 files:
     - `leetcode_parser.py` and `paper_breakdown.py` are left intact.
     - `execute_multi_language_sandbox` and its helper functions in `sandbox_runner.py` are preserved/appended.
     - `load_demo_paper_bytes()` is added to `pdf_parser.py`.
     - `load_demo_repo_index()` is added to `repo_parser.py` and re-exported in `ingestion/__init__.py`.
3. **Demo Cache / Fixtures Preservation:**
   - Keep existing `backend/demo_cache/sample_repo/` fixtures alongside M2's `sample_repo.bundle`, `sample_repo_index.json`, `sample_repo_authors.json`, `sample_repo_challenge.json`, and `sample_paper.pdf`.
4. **Git Branching Strategy for J3:**
   - Confirm target branch name for the port (e.g. `feat/m2-ingestion` or a fresh branch before merging to `main`).
