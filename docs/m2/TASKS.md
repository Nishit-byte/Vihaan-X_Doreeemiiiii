# M2 INGESTION, SANDBOX & DEMO RELIABILITY — TASK LIST

S0 and S1 run first, one after the other (setup). Then two lanes run at the same time; inside a
lane, tasks run in order. Lanes never wait on each other until the join tasks. Each task = one
fresh build chat (Antigravity, Gemini 3.8 Flash) + one review session (Claude Code).

| ID | Lane | Task | Depends on | Review model | Improvement-plan items |
|----|------|------|-----------|--------------|------------------------|
| S0 | —    | M2 folder, repo, docs + scan | — | none | — |
| S1 | —    | Scaffold: packages, config, models, stubs, venv, test setup | S0 | Sonnet 5.5 | — |
| A1 | A    | Repo clone, URL validation, Python file ranking | S1 | Sonnet 5.5 | P1-2.8, P2-2.9 |
| A2 | A    | AST indexer + RepoIndex helpers (numbered source, snap_range, identifiers) | A1 | Sonnet 5.5 | supports P0-1.2, P1-3.5 |
| A3 | A    | git blame author map + authorship stats + identity merge | A2 | Sonnet 5.5 | P1-2.7 |
| A4 | A    | Demo repo "studysync": build script, bundle, planted bug, challenge | A3 | Sonnet 5.5 | demo cache |
| A5 | A    | Demo loader + cache wiring (< 0.2 s offline ingest) | A4 | Sonnet 5.5 | demo cache |
| B1 | B    | Sandbox core: key-safe env, -I, pytest.ini, 8 s timeout, tree kill | S1 | Opus 5.5 | P0-2.1, P0-2.3 |
| B2 | B    | Sandbox repo copy (sibling imports), async wrapper, warm-up | B1 | Sonnet 5.5 | P0-2.2, P0-2.3 |
| B3 | B    | PDF text + section extraction, sample lab-report PDF | B2 | Sonnet 5.5 | — |
| B4 | B    | Concept graph (Gemini structured JSON + heuristic) + Mermaid in code | B3 | Sonnet 5.5 | P1-2.5, P1-1.7 (guard) |
| B5 | B    | Excerpt verification + parse_research_paper + paper cache | B4 | Sonnet 5.5 | P1-2.6 |
| B6 | B    | Replay mode: store + ASGI middleware (record / replay) | B5 | Opus 5.5 | P0-2.4 (infrastructure) |
| J1 | Join | End-to-end run, dev_cli, NOTES_FOR_TEAM.md | A5, B6 | Sonnet 5.5 | all |
| J2 | Join | Final readiness review (Claude only) | J1 | Opus 5.5 | all |
| J3 | Join | Port into the team repo + pull request | J2 + team repo access | Sonnet 5.5 | — |

Note on lane B order: B1→B2 (sandbox) and B3→B4→B5 (paper) are both in lane B and run in the
order listed: B1, B2, B3, B4, B5, B6.

---

## S0 — M2 folder, repo, docs + scan
Create the M2 folder (sibling of the M3 project folder), the private GitHub repo
shreyas-269/vivavoce-m2, .gitignore, docs/m2/ (CONTEXT, TASKS, STATUS, handoffs/), scan for any
existing M2 code and write docs/m2/REPO_STATE.md, first commit + push.

## S1 — Scaffold
Description: Create every M2 package with stub modules that already have the exact names and
signatures of CONTEXT §5 (stubs raise NotImplementedError or return safe empty values), fully
implement config.py (§5.1) and models.py (§5.2 — real Pydantic models with the RepoIndex methods
left as stubs), write both __init__.py files (§5.10), the tests_m2/conftest.py markers (§5.11),
and set up backend/.venv with: pymupdf, google-genai, pydantic, fastapi, httpx, pytest,
python-dotenv, fpdf2. Create backend/.env with placeholder GEMINI_API_KEY= if missing.
Acceptance: from backend/, "python -c "import ingestion, sandbox, replay; print('ok')"" works;
"python -m pytest tests_m2 -q" runs (0 tests is fine); a test file test_s1_scaffold.py checks
every public name exists with the right signature (inspect.signature).

---

## LANE A — REPO INTELLIGENCE

