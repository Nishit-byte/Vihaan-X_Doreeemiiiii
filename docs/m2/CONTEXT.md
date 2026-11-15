# M2 INGESTION, SANDBOX & DEMO RELIABILITY — SHARED CONTEXT

Read this whole file at the start of EVERY M2 task chat. It is the single source of truth for
the project, the way Shreyas works, and the exact interfaces M2 must implement.

---

## 1. The project in one paragraph

VivaVoce is a hackathon project (Vihaan hackathon, Education track, 24-hour build). It is a
spoken-plus-text technical examiner. A student gives it a GitHub repo (Mode A) or a research
paper PDF (Mode B). VivaVoce then runs an adaptive spoken viva: it asks questions grounded in
exact code lines or paper diagram nodes, climbs a 4-level Bloom's ladder (L1 Recall, L2
Comprehension, L3 Analysis/Trade-offs, L4 Evaluation/Mutation + live code fix), verifies code
fixes by running pytest in a sandbox with a timeout, and produces a fluency-blind report.

Stack: one FastAPI backend (modular monolith, port 8000) with modules brain/, ingestion/,
voice/, sandbox/ talking through Pydantic schemas, and one React + Vite + TypeScript frontend.

Team roles:
- M1 Nishit — brain + contract: models/schemas.py, brain/*, main.py (all routes)
- M2 — INGESTION, SANDBOX & DEMO RELIABILITY (this workstream)
- M3 — voice pipeline (Shreyas; built separately in its own repo)
- M4 — frontend shell (Monaco IDE, Paper view, Report modal, apiClient.ts, types/api.ts)

M2 feeds everyone: M1's examiner needs the repo index (code with line numbers, functions,
call boundaries) to ask grounded questions; M4's IDE needs file contents and the Mermaid
graph; M3's speech-to-text needs repo identifiers; the report needs authorship stats; the L4
coding challenge needs the sandbox; and the demo needs to survive the venue Wi-Fi dropping.

Integration checkpoints that matter to M2: Checkpoint 3 (Hour 14) — repo_parser, git_blame and
sandbox_runner replace M1's mocks; Checkpoint 4 (Hour 18) — pdf_parser feeds the paper view;
Checkpoint 5 (Hour 20) — demo cache + replay recording locked in.

### Where the code lives (standalone mode)
Shreyas has no access to the team repo (github.com/Nishit-byte/Vihaan) yet, so M2 is built in
its own private repo first and ported into the team repo later (task J3):
- M2 folder (= repo root):  C:\personal\shreyas\workOS\hackathons\vihaan\m2
- GitHub:                   github.com/shreyas-269/vivavoce-m2 (private), branch main
- It is a SIBLING of the M3 folder (...\vihaan\project), never inside it, so the M3 repo's
  reviews never see M2 files.
- Paths inside the M2 repo mirror the team repo exactly (backend/ingestion/..., backend/sandbox/...),
  so the J3 port is a 1:1 copy.
- docs/m2/... always means C:\personal\shreyas\workOS\hackathons\vihaan\m2\docs\m2\...
- There is no schemas.py here. M2 uses its own internal models (§5.2). Whenever M1 shares
  schemas.py, Shreyas pastes it into docs/m2/SCHEMAS_FROM_M1.md and later tasks align to it.

---

## 2. How Shreyas works (rules for every agent)

1. Work is split into small tasks in two parallel lanes:
   - Lane A = REPO INTELLIGENCE (clone, AST index, git blame, authorship, demo repo)
   - Lane B = EXECUTION, PAPERS & REPLAY (sandbox, PDF parser, Mermaid, replay mode)
   The lanes never wait on each other. They meet only in the join tasks (J1–J3).
2. Every task runs in its OWN fresh chat. Builds happen in Antigravity with Gemini 3.8 Flash.
   Reviews happen in Claude Code with Claude Sonnet 5.5 (or Opus 5.5 for the hard tasks).
3. PROMPTS OVER TERMINAL COMMANDS. Agents run commands themselves. Never hand Shreyas a list of
   terminal commands. If Shreyas must do something physically (paste an API key, sign in, look
   at the screen), give him short plain-language steps.
4. Every build task ends by writing a handoff file: docs/m2/handoffs/<TASK_ID>.md (template in §6).
5. Build agents NEVER run git commit. Only the Claude reviewer commits (and pushes), after a PASS.
6. Only the Claude reviewer edits docs/m2/STATUS.md. Run reviews one at a time.
7. File ownership rule (§3) is absolute. Breaking it is an automatic review FAIL.
8. Windows + PowerShell. Use paths and commands that work on Windows.
9. Never put secrets in committed files. API keys live only in backend/.env (git-ignored).
10. Communication style with Shreyas: concept-first explanations (the "why" before the "how"),
    detailed answers are welcome, and if he makes a grammar mistake, correct it briefly at the end.
11. If a file this task should create ALREADY contains real code (check REPO_STATE.md and the
    file itself), upgrade it to meet this spec instead of rewriting it; keep what works and say
    what you changed in the handoff.

---

## 3. File ownership (what M2 may touch)

M2 may create/edit ONLY these paths (relative to the M2 repo root):

- backend/ingestion/__init__.py
- backend/ingestion/config.py         (M2 addition: env + logging config, shared by all M2 packages)
- backend/ingestion/models.py         (M2 addition: internal Pydantic models, §5.2)
- backend/ingestion/repo_parser.py
- backend/ingestion/git_blame.py
- backend/ingestion/pdf_parser.py
- backend/ingestion/demo_loader.py    (M2 addition: offline demo cache loader)
- backend/ingestion/dev_cli.py        (M2 addition: dev command-line tool, never used in prod)
- backend/sandbox/__init__.py
- backend/sandbox/sandbox_runner.py
- backend/replay/__init__.py, backend/replay/store.py, backend/replay/middleware.py
                                       (M2 addition: offline replay mode, from the improvement plan)
- backend/demo_cache/**               (sample repo bundle + build script, cached indexes,
                                       sample paper + build script, papers/, replay/)
- backend/tests_m2/**                 (M2 addition: pytest tests, one file per task)
- backend/.env                        (local only, never committed; M2 keys only)
- .gitignore, README.md (M2 repo only)
- docs/m2/**

Team files M2 must NOT create here (they belong to M1/M3/M4 and would break the J3 port):
backend/main.py, backend/requirements.txt, backend/models/, backend/brain/, backend/voice/,
frontend/, .env.example. Needed changes to those go in the handoff under "Requests for other
members"; J1 compiles them into docs/m2/NOTES_FOR_TEAM.md.

Installing packages into the local virtualenv (backend/.venv) is allowed. The list of packages
M2 needs is recorded for M1's requirements.txt in the handoffs, not written into a requirements file.

---

## 4. What M1's contract expects from M2 (from the spec + improvement plan)

The spec's TurnResponse cites code as {file_path, line_start, line_end} and paper nodes as
diagram_node_id + paper_excerpt. M1's routes will call M2 like this:
- POST /api/ingest-repo -> clone_and_index_repo(url), extract_author_map(...), compute_authorship_stats(...)
- POST /api/ingest-pdf  -> parse_research_paper(pdf_bytes)
- POST /api/run-code    -> execute_verification(file_path, student_code, test_code, repo_root)
- startup               -> warm_up_sandbox(); app.add_middleware(ReplayMiddleware)

The improvement plan's contract gaps that M2 data must be able to fill:
- Monaco needs the file tree + file contents (RepoIndex.file_tree, FileIndex.content).
- Paper view needs the Mermaid string + node_id -> excerpt map (PaperIndex.mermaid, .excerpts).
- Report needs AuthorshipStat {author, share_of_lines, max_depth_reached} — M2 provides
  author + share_of_lines; M1 fills max_depth_reached.
- RunCodeResponse needs passed, stdout, stderr, runtime_ms (SandboxResult is a superset).
- One shared error shape {error, detail?}: M2 raises IngestionError(user_message, detail) and M1
  maps it.

---

## 5. M2 interfaces (decided — implement exactly these names and signatures)

### 5.1 backend/ingestion/config.py
- Best-effort load of backend/.env (python-dotenv in try/except; never crashes).
- Constants from env with defaults:
  GEMINI_API_KEY (""), GEMINI_MODEL ("gemini-2.5-flash"; if the API says the model doesn't exist,
  the agent picks the current Flash model from the API's model list and records it),
  GEMINI_TIMEOUT_S (30), CLONE_TIMEOUT_S (45), CLONE_DEPTH (50), FULL_CLONE_MAX_KB (20000),
  MAX_INDEXED_FILES (15), MAX_FILE_LINES (2000), MAX_REPO_PY_FILES (2000),
  SANDBOX_TIMEOUT_S (8), SANDBOX_OUTPUT_LIMIT (8000 chars),
  DEMO_REPO_URL ("https://github.com/shreyas-269/vivavoce-demo-repo"),
  DEMO_REPLAY (bool, env "1"), DEMO_RECORD (bool, env "1"),
  BACKEND_DIR, DEMO_CACHE_DIR (backend/demo_cache), REPLAY_DIR (backend/demo_cache/replay),
  WORK_DIR (a "vivavoce" folder inside the OS temp dir). All paths built from __file__.
- log = logging.getLogger("vivavoce.ingestion")

### 5.2 backend/ingestion/models.py (Pydantic v2; internal to M2, M1 maps them to schemas.py)
    class IngestionError(Exception): __init__(self, user_message: str, detail: str = "")
    class FunctionInfo:  name, qualname, kind ('function'|'async_function'|'method'),
                         args: list[str], docstring: str | None, line_start: int, line_end: int,
                         calls: list[str]
    class ConstantInfo:  name, value_repr (<= 80 chars), line: int
    class FileIndex:     path (posix, relative), line_count, import_count (how many indexed files
                         import it), imports: list[str], functions: list[FunctionInfo],
                         classes: list[str], constants: list[ConstantInfo], content: str
    class RepoIndex:     repo_id, source_url, local_path, commit_sha, files: list[FileIndex],
                         file_tree: list[str] (ALL .py paths, not just indexed), total_py_files,
                         truncated: bool, from_cache: bool, created_at: str (ISO)
        methods: get_file(path) -> FileIndex | None
                 identifiers(limit: int = 60) -> list[str]        # for M3's STT domain prompt
                 numbered_source(path, start=None, end=None) -> str  # "  12 | code" for M1's prompts
                 find_function(path, line) -> FunctionInfo | None
                 snap_range(path, start, end) -> tuple[str, int, int]
                     # M1's citation guard: unknown path -> best file's first function; range
                     # outside the file or outside any function -> nearest real function's range
    class OwnedSymbol:   file_path, symbol: str | None, line_start, line_end, lines_owned, share (0..1)
    class AuthorStat:    author, email, lines: int, share_of_lines: float (0..1)
    class PaperSection:  title, page_start, page_end, text
    class ConceptNode:   id ('N1'..'N8'), label, excerpt, section, page, excerpt_verified: bool
    class ConceptEdge:   source, target, label: str | None
    class PaperIndex:    paper_id (sha256 of bytes, first 16 hex), title, page_count,
                         sections: list[PaperSection], full_text, nodes, edges, mermaid: str,
                         excerpts: dict[str, str], source ('gemini'|'heuristic'|'cache')
    class SandboxResult: passed, stdout, stderr, runtime_ms: int, timed_out: bool,
                         tests_passed: int, tests_failed: int, error: str | None

### 5.3 backend/ingestion/repo_parser.py   (Python repos only — improvement plan P1-2.8)
    def validate_github_url(url: str) -> tuple[str, str]
        # only https://github.com/<owner>/<repo>(.git)(/) ; anything else -> IngestionError
    def clone_repo(github_url: str, dest_dir: str | None = None) -> str
        # git via subprocess; repos <= FULL_CLONE_MAX_KB (GitHub API size check, optional, skip on
        # failure) get a full clone, else --depth CLONE_DEPTH (P2-2.9); CLONE_TIMEOUT_S; no prompts
        # (GIT_TERMINAL_PROMPT=0); returns the local path
    def rank_python_files(repo_path: str) -> list[tuple[str, int, int]]
        # (path, line_count, import_count); skips .git, venv/.venv/env, node_modules, site-packages,
        # migrations, build/dist, __pycache__, files > MAX_FILE_LINES, symlinks; tests ranked last;
        # score = line_count + 40 * import_count
    def index_repo_path(repo_path: str, source_url: str = "local") -> RepoIndex
        # works on any local folder; keeps the top MAX_INDEXED_FILES; ast parse each (syntax
        # errors -> file kept with empty functions, never crash)
    def clone_and_index_repo(github_url: str, *, use_cache: bool = True) -> RepoIndex
        # demo URL + use_cache -> demo_loader (< 0.2 s); else validate, clone, index
    def cleanup_repo(path: str) -> None     # Windows-safe rmtree (read-only .git files)

### 5.4 backend/ingestion/git_blame.py   (improvement plan P1-2.7)
    def blame_file(repo_path: str, file_path: str) -> list[dict]
        # git blame --line-porcelain; each item {line, author, email, commit}
    def normalize_identity(name: str, email: str, alias_map: dict[str, str] | None = None) -> str
        # lower-cased email is the key; alias_map maps emails/names to one display name;
        # GitHub noreply emails "123+user@users.noreply.github.com" -> "user"
    def extract_author_map(repo_path: str, files: list[str], index: RepoIndex | None = None,
                           alias_map: dict[str, str] | None = None) -> dict[str, list[OwnedSymbol]]
        # author -> symbols they own (a function is owned by whoever wrote most of its lines;
        # lines outside functions grouped per file as symbol=None)
    def compute_authorship_stats(repo_path: str, files: list[str],
                                 alias_map: dict[str, str] | None = None) -> list[AuthorStat]
        # share_of_lines over all indexed lines, sorted descending, shares sum to 1.0
    def list_authors(author_map: dict[str, list[OwnedSymbol]]) -> list[str]

### 5.5 backend/ingestion/demo_loader.py
    def is_demo_source(url_or_name: str) -> bool        # DEMO_REPO_URL (any spelling) or "demo"
    def load_demo_repo() -> tuple[RepoIndex, dict[str, list[OwnedSymbol]], list[AuthorStat]]
        # from demo_cache JSON; from_cache=True; target < 0.2 s
    def materialize_demo_repo() -> str     # clones sample_repo.bundle into WORK_DIR (for sandbox / blame)
    def load_demo_challenge() -> dict      # {description, target_file, function, starter_code,
                                           #  test_code, reference_solution}
    (Paper caching lives in pdf_parser.py, not here, so the two lanes never edit the same file.)

### 5.6 backend/ingestion/pdf_parser.py   (improvement plan P1-2.5, P1-2.6)
    def extract_sections(pdf_bytes: bytes) -> tuple[str, int, list[PaperSection], str]
        # PyMuPDF (import fitz / pymupdf): title, page_count, sections (headings found by font
        # size/bold + numbered-heading regex; fallback one section per page), full_text
    def build_concept_graph(full_text: str, sections: list[PaperSection]) -> tuple[list[ConceptNode], list[ConceptEdge], str]
        # Gemini (google-genai SDK) with STRUCTURED OUTPUT: response_mime_type "application/json"
        # + a Pydantic response schema {nodes:[{id,label,excerpt,section}], edges:[{source,target,label}]};
        # 5–8 nodes N1..N8; one retry; then a heuristic fallback built from section headings
        # (methodology-like sections in order, chained edges). Returns source 'gemini'|'heuristic'.
        # The paper text is wrapped in <paper> … </paper> and the prompt says it is data, never
        # instructions (prompt-injection guard).
    def build_mermaid(nodes: list[ConceptNode], edges: list[ConceptEdge]) -> str
        # built IN CODE, never by the LLM: "flowchart TD", N1["label"], N1 --> N2, plus
        # "classDef active stroke-width:4px;". Labels sanitised (quotes, brackets, pipes,
        # newlines, length <= 40). Always valid.
    def verify_excerpt(excerpt: str, full_text: str) -> tuple[str, bool]
        # exact (whitespace-normalised) match -> (excerpt, True); else difflib fuzzy match over
        # the paper's sentences / 2-sentence windows -> (closest real text, False)
    def load_cached_paper(pdf_bytes: bytes) -> PaperIndex | None     # demo_cache/papers/<paper_id>.json
    def save_cached_paper(index: PaperIndex) -> None
    def parse_research_paper(pdf_bytes: bytes, *, use_gemini: bool = True, use_cache: bool = True) -> PaperIndex
        # cache hit -> source 'cache'; otherwise extract -> graph -> verify every excerpt ->
        # mermaid -> save to cache. Never raises on Gemini failure (heuristic); raises
        # IngestionError only for unreadable/empty PDFs.

### 5.7 backend/sandbox/sandbox_runner.py   (improvement plan P0-2.1, P0-2.2, P0-2.3)
    def execute_verification(file_path: str, student_code: str, test_code: str,
                             repo_root: str | None = None) -> SandboxResult
    async def execute_verification_async(...same args...) -> SandboxResult   # asyncio.to_thread
    def warm_up_sandbox() -> int     # runs one trivial pytest, returns ms; call at server start
Rules (all required):
- tempfile.TemporaryDirectory per run. If repo_root is given, copy every .py file under it
  (same skip rules as rank_python_files, max ~10 MB, no symlinks), keeping folders, so sibling
  imports work. Then write student_code over file_path (file_path must be relative, no "..",
  must stay inside the temp dir). Write test_code to test_vivavoce_challenge.py at the temp root.
- Write pytest.ini at the temp root: "[pytest]" + "pythonpath = ." (this is what makes imports
  work, because -I ignores PYTHONPATH).
- Command: [sys.executable, "-I", "-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider",
  "--noconftest", "test_vivavoce_challenge.py"], cwd = temp dir.
- env = a NEW minimal dict, never os.environ: PATH, SYSTEMROOT/WINDIR (Windows needs them),
  TEMP/TMP/HOME/USERPROFILE = temp dir, PYTHONDONTWRITEBYTECODE=1, PYTHONIOENCODING=utf-8.
  No API keys can reach student code.
- Timeout SANDBOX_TIMEOUT_S (8 s). On timeout kill the whole process tree (Windows: taskkill
  /T /F /PID) and return passed=False, timed_out=True.
- stdout/stderr truncated to SANDBOX_OUTPUT_LIMIT; parse "N passed / M failed" counts.
- Never raises; internal errors -> passed=False, error set.
- Wording everywhere (docs, logs, pitch notes): "sandboxed with a timeout", never "isolated".
  It does NOT stop student code reading files or using the network; say so in NOTES_FOR_TEAM.

### 5.8 backend/replay/  (improvement plan P0-2.4 — fully offline demo)
    store.py:
      class ReplayStore: __init__(self, replay_dir: str = REPLAY_DIR)
          record(method: str, path: str, status: int, body: dict) -> None
              # appends to session.jsonl; every "audio_base64" value is moved to an MP3 file in
              # replay/audio/ and replaced by "@audio:<file>"
          next(method: str, path: str) -> tuple[int, dict] | None   # rehydrates audio
          reset() -> None ; status() -> dict ; clear() -> None
          normalize_path(path) -> str   # /api/report/abc123 -> /api/report/{id}
    middleware.py:
      class ReplayMiddleware   # pure ASGI middleware (not BaseHTTPMiddleware)
          # inert unless DEMO_RECORD or DEMO_REPLAY is set; only touches /api/* JSON routes
          # DEMO_RECORD=1: passes requests through, records JSON responses
          # DEMO_REPLAY=1: never calls the app for /api/* except /api/replay/*; returns the next
          #   recorded response per (method, normalized path); none left -> 409 {error, detail}
          # also serves GET /api/replay/status and POST /api/replay/reset
    __init__.py: exports ReplayStore, ReplayMiddleware, is_replay_enabled(), is_record_enabled()
M1 adds one line: app.add_middleware(ReplayMiddleware). The real recording is made at
integration time on the merged app (record LAST, after everyone's P0 work).

### 5.9 backend/demo_cache/
- build_sample_repo.py  — deterministic script that creates the demo repo "studysync" (a small
  Python study-partner recommender, ~250 lines, 5–7 modules incl. a utils/ package) with 12–15
  commits by 3 FICTIONAL authors (Aman Verma, Priya Nair, Rohan Gupta; fixed emails and dates via
  GIT_AUTHOR_* / GIT_COMMITTER_* env vars) and ONE planted edge-case bug: cosine similarity in
  similarity.py divides by zero on an all-zero vector; similarity.py imports from utils/ (so the
  sandbox must copy siblings). Outputs:
    sample_repo.bundle (git bundle — a nested .git folder can't be committed),
    sample_repo_index.json, sample_repo_authors.json (author map + stats),
    sample_repo_challenge.json (description, target_file, function, starter_code = buggy file,
    test_code (pytest, includes the zero-vector edge case + normal cases), reference_solution).
- build_sample_paper.py + sample_paper.pdf — a generated 3–4 page fictional lab report (fpdf2),
  with clear numbered sections and a 6-stage method, so the paper demo has no licensing issues.
- papers/<paper_id>.json — cached PaperIndex for the sample paper.
- replay/ — recording folder (empty except a README until integration).

### 5.10 backend/ingestion/__init__.py and backend/sandbox/__init__.py
ingestion re-exports: clone_and_index_repo, index_repo_path, validate_github_url,
extract_author_map, compute_authorship_stats, list_authors, parse_research_paper,
is_demo_source, load_demo_repo, materialize_demo_repo, load_demo_challenge,
load_cached_paper, IngestionError,
RepoIndex, PaperIndex. sandbox re-exports: execute_verification, execute_verification_async,
warm_up_sandbox, SandboxResult. (Written once in S1; later tasks don't edit them except J1.)

### 5.11 Tests: backend/tests_m2/
One file per task (test_a1_clone.py, test_b1_sandbox.py, …). Run from backend/ with
"python -m pytest tests_m2 -q". conftest.py (written in S1) registers markers:
@pytest.mark.network (skipped unless M2_NETWORK_TESTS=1) and @pytest.mark.gemini (skipped
unless GEMINI_API_KEY is set).

---

## 6. Handoff file template (every build task writes docs/m2/handoffs/<TASK_ID>.md)

    # Handoff <TASK_ID> — <task name>
    ## Project in one paragraph            (VivaVoce + M2's role, 3–5 lines)
    ## How Shreyas works                   (the 11 rules of CONTEXT §2 in short form)
    ## What this task did
    ## Files created / changed             (M2-owned only, one line each)
    ## Public interface as implemented     (exact signatures; flag any difference from CONTEXT §5)
    ## How to test                         (test file + command + result; plain steps for Shreyas if he must act)
    ## Improvement-plan items covered      (e.g. P0-2.1 done / partly / not)
    ## Deviations from CONTEXT.md and why
    ## Requests for other members          (packages for requirements.txt, env vars, route code, fields)
    ## Known issues / TODO
    ## What the next task in this lane must know
    ## Review                              (left empty — filled by the Claude reviewer)

---

## 7. Definition of done for any task
- Acceptance criteria in TASKS.md met and actually tested (the task's pytest file passes).
- No file outside §3 modified (git status).
- Handoff file written.
- The agent's final message ends with: READY FOR REVIEW: <TASK_ID>
