# REPO STATE — M3 SCAN (Post-Git Remote Connection)

Date: 2026-11-13
Host OS: Windows
Working Directory: `C:\personal\shreyas\workOS\hackathons\vihaan\project`
Remote Repository: `https://github.com/Nishit-byte/Vihaan.git`

---

## 1. Git & Repo Root

- **Repo root absolute path:** `C:\personal\shreyas\workOS\hackathons\vihaan\project`
- **Git repo present:** Yes (`.git` initialized and linked to remote)
- **Current branch:** `m3-voice` (branched from `main`, tracking `origin/main`)
- **Remotes:** `origin` -> `https://github.com/Nishit-byte/Vihaan.git` (fetch & push)
- **Remote branches present:**
  - `origin/main` (active default branch)
  - `origin/feat/m2-ingestion`
  - `origin/feat/m4-frontend`
  - `origin/fix/viva-start-and-schema-sync`
- **Last 5 commits (on `main` / `m3-voice`):**
  1. `389ebfb` - Merge branch 'fix/viva-start-and-schema-sync'
  2. `a95e4f2` - fix(m1,m4): add Start Viva flow, open README.md by default, sync schemas, and vary fallback questions
  3. `304f278` - Merge pull request #2 from Nishit-byte/feat/m2-ingestion
  4. `1c43ed3` - feat(m2): implement ingestion and sandbox modules
  5. `58e698d` - renamed file
- **Uncommitted / untracked files:**
  - `M3_ORCHESTRATOR_HANDOFF.md` (preserved, untracked)
  - `docs/` (containing `docs/m3/` planning files, preserved, untracked)
- **Commit / Push Status:** Clean working tree relative to Git; no commits or pushes executed.

---

## 2. Folder Tree (3 Levels Deep)

Excluding `node_modules`, `.venv`, `venv`, `.git`, `__pycache__`, `dist`:

```
C:\personal\shreyas\workOS\hackathons\vihaan\project\
├── .gitattributes
├── .gitignore
├── M3_ORCHESTRATOR_HANDOFF.md
├── README.md
├── backend\
│   ├── brain\
│   │   ├── grader.py
│   │   ├── prompts.py
│   │   ├── state_machine.py
│   │   └── __init__.py
│   ├── demo_cache\
│   │   ├── sample_repo\
│   │   ├── .gitkeep
│   │   ├── sample_paper.pdf
│   │   └── sample_repo_index.json
│   ├── ingestion\
│   │   ├── .gitkeep
│   │   ├── git_blame.py
│   │   ├── pdf_parser.py
│   │   ├── repo_parser.py
│   │   └── __init__.py
│   ├── models\
│   │   ├── schemas.py
│   │   └── __init__.py
│   ├── sandbox\
│   │   ├── .gitkeep
│   │   ├── sandbox_runner.py
│   │   └── __init__.py
│   ├── voice\
│   │   └── .gitkeep
│   ├── main.py
│   ├── requirements.txt
│   └── __init__.py
├── docs\
│   └── m3\
│       ├── handoffs\
│       │   └── .gitkeep
│       ├── CONTEXT.md
│       ├── REPO_STATE.md
│       ├── STATUS.md
│       └── TASKS.md
└── frontend\
    ├── src\
    │   ├── components\
    │   │   ├── EmptyState.tsx
    │   │   ├── ExaminerPanel.tsx
    │   │   ├── IdeWorkspace.tsx
    │   │   ├── PaperWorkspace.tsx
    │   │   ├── ReportModal.tsx
    │   │   └── TopNavbar.tsx
    │   ├── services\
    │   │   ├── apiClient.ts
    │   │   └── demoData.ts
    │   ├── types\
    │   │   └── api.ts
    │   ├── App.tsx
    │   ├── index.css
    │   ├── main.tsx
    │   └── monacoSetup.ts
    ├── .gitkeep
    ├── index.html
    ├── package-lock.json
    ├── package.json
    ├── tsconfig.json
    └── vite.config.ts
```

---

## 3. File Ownership Scan (Updated with Origin State)

