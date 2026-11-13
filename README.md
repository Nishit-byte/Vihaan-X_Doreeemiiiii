# VivaVoce — Dual-Modality Technical Examiner & Code/Paper Verification System

**Track:** Education | **Architecture:** FastAPI Modular Monolith + React/Vite Split-Screen Workspace

VivaVoce is an adaptive spoken-voice and synchronized-text technical examiner that ingests either:
1. **Mode A (GitHub Repository):** Parses source files into Abstract Syntax Trees (AST) and `git blame` contributor ownership maps, highlights exact line ranges (`line_start..line_end`) in a live Monaco IDE, conducts a 4-tier Bloom's Taxonomy spoken viva (L1 Recall $\rightarrow$ L4 Mutation), and verifies student bug fixes empirically inside an isolated 4-second `pytest` sandbox.
2. **Mode B (Research Paper / Lab Report PDF):** Extracts methodology stages into a directed Mermaid.js concept/architecture flowchart (`N1..N8`), highlights the active node with its verbatim paper excerpt during questioning, and evaluates deep methodological comprehension.

---

## 1. Research Foundation

| Subsystem | Foundational Research | Architectural Implementation in VivaVoce |
| :--- | :--- | :--- |
| **Examiner State Machine & Tool Use** | Yao et al. (ICLR 2023), *ReAct*; Graesser et al. (2004), *AutoTutor* | State-driven ReAct loop (`backend/brain/state_machine.py`) reasoning over the student's answer before selecting `DrillDown`, `Probe`, `Hint`, or `TriggerCodeChallenge`. |
| **Adaptive Depth Ladder (L1–L4)** | Anderson & Krathwohl (2001), *Revised Bloom's Taxonomy* | 4-tier cognitive progression: **L1** Recall (*What*), **L2** Comprehension (*Why*), **L3** Analysis/Trade-offs (*Compare*), **L4** Evaluation/Mutation (*What breaks if* + Live IDE fix). |
| **AST-Grounded Code Retrieval** | Guo et al. (ICLR 2021), *GraphCodeBERT*; Lewis et al. (NeurIPS 2020), *RAG* | `repo_parser.py` & `git_blame.py` extract AST function boundaries, call graphs, constants, and per-line contributor provenance. |
| **Execution-Based Verification** | Chen et al. (OpenAI 2021), *HumanEval / Pass@k* | Spoken claims and live bug fixes are verified empirically by running generated `pytest` suites inside a 4-second isolated subprocess (`sandbox_runner.py`). |
| **Fluency-Blind Semantic Grading** | Koenecke et al. (PNAS 2020), *Racial disparities in ASR* | `grader.py` strips ASR hesitation/filler artifacts and assigns **0% weight** to grammar, accent, or Hinglish code-switching. |
| **Visual Concept Mapping** | Novak & Cañas (2008), *Theory Underlying Concept Maps* | `pdf_parser.py` synthesizes a directed `flowchart TD` (`N1..N8`) paired with 2-sentence verbatim paper excerpts. |

---

## 2. Repository Structure & Zero-Conflict 4-Member Worksplit

Every file has a single owner (`M1`, `M2`, `M3`, or `M4`) to guarantee zero Git merge conflicts during the 24-hour sprint:

```text
vivavoce/
|-- README.md                         [M1: Setup & Demo Instructions]
|-- .env.example                      [M1: API Keys Template]
|-- backend/
|   |-- requirements.txt              [M1: Python Dependencies]
|   |-- main.py                       [M1: FastAPI App, CORS, Route Mounting]
|   |-- models/
|   |   |-- __init__.py               [M1]
|   |   `-- schemas.py                [M1: All Shared Pydantic Request/Response Models]
|   |-- brain/
|   |   |-- __init__.py               [M1]
|   |   |-- prompts.py                [M1: System Prompts for Repo, Paper, Bug Gen, Grader]
|   |   |-- state_machine.py          [M1: Adaptive L1-L4 Examiner Loop & Session Store]
|   |   `-- grader.py                 [M1: Fluency-Blind Rubric & Depth Radar Calculator]
|   |-- ingestion/                    [M2: repo_parser.py, git_blame.py, pdf_parser.py]
|   |-- sandbox/                      [M2: sandbox_runner.py]
|   |-- voice/                        [M3: stt_service.py, tts_service.py, audio_utils.py]
|   `-- demo_cache/                   [M2: sample_repo/ & sample_paper.pdf]
`-- frontend/                         [M4 + M3: React + Vite + Monaco + Mermaid + Recharts]
```

---

## 3. Quickstart & Setup Instructions

### Backend Setup (Port 8000)

```bash
# 1. From the repository root (vivavoce/)
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# 2. Install Python dependencies
pip install -r backend/requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env and add GEMINI_API_KEY and GROQ_API_KEY (offline deterministic fallback works out-of-the-box)

# 4. Launch FastAPI Modular Monolith on Port 8000
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive Swagger API docs are available at: `http://localhost:8000/docs`

### Frontend Setup (Port 5173)

```bash
cd frontend
npm install
npm run dev
```

---

## 4. Core REST API Contract (`backend/main.py` & `backend/models/schemas.py`)

| Method | Endpoint | Description | Request Body / Form | Response Model |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/health` | Live status of M1/M2/M3 modules & active session count | — | `dict` |
| `POST` | `/api/ingest-repo` | Clones & AST-indexes GitHub repo, maps `git blame`, starts L1 Viva | `IngestRepoRequest` | `IngestResponse` |
| `POST` | `/api/ingest-pdf` | Parses PDF into Mermaid `flowchart TD` (`N1..N8`), starts Paper Viva | `multipart/form-data` (`file`) | `IngestResponse` |
| `POST` | `/api/viva/turn` | Transcribes audio / cleans text, runs L1–L4 ReAct loop, returns TTS | `TurnRequest` (JSON) or `FormData` | `TurnResponse` |
| `POST` | `/api/run-code` | Runs student code & `pytest` suite inside isolated 4s subprocess | `RunCodeRequest` | `RunCodeResponse` |
| `GET` | `/api/report/{id}` | Generates Fluency-Blind Rubric & Bloom Depth Radar scorecard | Path `session_id` | `VivaReport` |

---

## 5. Hackathon Demo Flow (90-Second Pitch Script)

1. **Repo Ingestion & Author Filtering (0:00–0:20):** Paste a GitHub repo URL, select teammate **`Nishit`** from the `git blame` dropdown, and watch VivaVoce open `src/retrieval/scorer.py` highlighting lines `6..18` while speaking an **L1 Recall** question aloud.
2. **Adaptive Bloom L1 $\rightarrow$ L4 Escalation (0:20–0:50):** Answer using Spacebar Push-to-Talk (even with casual Hinglish/fillers). Watch the **Live Cognitive Depth Meter** climb from **L1** to **L4** and trigger a live `CodingChallenge`.
3. **Empirical Sandbox Verification (0:50–1:10):** Fix the zero-norm boundary bug directly in the Monaco IDE, click **Run & Verify**, and show the green `pytest` pass output from the isolated 4s sandbox.
4. **Visual Paper Mode & Fluency-Blind Report (1:10–1:30):** Switch to Paper Explorer to show active Mermaid node highlighting (`N1..N6`), then click **Finish Viva** to display the Recharts Depth Radar and the **Fluency & Accent Weight: 0%** audit badge.