### A1 — Repo clone, URL validation, Python file ranking
Description: Implement validate_github_url, clone_repo, rank_python_files, cleanup_repo (§5.3).
Details:
- URL rules: only https://github.com/<owner>/<repo> with optional .git or trailing slash; reject
  ssh, file://, other hosts, paths with extra segments, empty owner/repo -> IngestionError with a
  friendly user_message.
- clone via subprocess git with env GIT_TERMINAL_PROMPT=0, timeout CLONE_TIMEOUT_S; optional size
  check with GET https://api.github.com/repos/<o>/<r> (size in KB, no auth; any failure -> shallow
  clone); full clone if size <= FULL_CLONE_MAX_KB else --depth CLONE_DEPTH. Clone into a unique
  folder under WORK_DIR. Clone failures (404, private, timeout) -> IngestionError.
- Python only (P1-2.8). Skip rules from §5.3. import_count: parse imports with ast and count how
  many OTHER repo files import each module (handle "from pkg.mod import x", "import pkg.mod",
  relative imports).
- cleanup_repo must delete read-only .git files on Windows (onerror/onexc handler).
Tests (test_a1_clone.py): URL validation table; ranking on a small fixture repo created in
tmp_path (a package with cross-imports, a venv folder, a huge file, a tests/ folder);
@network test cloning a tiny public repo and cleaning it up.
Acceptance: tests pass (network test run once with M2_NETWORK_TESTS=1 and result in handoff).

### A2 — AST indexer + RepoIndex helpers
Description: Implement index_repo_path and clone_and_index_repo (without the demo cache yet —
use_cache is accepted and ignored until A5), plus the RepoIndex methods in models.py.
Details:
- ast extraction per file: functions and async functions (top-level and methods, qualname
  Class.method, nested functions included with qualname outer.inner), args (incl. *args,
  **kwargs, kw-only), docstring (first 300 chars), line_start/line_end (lineno/end_lineno;
  include decorators in line_start), calls (names of called functions, deduped, max 30),
  classes, module-level UPPER_CASE constants (value_repr via ast.unparse, <= 80 chars), imports.
- file_tree = every .py path (posix, sorted), not just the indexed top files; truncated=True if
  the repo had more than MAX_INDEXED_FILES candidates. commit_sha via git rev-parse HEAD
  ("" if not a git repo). repo_id = short hash of url + sha.
- numbered_source: right-aligned line numbers "  12 | code"; start/end optional, clamped.
- snap_range rules (§5.2): exact containment in a function -> unchanged; partly outside -> clamp
  to that function; outside any function -> nearest function by distance; unknown path -> the
  highest-ranked file's first function. Never returns a range outside the file.
- identifiers: function names, class names, constants and module names, most important first,
  deduped, limit.
- Files with syntax errors are kept (content + line_count) with empty functions.
Tests (test_a2_index.py): fixture repo with classes, nested and async functions, decorators,
constants, a syntax-error file; numbered_source; snap_range for all four rules; identifiers.
Acceptance: tests pass; indexing a ~15-file repo takes under 1 s (time it, record in handoff).

### A3 — git blame author map + authorship stats
Description: Implement git_blame.py (§5.4).
Details:
- git blame --line-porcelain -w per file (subprocess, timeout per file 10 s); parse author,
  author-mail (strip <>), commit, final line number. Uncommitted lines ("Not Committed Yet")
  skipped.
- normalize_identity: lower-cased email key; GitHub noreply -> username; alias_map applied to
  both name and email; display name = most frequent spelling for that key.
- extract_author_map: function owner = author with most lines in its range (ties -> earliest
  line); share = owner's lines / function lines; lines outside functions grouped per file (symbol None).
  If index is None, index the files with A2 to get function ranges.
- compute_authorship_stats: shares over all indexed lines, sorted desc, sum to 1.0 (+-0.001).
- Shallow clones: note in docstring that boundary commits absorb older history (P2-2.9).
Tests (test_a3_blame.py): build a fixture git repo in tmp_path with 3 authors (one author using
two spellings + two emails merged by alias_map, one noreply email), commits with fixed authors
via env vars; check map, ownership, shares, list_authors order.
Acceptance: tests pass on Windows (git available).

