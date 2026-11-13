# M3 STATUS BOARD

Only the Claude reviewer edits this file (one row update per review).
Build: not started / in progress / ready for review. Review: — / PASS / FAIL (n).

| ID | Lane | Task | Build | Review | Commit | Notes |
|----|------|------|-------|--------|--------|-------|
| S0 | —    | Docs setup + repo scan | done | — | — | |
| A1 | A    | Voice scaffold, config & deps | done | PASS | 3daec1a | Stubs only; routes in A5 |
| A2 | A    | TTS service | done | PASS | m3(A2) | edge-tts + ElevenLabs fallback, LRU 128 |
| A3 | A    | Audio utils + filler cache | not started | — | — | |
| A4 | A    | STT service | not started | — | — | |
| A5 | A    | voice_router + dev_server | not started | — | — | |
| A6 | A    | Self-test + hardening | not started | — | — | |
| B1 | B    | Recon, dev harness, stubs | done | PASS | 3daec1a | Mode (a); http://localhost:5173/examiner-dev.html |
| B2 | B    | Push-to-talk recorder | done | PASS | m3(B2) | 3 reviewer fixes (keyup/blur/enabled stuck-recording); B6: avoid 2 hook instances binding Space |
| B3 | B    | Playback + browser TTS | not started | — | — | |
| B4 | B    | Panel static layout | not started | — | — | |
| B5 | B    | Voice orb | not started | — | — | |
| B6 | B    | Turn-flow wiring | not started | — | — | |
| J1 | Join | End-to-end + team notes | not started | — | — | |
| J2 | Join | Final review | not started | — | — | |

