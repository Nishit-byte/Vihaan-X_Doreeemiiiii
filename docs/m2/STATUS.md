# M2 STATUS BOARD

Only the Claude reviewer edits this file (one row update per review).
Build: not started / in progress / ready for review. Review: — / PASS / FAIL (n).

| ID | Lane | Task | Build | Review | Commit | Notes |
|----|------|------|-------|--------|--------|-------|
| S0 | —    | M2 folder, repo, docs + scan | done | — | — | |
| S1 | —    | Scaffold | done | PASS | 7e5509f | reviewer set DEMO_REPLAY/RECORD default False |
| A1 | A    | Clone + URL validation + ranking | done | PASS | 8d3d3d8 | reviewer fixed ".."/canonical clone URL/no-prompt env |
| A2 | A    | AST indexer + RepoIndex helpers | done | PASS | f173246 | reviewer widened parse-failure except to ValueError/RecursionError/MemoryError |
| A3 | A    | git blame + authorship | done | PASS | b927987 | |
| A4 | A    | Demo repo studysync | done | PASS | 7edb875 | |
| A5 | A    | Demo loader + cache wiring | done | PASS | (see git log: m2(A5)) | 9 tests; offline load ~3 ms; minor: reused dir not reset if dirtied |
| B1 | B    | Sandbox core | done | PASS | (see git log) | round 2: Job object kill-on-close + file output fixed orphans/false timeouts; psutil ancestor-env read + WMI launch remain documented limits; reviewer reworded docstring/handoff |
| B2 | B    | Sandbox repo copy + async + warm-up | done | PASS | (see git log: m2(B2)) | 25 tests pass (B1+B2); cold ~1.0 s / warm ~0.85 s; minor: copy cap stops silently, junctions not detected |
| B3 | B    | PDF extraction + sample paper | done | PASS | (see git log: m2(B3)) | 10 tests pass; 12 sections in sample paper; minor: short bold standalone lines count as headings |
| B4 | B    | Concept graph + Mermaid | done | PASS | (see git log: m2(B4)) | 20 tests pass (B3+B4); live Gemini fell back to heuristic (timeout); reviewer raised min Gemini nodes to 5 |
| B5 | B    | Excerpt verify + paper cache | done | PASS | (see git log: m2(B5)) | 35 tests pass (B3+B4+B5); sample paper cache committed (heuristic) |
| B6 | B    | Replay mode | done | PASS | (see git log: m2(B6)) | 8 B6 tests pass, Lane B 79 pass; audio round-trip made lossless; M1 must add ReplayMiddleware BEFORE CORSMiddleware |
| J1 | Join | End-to-end + dev_cli + team notes | done | PASS | (see git log: m2(J1)) | 164 pass; 5 CLI cmds OK; NOTES route code is illustrative, align in J3 |
| J2 | Join | Final review | done | READY WITH FIXES | df15e38 | FIX PROMPT 3 applied; FIX PROMPTS 1–2 queued for J3; 164 pass / 166 w/ network; team main.py can't import M2 + expects M1 types → FIX PROMPT 1–2 for J3; reviewer fixed RecursionError, non-Python repo, cache-write raise, Job caps (32 procs/1 GB), NOTES demo repo_root + to_thread; see FINAL_REVIEW.md |
| J3 | Join | Port to team repo + PR | not started | — | — | |