### A4 — Demo repo "studysync": build script, bundle, planted bug, challenge
Description: Write backend/demo_cache/build_sample_repo.py (§5.9) and run it to produce the
committed outputs.
Details:
- Deterministic: running it twice produces the same files/commit graph (fixed dates and authors,
  sorted writes). It builds the repo in a temp folder, then writes sample_repo.bundle
  ("git bundle create ... --all"), sample_repo_index.json (A2's RepoIndex, local_path blanked,
  source_url = DEMO_REPO_URL), sample_repo_authors.json (A3's author map + stats), and
  sample_repo_challenge.json.
- Content: realistic, readable code with docstrings (it is what the examiner quizzes on):
  e.g. models.py (Student dataclass), similarity.py (cosine_similarity, jaccard), ranking.py
  (top_k_partners), data_loader.py (load CSV), utils/vector_ops.py (dot, norm), utils/__init__.py,
  cli.py. Author split roughly Aman 50%, Priya 30%, Rohan 20% so the "wrote it vs understands it"
  pitch works.
- Planted bug: cosine_similarity (similarity.py, imports norm/dot from utils.vector_ops) raises
  ZeroDivisionError on an all-zero vector. challenge.test_code: 4–6 pytest tests incl. zero
  vectors (expected 0.0) and normal cases. reference_solution = fixed file.
- Check: run the challenge's tests against the buggy file (must FAIL) and the reference (must
  PASS) using a plain pytest run in a temp copy (the real sandbox is lane B's; don't import it).
- Optional, ask Shreyas first: create the PUBLIC repo shreyas-269/vivavoce-demo-repo from the
  bundle (gh if available) so the live demo can also clone it.
Tests (test_a4_demo_repo.py): bundle exists and clones; index JSON loads into RepoIndex; author
shares roughly as planned; challenge fails on starter and passes on reference.
Acceptance: outputs committed-size reasonable (bundle < 200 KB); tests pass.

### A5 — Demo loader + cache wiring
Description: Implement demo_loader.py (§5.5) and wire it into clone_and_index_repo(use_cache=True).
Details: is_demo_source accepts DEMO_REPO_URL with/without .git, trailing slash, any case, and
"demo"; load_demo_repo parses the JSON files (cache parsed objects in memory after first load);
materialize_demo_repo clones the bundle into WORK_DIR once per process (reuses it if present)
and sets RepoIndex.local_path; load_demo_challenge. Offline: nothing in this path touches the
network.
Tests (test_a5_demo_loader.py): load time < 0.2 s (after import, measure), from_cache True,
clone_and_index_repo(DEMO_REPO_URL) never calls git clone over the network (monkeypatch
clone_repo to fail), materialize works twice.
Acceptance: tests pass; handoff records the measured load time.

---

## LANE B — EXECUTION, PAPERS & REPLAY

### B1 — Sandbox core
Description: Implement execute_verification without repo copying yet (repo_root=None path) with
every security/robustness rule in §5.7.
Details: minimal env dict, -I, pytest.ini pythonpath, --noconftest, -p no:cacheprovider,
SANDBOX_TIMEOUT_S, process-tree kill on Windows (Popen + communicate(timeout) + taskkill /T /F),
output truncation, pass/fail count parsing (also handle "no tests ran", collection errors, syntax
errors in student code), never raises, runtime_ms.
Tests (test_b1_sandbox.py):
- KEY LEAK: set fake GEMINI_API_KEY/GROQ_API_KEY/SECRET_TOKEN in the parent os.environ; test_code
  prints os.environ and asserts none of them is present -> result passed=True and stdout/stderr
  contain none of the fake values (P0-2.1 "done when").
- passing test, failing test, syntax error in student code, infinite loop (timed_out=True,
  returns within ~SANDBOX_TIMEOUT_S + 2 s), a child process spawned by student code that would
  outlive the timeout is killed, huge output truncated, file_path with ".." rejected.
Acceptance: all tests pass on Windows; handoff states plainly what the sandbox does NOT protect
against (file reads, network).

### B2 — Sandbox repo copy, async wrapper, warm-up
Description: Add the repo_root path (copy siblings, overwrite target), execute_verification_async,
warm_up_sandbox (§5.7).
Details: copy rules = same skip rules as A1's ranking (re-implement locally in sandbox_runner.py,
do NOT import lane A code), size cap ~10 MB, preserve folders, ensure package __init__.py files
come along; target path must exist in the repo OR be a new file inside it; overwrite with
student_code. warm_up_sandbox returns ms and never raises. Cold vs warm timing recorded.
Tests (test_b2_sandbox_repo.py): fixture repo in tmp_path where pkg/core.py imports
pkg/utils/helpers.py; a correct fix passes, a wrong fix fails (P0-2.2 "done when"); target
outside repo rejected; async wrapper works inside an event loop; warm-up < 8 s.
Acceptance: tests pass; cold/warm ms in handoff.