### M3-Owned Files
| File Path | Exists? | Line Count | Status / Notes |
|-----------|---------|------------|----------------|
| `backend/voice/__init__.py` | No | 0 | Ready to create in A1 |
| `backend/voice/config.py` | No | 0 | Ready to create in A1 |
| `backend/voice/stt_service.py` | No | 0 | Ready to implement in A2 |
| `backend/voice/tts_service.py` | No | 0 | Ready to implement in A3 |
| `backend/voice/audio_utils.py` | No | 0 | Ready to implement in A2/A3 |
| `backend/voice/dev_server.py` | No | 0 | Ready to create in A4 |
| `backend/voice/selftest.py` | No | 0 | Ready to create in A5 |
| `backend/voice/filler_cache/**` | No | 0 | Ready to pre-generate in A3 |
| `backend/voice/.gitkeep` | Yes | 0 | Placeholder committed by team |
| `backend/.env` | No | 0 | To be created locally with API keys |
| `frontend/src/services/audioRecorder.ts` | No | 0 | Ready to create in B2 |
| `frontend/src/components/ExaminerPanel.tsx` | Yes | 227 | Scaffolded by M4; M3 owns refining audio recording, orb sync & playback |
| `frontend/examiner-dev.html` | No | 0 | Standalone tester optional |
| `frontend/src/dev/**` | No | 0 | Optional test harness |
| `m3-playground/**` | Deprecated | 0 | Not needed: M4 already delivered working frontend scaffold |
| `docs/m3/CONTEXT.md` | Yes | 293 | Preserved untracked |
| `docs/m3/TASKS.md` | Yes | 226 | Preserved untracked |
| `docs/m3/STATUS.md` | Yes | 22 | Preserved untracked |
| `docs/m3/REPO_STATE.md` | Yes | - | Active document |
| `docs/m3/handoffs/.gitkeep` | Yes | 1 | Preserved untracked |

### Team-Owned Files (Pushed by M1, M2, M4)
| File Path | Exists? | Line Count | Owner | Status / Notes |
|-----------|---------|------------|-------|----------------|
| `.gitignore` | Yes | 21 | Team | Configured; ignores `.env`, `node_modules`, `.venv` |
| `backend/requirements.txt` | Yes | 19 | M1 | Includes `groq>=0.11.0` and `edge-tts>=6.1.12` |
| `backend/main.py` | Yes | 651 | M1 | Fully functional FastAPI app with M3 voice adapter hooks |
| `backend/models/schemas.py` | Yes | 161 | M1 | Canonical contract: `TurnRequest`, `TurnResponse`, `VerdictType` |
| `backend/brain/state_machine.py` | Yes | 791 | M1 | ReAct Bloom L1-L4 state machine |
| `backend/brain/grader.py` | Yes | 229 | M1 | Fluency-blind rubric grader |
| `backend/brain/prompts.py` | Yes | 182 | M1 | Prompts for viva evaluation |
| `backend/ingestion/repo_parser.py` | Yes | 355 | M2 | AST extraction and repo chunker |
| `backend/ingestion/git_blame.py` | Yes | 93 | M2 | Contributor line authorship mapping |
| `backend/ingestion/pdf_parser.py` | Yes | 267 | M2 | PyMuPDF extractor and Mermaid graph builder |
| `backend/sandbox/sandbox_runner.py` | Yes | 90 | M2 | 4s isolated pytest sandbox execution |
| `frontend/package.json` | Yes | 29 | M4 | Vite + React + Tailwind v4 + Monaco + Mermaid |
| `frontend/vite.config.ts` | Yes | 13 | M4 | Port 5173 with `/api` -> `http://localhost:8000` proxy |
| `frontend/src/App.tsx` | Yes | 141 | M4 | Full split-view layout with TopNavbar and workspaces |
| `frontend/src/main.tsx` | Yes | 9 | M4 | React DOM entry point |
| `frontend/src/index.css` | Yes | 60 | M4 | Tailwind v4 @theme design tokens |
| `frontend/src/services/apiClient.ts` | Yes | 150 | M4 | API client with demo fallback & normalization |
| `frontend/src/types/api.ts` | Yes | 96 | M4 | TypeScript interfaces synced with schemas.py |

---

## 4. Backend Environment

- **Python version:** `Python 3.13.5`
- **py launcher version:** `Python 3.13.5`
- **Virtualenv folder and path:** None found yet (ready to create `backend/.venv` in A1).
- **Content of `backend/requirements.txt`:**
  - `fastapi>=0.115.0`
  - `uvicorn[standard]>=0.32.0`
  - `pydantic>=2.9.0`
  - `python-dotenv>=1.0.1`
  - `python-multipart>=0.0.12`
  - `httpx>=0.27.2`
  - `google-genai>=1.0.0`
  - `google-generativeai>=0.8.3`
  - `GitPython>=3.1.43`
  - `PyMuPDF>=1.24.13`
  - `pytest>=8.3.3`
  - `groq>=0.11.0` (M3 Voice STT)
  - `edge-tts>=6.1.12` (M3 Voice TTS)

