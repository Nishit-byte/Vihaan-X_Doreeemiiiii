# VivaVoce Project Guide

## Who it is for

Students preparing for technical interviews, explaining projects they have built, practicing DSA problems, or trying to understand research papers.

## Modes at a glance

| Mode | Input | What the student does | What VivaVoce provides |
|---|---|---|---|
| Practice Interview | GitHub repository | Explains code and design decisions by voice or text | Context-aware questions, relevant code focus, adaptive follow-ups, practice report |
| Coding Practice | DSA problem | Writes and runs a solution in the editor | Starter challenge, tests, feedback and questions about complexity/edge cases |
| Research Paper Explorer | Research-paper PDF | Reads a structured breakdown and explores cited evidence | Paper explanation, method/concept visual, results when supported, glossary and source excerpts |

The research-paper mode is for paper understanding. Interview behavior belongs to the repository and coding-practice flows.

## First-time setup

1. Install Python 3.10+ and Node.js/npm.
2. Create a Python virtual environment at the repository root.
3. Install backend packages with `pip install -r backend/requirements.txt`.
4. Start the backend: `uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`.
5. In `frontend/`, run `npm install` and `npm run dev`.
6. Open the Vite URL (normally port 5173) and try the demo inputs first.
7. Configure `GEMINI_API_KEY` and `GROQ_API_KEY` in the environment for the corresponding live AI/STT integrations. See README for details.

## How to use each mode

### Practice Interview

1. Open the project interview mode.
2. Enter a public GitHub repository URL or select the available demo.
3. Review the code context presented by the workspace.
4. Start the interview and answer using push-to-talk or the text field.
5. Follow the question progression and inspect referenced files/lines.
6. Finish to view the practice report.

### Coding Practice

1. Open DSA practice and select a problem.
2. Read the prompt and starter code.
3. Implement a solution in the editor.
4. Run verification and inspect test output.
5. Discuss trade-offs, time/space complexity, and edge cases with the examiner.

### Research Paper Explorer

1. Open paper study and upload a selectable-text PDF or load the demo paper.
2. Review the title and paper overview, checking metadata if uncertain.
3. Explore the problem, method, evidence/results, contributions, limitations, future work, and glossary.
4. Click a claim or diagram node to inspect its supporting excerpt and page.
5. Treat conceptual diagrams as explanatory maps, not necessarily original figures from the paper.

## AI and voice setup

- Set `GEMINI_API_KEY` to enable Gemini-backed generation where supported.
- Set `GROQ_API_KEY` to enable Groq Whisper speech transcription.
- Voice playback uses the configured TTS implementation; optional ElevenLabs settings are available in the voice configuration.
- Keep text input available in interviews if microphone permission, transcription, or network access fails.

## Project structure reference

- `backend/brain/` — interview logic, prompts, grading, and DSA coaching.
- `backend/ingestion/` — repository parsing, PDF parsing, and paper breakdown.
- `backend/voice/` — STT/TTS and voice routes.
- `backend/sandbox/` — code verification.
- `frontend/src/components/` — user experiences and visual workspaces.
- `frontend/src/services/` — API, demo fallback, and audio handling.
- `backend/demo_cache/` — sample repository and sample paper.

## Demo checklist

- Start backend and frontend and confirm `/api/health` responds.
- Load the sample repository and sample PDF once before presenting.
- Check microphone permissions and typed-answer fallback.
- Keep API credentials out of source control and screenshots.
- Be transparent when demo/fallback data is being used.
- Avoid describing the subprocess runner as a secure production sandbox.