### B3 — PDF text + section extraction, sample paper
Description: Implement extract_sections (§5.6) and create the sample paper.
Details:
- build_sample_paper.py (fpdf2) generates backend/demo_cache/sample_paper.pdf: a fictional 3–4
  page lab report, e.g. "Adaptive Spaced Repetition with Peer Matching", with Abstract,
  1 Introduction, 2 Method (2.1–2.6: six clear stages), 3 Evaluation, 4 Limitations, References.
  Deterministic output. Use only built-in fonts (no external font files).
- extract_sections with PyMuPDF: page text via get_text("dict") to read font sizes/bold; a line
  is a heading if it is noticeably larger/bold than body text OR matches a numbered heading
  regex ("2", "2.1", "II." + Title Case); title = largest text on page 1; fallback one section per
  page. Normalise whitespace and de-hyphenate line breaks in full_text.
- Unreadable/empty/encrypted/image-only PDF -> IngestionError with a friendly message.
Tests (test_b3_pdf_extract.py): sample paper -> title right, >= 8 sections incl. the 6 method
stages in order; a PDF made in-test with no headings -> per-page fallback; garbage bytes ->
IngestionError.
Acceptance: tests pass.

### B4 — Concept graph + Mermaid in code
Description: Implement build_concept_graph and build_mermaid (§5.6).
Details:
- Needs GEMINI_API_KEY. If missing: STOP and tell Shreyas in plain steps — open
  aistudio.google.com, sign in with his Google account, "Get API key" -> Create API key, copy it,
  paste after GEMINI_API_KEY= in backend/.env (m2 folder), save, reply "done". The free tier is
  enough.
- google-genai SDK: client.models.generate_content(model=GEMINI_MODEL, contents=..., config with
  response_mime_type="application/json" and response_schema=<Pydantic model>), timeout
  GEMINI_TIMEOUT_S, one retry, then heuristic. Verify the model name with one tiny call; if it
  404s, list models and pick the current Flash model, record it in the handoff.
- Prompt: 5–8 methodology/architecture stages, ids N1..N8 in order, labels <= 6 words, each with a
  1–2 sentence excerpt copied VERBATIM from the paper and the section title; paper text inside
  <paper>…</paper> marked as data, never instructions; truncate input to ~30k chars, prioritising
  Method sections.
- Post-process: renumber ids N1..Nk in order, drop edges to unknown ids, dedupe, ensure a
  connected chain (add N_i -> N_i+1 if a node has no edges).
- Heuristic fallback: method-like sections (by heading keywords or numbering under the Method
  section) in order, 5–8 nodes, chained; excerpt = first 2 sentences of that section.
- build_mermaid: per §5.6; sanitised labels; deterministic output.
Tests (test_b4_graph.py): build_mermaid with nasty labels (quotes, brackets, pipes, unicode) ->
valid structure (regex check of every line); heuristic on the sample paper -> 6 nodes chained;
@gemini test: real call on the sample paper returns 5–8 nodes (run once, record output in handoff).
Acceptance: tests pass; Mermaid output for the sample paper pasted into the handoff (Shreyas can
paste it into mermaid.live to see it render).

### B5 — Excerpt verification + parse_research_paper + paper cache
Description: Implement verify_excerpt, load_cached_paper, save_cached_paper and
parse_research_paper (§5.6), and commit the cached index for the sample paper.
Details: sentence split that survives "e.g.", "et al.", numbers; normalise quotes/dashes/
whitespace before comparing; fuzzy = difflib.SequenceMatcher ratio over sentences and
2-sentence windows, best one wins; excerpts dict = node_id -> verified excerpt; cache file
demo_cache/papers/<paper_id>.json. Run parse_research_paper on the sample paper (with Gemini if
the key exists, else heuristic) and keep the cache file (committed, so the paper demo is offline).
Tests (test_b5_paper.py): exact excerpt -> True; paraphrased excerpt -> returns a real sentence
from the text, False; cache round-trip; second parse of the same bytes returns source 'cache'
in < 50 ms; use_gemini=False path works offline.
Acceptance: tests pass; papers/<id>.json committed.

