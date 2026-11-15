# M2 FINAL READINESS REVIEW (J2)

**Reviewer:** Claude Code (Opus 5.5) · **Date:** 2026-11-15 · **Scope:** S1, A1–A5, B1–B6, J1 at `9c0e2c7` + J2 fixes (uncommitted)

## Verdict: **READY WITH FIXES**

> **Status update (2026-11-15):** FIX PROMPT 3 has been **applied** in the M2 repo and re-verified
> (164 passed / 2 skipped; `dev_cli sandbox-leak` prints the new honest verdict). The reviewer also
> corrected one NOTES sentence (the `config.py` default is still `gemini-2.5-flash`, and the 3.8 fallback is automatic).
> The J2 fixes + FIX PROMPT 3 are committed as `m2(J2): final readiness review and hardening fixes`.
> **FIX PROMPTS 1–2 are queued for J3:** they change the team repo (`main.py` adapter, merge rules)
> and can't be applied here. The M2 repo itself is ready to port; the port must follow FIX PROMPT 2,
> not a 1:1 copy.

M2's own code is solid. The full suite passes (164 passed / 2 skipped offline; **166 passed / 0 skipped** with
`M2_NETWORK_TESTS=1`), all 5 `dev_cli` commands exit 0, and the sandbox survived every adversarial probe
J2 threw at it. **But M2 cannot be ported "1:1" into the team repo, and the integration notes were wrong
in a way that breaks the demo.** The team's real `main.py` (Nishit-byte/Vihaan @ `9f4a547`) already calls M2,
but under its launch command (`uvicorn backend.main:app`) every M2 module fails to import. Its wrappers also
expect M1 schema types and swallow every exception into a mock fallback. Nothing would crash: the demo
would just quietly run on mock data. FIX PROMPTS 1–2 below close this in J3; FIX PROMPT 1's adapter code
was executed by J2 against the real team `schemas.py`, and it works.

---

## 1. Blockers (must be fixed before/during J3)

| # | Blocker | Evidence | Fix |
|---|---------|----------|-----|
| B1 | **M2 packages don't import under the team's launch command.** README runs `uvicorn backend.main:app` from the project root, so only the project root is on `sys.path`. M2 imports `from ingestion.config import …` (top-level), which fails with `ModuleNotFoundError: No module named 'ingestion'`. `main.py`'s `_invoke_m2_*` wrappers catch it with `except Exception: pass` and silently serve `_mock_repo_index` / `_mock_paper_index` / the built-in fallback runner. | J2 import probe: `backend.ingestion.repo_parser`, `backend.ingestion.pdf_parser`, `backend.sandbox.sandbox_runner`, `backend.replay` all FAIL from project root. | FIX PROMPT 1 step 1 (one `sys.path` line in `main.py`) |
| B2 | **Team `main.py` wrappers are incompatible with M2's return types.** `_invoke_m2_repo_ingestion` reads `repo_index.author_map` (M2 `RepoIndex` has none, so AttributeError, so mock). `use_demo_cache=True` *always* returns the mock. `ingest_pdf` reads `.mermaid_graph` / `.breakdown` (M2 has `.mermaid`). `run_code` returns M2's `SandboxResult` where a `RunCodeResponse` is expected. `_invoke_m2_sandbox` passes **no `repo_root`**, so the demo's `similarity.py` can't import `utils.vector_ops` and the correct fix fails. All three M2 calls are synchronous inside `async def` routes. | Read of team `backend/main.py` lines 326–420, 596–700, 905–1000. | FIX PROMPT 1 (adapter, J2-verified) |
| B3 | **A 1:1 copy would delete team code that is still used.** Team `backend/sandbox/sandbox_runner.py` holds `execute_multi_language_sandbox` (OA/LeetCode mode in `/api/run-code`). Team `pdf_parser.py` has `load_demo_paper_bytes`, team `repo_parser.py` has `load_demo_repo_index`, team `ingestion/__init__.py` exports both, and `leetcode_parser.py` / `paper_breakdown.py` live in M2's folders. | `git show HEAD:` of those files in the team repo. | FIX PROMPT 2 (merge rules for J3) |
| B4 | ~~NOTES route code broke the demo's L4 fix~~ **fixed by J2.** Following §1.5 verbatim, `load_demo_repo()` leaves `local_path=""`, so `/api/run-code` gets `repo_root=""` and the **reference solution returned "Wrong Answer"**. Blocking calls were also not threaded. | J2 ran the §1.3–1.5 snippets against M2 + team `schemas.py` with TestClient: before, *Wrong Answer*; after the fix, *Accepted*. | Done in NOTES (§1.4, §1.5, new §1.8) |