---

## 5. Models & Schemas (`backend/models/schemas.py`)

- **File status:** Exists (161 lines). Canonical and locked.
- **`TurnRequest` defined?:** Yes (lines 113-131):
  ```python
  class TurnRequest(BaseModel):
      session_id: str
      student_text: Optional[str] = Field(default=None, description="Direct text answer")
      audio_base64: Optional[str] = Field(default=None, description="Base64-encoded WebM/WAV audio")
      selected_author: Optional[str] = Field(default=None, description="Optional git blame contributor filter")
      code_result: Optional[RunCodeResponse] = Field(default=None, description="Optional result from live sandbox pytest run")
  ```
- **`TurnResponse` defined?:** Yes (lines 133-147):
  ```python
  class TurnResponse(BaseModel):
      session_id: str
      student_transcript: str
      verdict: VerdictType  # Literal["start", "strong", "partial", "weak", "no_answer"]
      ack_text: str
      question_text: str
      audio_base64: str  # MP3/WAV bytes encoded as base64 for instant playback
      topic: str
      depth_level: int = Field(..., ge=1, le=4)
      highlight: Optional[CodeHighlight] = None
      diagram_node_id: Optional[str] = None
      paper_excerpt: Optional[str] = None
      coding_challenge: Optional[CodingChallenge] = None
      done: bool = False
  ```
- **Alignment:** Complete 100% contract match with M3 design.

---

## 6. Frontend Recon

- **Frontend mode:** Mode (a) Scaffolded! M4 has delivered the full workspace into `origin/main`.
- **`package.json` scripts & dependencies:**
  - Scripts: `dev` (vite), `build` (tsc --noEmit && vite build), `preview` (vite preview)
  - Dependencies: `@monaco-editor/react`, `lucide-react`, `mermaid`, `monaco-editor`, `react`, `react-dom`, `recharts`
  - DevDependencies: `@tailwindcss/vite`, `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`, `tailwindcss`, `typescript`, `vite`
- **Tailwind setup:** Tailwind v4 (`@tailwindcss/vite` 4.0.0) configured via `frontend/vite.config.ts` and `@theme` tokens in `frontend/src/index.css`.
- **Global CSS file path:** `frontend/src/index.css`
- **`vite.config.ts` proxy settings:** Proxies `/api` to `http://localhost:8000`.
- **`src/types/api.ts` exists?:** Yes (96 lines). Types matching `schemas.py`.
- **`src/components/ExaminerPanel.tsx` exists?:** Yes (227 lines). Implemented with Web Audio Analyser amplitude meter, MediaRecorder push-to-talk (Spacebar / Click), question card, collapsible transcript, and typed text fallback.

---

## 7. Node & Tooling Versions

- **Node version:** `v24.16.0`
- **npm version:** `11.13.0`

---

## 8. Gitignore Check

- **`.gitignore` status:** Exists (21 lines).
- **Ignores `.env`, `node_modules`, `.venv`/`venv`?:** Yes:
  - Line 5-7: `.venv/`, `venv/`, `env/`
  - Line 12-13: `.env`, `.env.local`
  - Line 16: `node_modules/`

---

## 9. Anything Surprising That Could Affect M3

1. **Ahead of Schedule Monolith Integration:** M1, M2, and M4 have already merged into `main`. The codebase is not an empty skeleton—it is a functional, integrated backend and frontend.
2. **Built-in M3 Adapters in `backend/main.py`:**
   - Lines 398–416: `_invoke_m3_stt` invokes `backend.voice.stt_service.transcribe_audio(audio_bytes, domain_prompt=...)`
   - Lines 419–440: `_invoke_m3_tts` invokes `backend.voice.tts_service.synthesize_speech(text)`
   - Lines 590–600: `/api/filler-audio` serves pre-generated filler clips for sub-200ms audio response.
   Implementing `stt_service.py` and `tts_service.py` will instantly bring the entire live application to life.
3. **No Need for Separate `m3-playground`:** Since M4 has already completed and merged the full Vite React frontend including `ExaminerPanel.tsx`, M3 can work directly inside `frontend/` (or run a dev harness) instead of creating a throwaway playground.
4. **Current Git Branch:** Working on local branch `m3-voice` branched off updated `main`. No commits or pushes have been made.
5. **Untracked Docs Safety:** All documentation files in `docs/m3/` and `M3_ORCHESTRATOR_HANDOFF.md` remain intact and untracked.