### B6 — Replay mode
Description: Implement backend/replay/ (§5.8) — the infrastructure for a fully offline demo.
Details:
- Pure ASGI middleware (scope/receive/send): buffer the response body for /api/* JSON responses
  while recording; never break streaming/non-JSON responses (pass them through untouched); in
  replay mode don't call the downstream app for /api/* (except /api/replay/*).
- Ordering is per (method, normalized path) queue; a cursor file or in-memory cursor with reset.
- Audio extraction: any key named audio_base64 at any depth (dicts/lists) -> MP3 file, restored
  on replay.
- Status endpoint: {mode, recorded_calls, remaining per route}.
- Thread/async safety: an asyncio.Lock around store writes.
- README in demo_cache/replay/ explaining how to record at integration (start the merged server
  with DEMO_RECORD=1, do the scripted viva once, stop; then DEMO_REPLAY=1 with Wi-Fi off).
Tests (test_b6_replay.py): a toy FastAPI app built inside the test (routes /api/ingest-repo,
/api/viva/turn returning audio_base64, /api/report/{id}) + TestClient: record a 5-call session,
then replay it with the toy app's handlers replaced by functions that raise (proves no app/API
calls), responses identical incl. audio; 409 when exhausted; reset works; non-/api routes and
inert mode untouched.
Acceptance: tests pass; README written.

---

## JOIN TASKS

### J1 — End-to-end run, dev_cli, NOTES_FOR_TEAM.md
Description: Prove the whole M2 pipeline works together and write the integration notes.
Details:
- backend/ingestion/dev_cli.py: "python -m ingestion.dev_cli repo <url|demo>" (prints index
  summary, top files, authors + shares, timing), "pdf <path>" (title, sections, nodes, mermaid),
  "challenge demo" (runs the demo challenge through the REAL sandbox with repo_root =
  materialize_demo_repo(): starter must fail, reference must pass), "sandbox-leak" (runs the key
  leak check), "replay-status".
- End-to-end test tests_m2/test_j1_end_to_end.py covering exactly those flows offline.
- Live check (network): clone + index one small real public Python repo; if the demo repo was
  published, clone it live too.
- Update __init__.py exports if anything changed; fill the M2 sections of docs/m2/NOTES_FOR_TEAM.md:
  For M1 — packages for requirements.txt, env vars for .env.example, the exact route code for
  /api/ingest-repo, /api/ingest-pdf, /api/run-code (incl. repo_root from the session and
  execute_verification_async), startup (warm_up_sandbox, ReplayMiddleware), how to use
  numbered_source + snap_range (P0-1.2) and identifiers() (for M3's domain_terms), IngestionError
  -> {error, detail}, proposed IngestResponse fields (file_tree + contents, authors, authorship,
  mermaid, nodes, excerpts), RunCodeResponse mapping from SandboxResult, and the replay recording
  procedure. For M4 — shapes of file tree/contents, Mermaid + node ids (+ classDef active),
  excerpts, authors list. For M3 — identifiers(). For the pitch — "sandboxed with a timeout",
  "Python repos", what the sandbox doesn't protect against. Collect every "Requests for other
  members" from handoffs S1–B6. End with a short ready-to-send team message.
- If docs/m2/SCHEMAS_FROM_M1.md exists, align the notes (and any small mapping helpers) to it.
Acceptance: test_j1 passes; dev_cli outputs pasted into the handoff; notes complete.

### J2 — Final readiness review (Claude Code, Opus 5.5)
Whole-workstream review: ownership, full test run, security of the sandbox, Windows behaviour,
demo-day failure modes (no Wi-Fi, no Gemini key, rate limits, giant repo, private repo, weird
PDF), the improvement-plan checklist for M2, and a merge checklist. No Gemini build step.

### J3 — Port into the team repo + pull request
When Shreyas has access to github.com/Nishit-byte/Vihaan: clone it next to the M2 folder,
branch m2-ingestion, copy the M2 paths 1:1 (stop on any non-stub conflict), align to the real
schemas.py, run the tests there, then the reviewer commits, pushes and opens a PR.