## 2. Non-blocking findings

**Security (sandbox: "sandboxed with a timeout")**
1. **Student code CAN read the Gemini key from disk.** `Path(sys.prefix).parent / ".env"` is `backend/.env` (the venv lives in `backend/`). J2 probe T1 read it (key length 53; the value was never printed). Walking up from the sandbox cwd finds nothing (T2); walking up from any `sys.path` entry does (T2b). This is the documented same-user limit (CONTEXT §5.7, NOTES §4), so it is not a blocker. Still, **use a throwaway, quota-limited key for the demo and rotate it afterward.**
2. **Ancestor-environment read via psutil still leaks the key** (T3). Both M2's `config.py` and the team's `main.py` call `load_dotenv()`, which puts the key in the server's `os.environ`. Same-user memory reads make this unfixable in-process anyway; it's documented.
3. **Outbound network is open** (T6). Documented.
4. **Forged pass** via printing "1 passed" + `os._exit(0)` (B1 review #6). Documented.
5. **New in J2:** Job object now caps a run at **32 processes and 1 GB** (Windows). Before this, a fork bomb could spawn until the 8 s kill and freeze the demo laptop. POSIX (macOS/Linux) has the timeout + `killpg` but **no process/memory caps**.
6. Wording: `backend/sandbox/__init__.py` said "isolated test runner", and NOTES §4 said "Module isolation" with a false claim that imports are confined to the copied repo. **Both fixed.** Note: the team `main.py` docstrings say "isolated 4s pytest"; M1 should reword, and the M2 timeout is 8 s.

**Robustness**

7. **Fixed:** one pathological `.py` file (e.g. a 200k-term expression) made `index_repo_path` raise a raw `RecursionError` → HTTP 500. A2's hardening covered `_parse_python_file` but not the `ast.parse` in `rank_python_files`.
8. **Fixed:** a non-Python repo "succeeded" with 0 files and no error. `clone_and_index_repo` now raises `IngestionError("This repository has no Python files…")` and deletes the clone (P1-2.8).
9. **Fixed:** `parse_research_paper` raised `OSError` if the paper cache couldn't be written. It now logs and continues.
10. **Gemini never produced a real `source='gemini'` result in this repo.** Live J2 call: `gemini-2.5-flash` gives **404** ("no longer available to new users"), then `gemini-3.8-flash` gives **429 RESOURCE_EXHAUSTED**, then the heuristic in 2.3 s. The `@gemini` tests pass because they accept the fallback. Every fresh (non-cached) PDF currently gets the heading heuristic. Set `GEMINI_MODEL=gemini-3.8-flash`, check the quota, and consider `GEMINI_TIMEOUT_S=15` (a hung API costs about 2 × timeout + 1 s before fallback).
11. git blame runs **twice** per ingest (`extract_author_map` and `compute_authorship_stats` each blame every file). Real repos pay double (psf/requests took 10.6 s total in J1).
12. Clones in `%TEMP%\vivavoce\` are never deleted (`cleanup_repo` is not exported or called). The disk grows over a long demo day.
13. Every uploaded PDF's index is written into `backend/demo_cache/papers/`, which creates untracked files in git. Don't commit judges' papers. There is also no upload size or page cap; M1 should reject anything over ~20 MB.
14. Replay: any **non-JSON** `/api/*` route returns **409** in replay mode, and WebSocket traffic passes through to the live app. Before recording, confirm that every `/api/*` call the frontend makes in the scripted viva is JSON.
15. `materialize_demo_repo()` can race on the very first concurrent call (two `git clone`s into one folder). Call it once at startup.
16. Some `IngestionError.user_message`s embed internal text (e.g. "Unreadable PDF document: Failed to open stream"). Cosmetic.
17. `dev_cli sandbox-leak` prints "Zero secrets leaked", but it only proves the child **env dict** is clean. Don't show it to judges as proof that keys are unreachable.
18. S1's handoff lists `DEMO_REPLAY=1` / `DEMO_RECORD=1` for `.env.example`; NOTES (`=0`) is correct.

## 3. Reviewer fixes applied in J2 (uncommitted, about 18 code lines + docs)

| File | Change |
|------|--------|
| `backend/ingestion/repo_parser.py` | `rank_python_files`: catch `(SyntaxError, ValueError, RecursionError, MemoryError)` from `ast.parse`; `clone_and_index_repo`: 0 indexable `.py` files → cleanup + `IngestionError` |
| `backend/ingestion/pdf_parser.py` | `save_cached_paper` failure logged, never raised |
| `backend/sandbox/sandbox_runner.py` | Job object: `JOB_OBJECT_LIMIT_ACTIVE_PROCESS` (32) + `JOB_OBJECT_LIMIT_JOB_MEMORY` (1 GB) |
| `backend/sandbox/__init__.py` | docstring wording: "isolated" → "sandboxed with a timeout" |
| `docs/m2/NOTES_FOR_TEAM.md` | §1.4 `error` = `exc.user_message`; §1.5 demo branch materializes the bundle + `asyncio.to_thread` everywhere; §4 "Module isolation" corrected; new §1.8 (blocking-call table + warning that §1.5 predates the real `main.py`) |

Re-verified after the fixes: `pytest tests_m2 -q` → 164 passed / 2 skipped; `dev_cli challenge demo` → starter FAIL, reference PASS; probes T7 (unbounded spawn: stopped at 18 children by `OSError`, 0 survivors), T8 (1.5 GB allocation → `MemoryError`), T9 (normal 2M-element test passes); the corrected NOTES routes return *Accepted* for the reference fix.

---

## 4. FIX PROMPTS

### FIX PROMPT 1: J3 adapter for the team `backend/main.py` (M1-owned file; apply only during J3, with Nishit's OK)

```text
You are working in the VivaVoce TEAM repo (github.com/Nishit-byte/Vihaan), file backend/main.py
(owned by M1/Nishit; you have his OK for this change during task J3). M2's modules have just been
merged into backend/ingestion, backend/sandbox and backend/replay. M2 code imports itself with
TOP-LEVEL names (ingestion, sandbox, replay), not backend.ingestion. Make exactly these changes:

1. Right after the existing PROJECT_ROOT sys.path block near the top, add:
       BACKEND_DIR = str(Path(__file__).resolve().parent)
       if BACKEND_DIR not in sys.path:
           sys.path.insert(0, BACKEND_DIR)  # M2 packages use top-level imports
   Then add these imports (top-level names ONLY; never import backend.ingestion.models,
   it would create a second, different IngestionError class):
       import asyncio
       from fastapi.responses import JSONResponse
       import ingestion as m2_ingestion
       import sandbox as m2_sandbox
       from ingestion import IngestionError
       from replay import ReplayMiddleware

2. Middleware order: add `app.add_middleware(ReplayMiddleware)` on the line BEFORE the existing
   `app.add_middleware(CORSMiddleware, ...)` (Starlette makes the last-added outermost; CORS must
   be outermost or replayed responses lose CORS headers).

3. In the existing lifespan(), before `yield`, add:
       await asyncio.to_thread(m2_sandbox.warm_up_sandbox)
       try:
           await asyncio.to_thread(m2_ingestion.materialize_demo_repo)
       except Exception:
           pass

4. Add an exception handler after `app = FastAPI(...)`:
       @app.exception_handler(IngestionError)
       async def _m2_ingestion_error(request: Request, exc: IngestionError):
           return JSONResponse(status_code=400,
                               content={"error": exc.user_message, "detail": exc.detail})

5. Replace the three functions _invoke_m2_repo_ingestion, _invoke_m2_pdf_ingestion and
   _invoke_m2_sandbox ENTIRELY with the code below (keep _mock_repo_index/_mock_paper_index in the
   file, unused). This code was executed against this repo's schemas.py by the M2 J2 review:
   demo repo -> 7 files/21 symbols/3 authors, starter "Wrong Answer" 4/6, reference "Accepted" 6/6,
   sample paper -> 6 nodes, garbage PDF -> IngestionError.

M2_REPO_INDEXES: Dict[str, Any] = {}  # github_url -> M2 RepoIndex (snap_range, numbered_source, identifiers)


def _m2_repo_to_schema(idx, author_map, stats) -> RepoIndex:
    symbols = [
        ASTFunctionSymbol(
            name=fn.qualname, file_path=f.path, line_start=fn.line_start, line_end=fn.line_end,
            args=fn.args, docstring=fn.docstring, calls=fn.calls,
            code_snippet=idx.numbered_source(f.path, fn.line_start, fn.line_end),
        )
        for f in idx.files for fn in f.functions
    ]
    name = idx.source_url.rstrip("/").split("/")[-1]
    return RepoIndex(
        repo_name=(name[:-4] if name.endswith(".git") else name) or idx.repo_id,
        github_url=idx.source_url,
        local_path=idx.local_path or None,
        files=[RepoFile(path=f.path, content=f.content, line_count=f.line_count) for f in idx.files],
        symbols=symbols,
        authors=[s.author for s in stats],
        author_map={
            a: [OwnedSymbol(file_path=s.file_path, line_start=s.line_start, line_end=s.line_end,
                            symbol_name=s.symbol) for s in syms]
            for a, syms in author_map.items()
        },
        summary=f"{idx.total_py_files} Python files ({len(idx.files)} indexed), commit {idx.commit_sha[:7]}",
    )


def _invoke_m2_repo_ingestion(github_url: str, use_demo_cache: bool = False) -> RepoIndex:
    if use_demo_cache or m2_ingestion.is_demo_source(github_url):
        idx, author_map, stats = m2_ingestion.load_demo_repo()
        idx.local_path = m2_ingestion.materialize_demo_repo()  # sandbox needs the real files
    else:
        idx = m2_ingestion.clone_and_index_repo(github_url, use_cache=False)  # raises IngestionError
        paths = [f.path for f in idx.files]
        author_map = m2_ingestion.extract_author_map(idx.local_path, paths, index=idx)
        stats = m2_ingestion.compute_authorship_stats(idx.local_path, paths)
    M2_REPO_INDEXES[idx.source_url] = idx
    return _m2_repo_to_schema(idx, author_map, stats)


def _invoke_m2_pdf_ingestion(pdf_bytes: bytes, filename: str) -> PaperIndex:
    if not pdf_bytes:
        pdf_bytes = (Path(m2_ingestion.__file__).resolve().parent.parent / "demo_cache" / "sample_paper.pdf").read_bytes()
    p = m2_ingestion.parse_research_paper(pdf_bytes)  # raises IngestionError on unreadable PDFs
    nodes = [PaperNode(node_id=n.id, label=n.label, section=n.section or None, page=max(1, n.page),
                       excerpt=n.excerpt) for n in p.nodes]
    return PaperIndex(title=p.title, mermaid_graph=p.mermaid, nodes=nodes,
                      node_excerpts=dict(p.excerpts), full_text_summary=p.full_text[:2000])


def _invoke_m2_sandbox(file_path: str, student_code: str, test_code: str, repo_root=None) -> RunCodeResponse:
    r = m2_sandbox.execute_verification(file_path, student_code, test_code, repo_root=repo_root)
    verdict = "Time Limit Exceeded" if r.timed_out else ("Accepted" if r.passed else "Wrong Answer")
    return RunCodeResponse(passed=r.passed, verdict=verdict, stdout=r.stdout,
                           stderr=r.stderr if not r.error else f"{r.stderr}\n{r.error}".strip(),
                           runtime_ms=r.runtime_ms, total_cases=r.tests_passed + r.tests_failed,
                           passed_cases=r.tests_passed)

6. Call sites (all three are inside `async def` routes, so they must not block the event loop):
   - ingest_repo:  repo_index = await asyncio.to_thread(_invoke_m2_repo_ingestion,
                        req.github_url.strip(), req.use_demo_cache)
   - ingest_pdf:   paper_index = await asyncio.to_thread(_invoke_m2_pdf_ingestion, pdf_bytes, filename)
   - run_code (the pytest branch, NOT the execute_multi_language_sandbox branch):
         repo_root = session.repo_index.local_path if (session and session.repo_index) else None
         result = await asyncio.to_thread(_invoke_m2_sandbox, req.file_path or "main.py",
                                          source, effective_test_code or "", repo_root)
     Also wrap the execute_multi_language_sandbox(...) call in `await asyncio.to_thread(...)`.

7. In viva_turn, the STT domain terms: if session.repo_index and
   M2_REPO_INDEXES.get(session.repo_index.github_url) exists, use
   ", ".join(M2_REPO_INDEXES[...].identifiers(30)) instead of the symbols[:20] names.

8. Reword docstrings/comments that say "isolated 4s pytest" to "pytest sandboxed with an 8 s timeout".

Do not change any other route. Then from the project root run `uvicorn backend.main:app --port 8000`
and check: GET /api/health reports M2 repo/pdf/sandbox present; POST /api/ingest-repo
{"github_url":"demo","use_demo_cache":true} returns title "vivavoce-demo-repo" with 7 files and authors
Aman Verma / Priya Nair / Rohan Gupta (NOT the mock repo); POST /api/ingest-pdf with
backend/demo_cache/sample_paper.pdf returns 6 paper_nodes; POST /api/ingest-repo
{"github_url":"git@github.com:a/b.git"} returns 400 {"error": "...", "detail": "..."}.
Do not git commit. Report what you changed.
```

### FIX PROMPT 2: J3 port merge rules (team repo, M2-owned paths)

```text
You are porting M2 (C:\personal\shreyas\workOS\hackathons\vihaan\m2) into the VivaVoce team repo
(branch m2-ingestion). Do NOT blindly copy files over: the team repo has code in M2's folders that
other team code still uses. Rules:

1. Copy as-is (new or stub-only in the team repo): backend/ingestion/config.py, models.py,
   demo_loader.py, dev_cli.py, git_blame.py; backend/replay/** ; backend/demo_cache/** (keep any
   team-only files that exist there, e.g. sample_repo/); backend/tests_m2/**.
   Before overwriting team git_blame.py, grep the team repo for "author_map_as_dict" and
   "_blame_file". If anything outside git_blame.py uses them, append the team versions of those
   functions to the end of M2's git_blame.py unchanged.

2. backend/sandbox/sandbox_runner.py: start from M2's file, then APPEND the team file's
   multi-language section unchanged: _sanitize_cpp_code, _strip_solution_class_braces,
   _clean_driver_cpp, _generate_fallback_cpp_main, _clean_driver_java, _clean_driver_python,
   _clean_driver_javascript, _minimal_environment, execute_multi_language_sandbox, plus any
   module-level constants/imports they need. backend/main.py imports
   `from backend.sandbox.sandbox_runner import execute_multi_language_sandbox` (OA mode).
   Keep M2's execute_verification (signature-compatible with the team call).

3. backend/ingestion/pdf_parser.py: use M2's file and ADD at the end:
       def load_demo_paper_bytes() -> bytes:
           """Bytes of the bundled sample paper (used by main.py when no file is uploaded)."""
           return (Path(DEMO_CACHE_DIR) / "sample_paper.pdf").read_bytes()
   (import DEMO_CACHE_DIR from ingestion.config). Before replacing, grep the team repo for every
   `pdf_parser.` / `from backend.ingestion.pdf_parser import` / `from .pdf_parser import` use
   (especially in paper_breakdown.py and brain/). For any other name still used, copy that team
   function into M2's pdf_parser.py unchanged and list it in the handoff.

4. backend/ingestion/repo_parser.py: use M2's file and ADD
       def load_demo_repo_index():
           from ingestion.demo_loader import load_demo_repo
           return load_demo_repo()[0]
   because the team ingestion/__init__.py exports it. Grep for other users of team repo_parser
   names (_validate_github_url, _build_index, ...) and keep anything still referenced.

5. backend/ingestion/__init__.py and backend/sandbox/__init__.py: use M2's versions (they
   re-export a superset), then re-add any name the team versions exported that is still imported
   anywhere (load_demo_repo_index). Never delete leetcode_parser.py or paper_breakdown.py.

6. requirements.txt (M1-owned; propose, don't edit unless Nishit agrees): it already has PyMuPDF,
   google-genai, httpx, pytest, python-dotenv, python-multipart. fpdf2 is only needed to rebuild
   the sample paper (dev only).

7. From backend/ run `python -m pytest tests_m2 -q` (expect 164 passed, 2 skipped) and from the
   project root run `python -c "import sys; sys.path[:0]=['.','backend']; import backend.main"`.
   Both must succeed. Do not git commit. Write docs/m2/handoffs/J3.md listing every
   team function you kept and why.
```

### FIX PROMPT 3: small M2 polish (M2 repo) — ✅ APPLIED and verified in J2

```text
In the M2 repo (C:\personal\shreyas\workOS\hackathons\vihaan\m2), make only these edits:

1. docs/m2/NOTES_FOR_TEAM.md §4 "What the sandbox DOES protect against": add a bullet
   "**Fork/memory bombs (Windows):** the Job object caps each run at 32 processes and 1 GB; every
   process is killed when the run ends. (macOS/Linux: timeout + process-group kill only, no caps.)"
   In "does NOT protect against", add "Student code can locate and read backend/.env via
   sys.prefix (the venv lives in backend/). Use a throwaway, quota-limited Gemini key for demos."
   In §1.1, add `python-multipart>=0.0.12` (needed for UploadFile) and mark fpdf2 as dev-only.
   In §1.2 change the example to `GEMINI_MODEL=gemini-3.8-flash` and add a note that
   gemini-2.5-flash returns 404 for new keys.

2. backend/ingestion/dev_cli.py run_sandbox_leak: change the PASS verdict text from
   "Zero secrets leaked" to "No secrets in the child environment (same-user file reads are NOT
   blocked; see NOTES §4)". Keep the logic. Update tests_m2/test_j1_end_to_end.py if it asserts
   on the old text.

3. Run `python -m pytest tests_m2 -q` from backend/ (expect 164 passed, 2 skipped) and
   `python -m ingestion.dev_cli sandbox-leak`. Do not git commit.
```

---

## 5. Improvement-plan verification (M2 items)

| Item | Status | Evidence |
|------|--------|----------|
| **P0-2.1** Key-safe sandbox env | **Done** (env dict); same-user file/psutil reads remain, documented | `_build_minimal_env` (`sandbox_runner.py`); `test_b1_sandbox.py::test_key_leak_prevention`; `dev_cli sandbox-leak` PASS; J2 T1/T3 confirm the documented limits |
| **P0-2.2** Multi-file sandbox (sibling imports) | **Done** in M2; **partly** in the team app until FIX PROMPT 1 passes `repo_root` | `_copy_repo_files`; `test_b2_sandbox_repo.py`; `dev_cli challenge demo` (starter 4/6 FAIL, reference 6/6 PASS); J2 adapter check |
| **P0-2.3** 8 s timeout, tree kill, warm-up | **Done** (+ J2 process/memory caps) | Job object kill-on-close; `test_b1_sandbox.py` timeout/orphan/pipe-holding tests; J2 T4/T5/T7/T8 (0 survivors, 8.4 s timeout); `warm_up_sandbox` ≈ 1.2–1.3 s |
| **P0-2.4** Fully offline demo (replay) | **Partly**: infrastructure done; recording not made; middleware not yet in the team `main.py` | `backend/replay/*`; `test_b6_replay.py` (8 tests); `demo_cache/replay/` holds only README + .gitkeep |
| **P1-2.5** Concept graph: Gemini structured output + Mermaid in code | **Partly**: code done and heuristic verified; the live Gemini path has never returned `source='gemini'` (404 then 429) | `build_concept_graph`, `build_mermaid`; `test_b4_graph.py`; J2 live call → heuristic in 2.3 s |
| **P1-2.6** Verbatim excerpt verification | **Done** | `verify_excerpt`; `test_b5_paper.py`; cached sample paper 6/6 `excerpt_verified=True` |
| **P1-2.7** git blame authorship + identity merge | **Done** | `git_blame.py`; `test_a3_blame.py`; demo 49.8 / 28.8 / 21.4 %; J1 psf/requests live (270 authors) |
| **P1-2.8** Python repos only | **Done** (non-Python rejection added in J2) | `rank_python_files` .py-only; J2 fix in `clone_and_index_repo` + probe (friendly IngestionError, clone deleted) |
| **P2-2.9** Shallow clone for big repos | **Done** | `clone_repo` GitHub size check → full vs `--depth 50`; `test_a1_clone.py` network test (passed with `M2_NETWORK_TESTS=1`); shallow-blame note in `compute_authorship_stats` docstring |

## 6. Demo-day failure modes

| Scenario | What happens now | Acceptable? |
|----------|------------------|-------------|
| Wi-Fi down: demo repo | `is_demo_source` is checked before any network call. JSON cache loads in ~3 ms; `materialize_demo_repo` clones the local bundle. | ✅ (after FIX PROMPT 1; today's team `main.py` would show the mock) |
| Wi-Fi down: sample paper | Cache hit by sha256, ~1 ms, `source='cache'` | ✅ |
| Wi-Fi down: replay | Works only once a recording exists (`DEMO_RECORD=1` run at Hour 20). Non-JSON `/api/*` returns 409; WebSockets go live. | ⚠️ must record + rehearse |
| Gemini key missing | Heuristic concept graph, immediately | ✅ |
| Gemini rate-limited / wrong model | 404 → 429 → heuristic in 2.3 s (measured) | ✅; a *hung* API costs ~61 s → lower `GEMINI_TIMEOUT_S` |
| Giant repo | Size check → `--depth 50`; 45 s clone timeout → friendly IngestionError; >2000-line files skipped; top 15 indexed; blame ≤10 s/file × 2 | ✅ if threaded (§1.8); slow but bounded |
| Private / 404 repo | Friendly "not found or is private" IngestionError in 4.3 s; no credential prompt | ✅ |
| Non-Python repo | **Now** friendly IngestionError + clone deleted (J2 fix) | ✅ |
| Weird / scanned / encrypted PDF | Garbage/encrypted/image-only → IngestionError; headingless → one section per page + heuristic graph | ✅ (cosmetic: raw PyMuPDF text in the message) |
| Infinite loop | `timed_out=True` at ~8.4 s; whole tree killed | ✅ |
| Fork bomb | **Now** capped at 32 processes / 1 GB per run (Windows); all killed at run end | ✅ (Windows) / ⚠️ macOS–Linux uncapped |
| Two challenges at once | Separate temp dirs + Job objects; 3 concurrent runs in 1.8 s, correct results | ✅ (via `execute_verification_async` / `to_thread`) |
| Judge reads `backend/.env` from student code | Succeeds (same OS user) | ⚠️ documented; use a throwaway key |

## 7. Pre-merge & demo-day checklist

**Before J3 merge**
- [x] J2 fixes + FIX PROMPT 3 committed and pushed (`m2(J2): final readiness review and hardening fixes`).
- [ ] J3: FIX PROMPT 2 merge rules (keep `execute_multi_language_sandbox`, `load_demo_paper_bytes`, `load_demo_repo_index`, `leetcode_parser.py`, `paper_breakdown.py`).
- [ ] J3: FIX PROMPT 1 in `main.py` (with Nishit). Then `/api/ingest-repo` demo shows **studysync**, not the mock.
- [ ] `pytest tests_m2 -q` green in the team repo; `uvicorn backend.main:app` starts from the project root.
- [ ] `backend/.env` untracked; no `demo_cache/replay/session.jsonl` or `*.mp3` committed until the real recording; no judge PDFs in `demo_cache/papers/` (only `73cbee6fbc268346.json`).

**Demo day**
- [ ] `.env`: `GEMINI_MODEL=gemini-3.8-flash`, `GEMINI_TIMEOUT_S=15`, a throwaway key with quota left.
- [ ] Record the replay at Hour 20 on the merged app (`DEMO_RECORD=1`, one scripted viva, stop). Check `GET /api/replay/status`. Rehearse once with `DEMO_REPLAY=1` and Wi-Fi OFF, then `POST /api/replay/reset`.
- [ ] Warm start: server startup runs `warm_up_sandbox` + `materialize_demo_repo`; run `python -m ingestion.dev_cli challenge demo` once (expect VERDICT: PASS).
- [ ] Keep `%TEMP%\vivavoce\` small (delete old clones between sessions).
- [ ] Pitch wording: "sandboxed with a timeout", "Python repositories only". Never "isolated".

## 8. 30-second pitch talking points: "how our sandbox and offline mode work"

- **Sandbox:** "When you fix the bug, we copy the repo's Python files into a fresh temp folder, drop in your version, and run pytest **sandboxed with a timeout**. That means a brand-new environment with none of our API keys, 8 seconds max, and a Windows Job object that caps the run at 32 processes and 1 GB, then kills every process it started. Infinite loops and fork bombs just come back as 'Time Limit Exceeded'."
- **Honest limits (say it before they ask):** "It runs as the same OS user, so it doesn't block file reads or the network. That's fine for a prototype where the student is running their own code. In production we'd put this exact runner inside a container or microVM."
- **Offline mode:** "The demo repo ships as a git bundle with a pre-built index and blame data, so it loads in about 3 ms with no network. The sample paper's concept graph is cached by its hash. If the venue Wi-Fi dies, a replay middleware answers every API call from a recorded session, audio included, with zero external calls."
- **Grounding:** "Every question cites real line ranges (`snap_range` clamps whatever the LLM says to a real function), and every paper excerpt is checked word-for-word against the PDF text."

## 9. Commands run by J2 (results)

- `python -m pytest tests_m2 -q` → 164 passed, 2 skipped (before and after fixes)
- `M2_NETWORK_TESTS=1 python -m pytest tests_m2 -q` → 166 passed
- `dev_cli repo demo` (2.96 ms) · `pdf demo_cache/sample_paper.pdf` (cache, 1.24 ms, 6 nodes) · `challenge demo` (PASS) · `sandbox-leak` (PASS) · `replay-status` (0 calls). All exit 0.
- Adversarial probes (temp scripts, deleted afterward): T1/T2 `.env` via `sys.prefix` (readable) and cwd walk (not found); T3 psutil ancestor env (leak, documented); T4 15-process fork tree (0 survivors); T5 spawn loop (timeout 8.4 s, 0 survivors); T6 outbound TCP (open); T7 unbounded spawn (capped, 0 survivors); T8 1.5 GB allocation (MemoryError); T9 normal test (pass). Also: pathological `.py` file, non-Python repo, 404 repo, unwritable paper cache, 3 concurrent challenges, live Gemini call, NOTES §1.3–1.5 executed with TestClient against the team `schemas.py`, and the FIX PROMPT 1 adapter executed against the team `schemas.py`.
