# M3 VOICE PIPELINE — SHARED CONTEXT

Read this whole file at the start of EVERY M3 task chat. It is the single source of truth for
the project, the way Shreyas works, and the exact interfaces M3 must implement.

---

## 1. The project in one paragraph

VivaVoce is a hackathon project (Vihaan hackathon, Education track, 24-hour build). It is a
spoken-plus-text technical examiner. A student gives it a GitHub repo (Mode A) or a research
paper PDF (Mode B). VivaVoce then runs an adaptive spoken viva: it asks questions grounded in
exact code lines or paper diagram nodes, climbs a 4-level Bloom's ladder (L1 Recall, L2
Comprehension, L3 Analysis/Trade-offs, L4 Evaluation/Mutation + live code fix), verifies code
fixes in a 4-second pytest sandbox, and produces a fluency-blind report (accent and grammar get
0% weight).

Stack: one FastAPI backend (modular monolith, port 8000) with modules brain/, ingestion/,
voice/, sandbox/ talking through Pydantic schemas, and one React + Vite + TypeScript + Tailwind
frontend (port 5173) that proxies /api to port 8000. Audio travels as base64 inside JSON.

Team:
- M1 Nishit — team lead, AI brain: schemas.py, prompts.py, state_machine.py, grader.py, main.py
- M2 — ingestion (repo AST parser, git blame, PDF parser) and sandbox runner
- M3 Shreyas — VOICE PIPELINE (this workstream)
- M4 — frontend shell: App.tsx, TopNavbar, Monaco IDE, Paper view, Report modal, apiClient.ts, types/api.ts

Integration checkpoint that matters to M3: Checkpoint 2 (Hour 8) — ExaminerPanel.tsx +
audioRecorder.ts plug into M1's POST /api/viva/turn; spoken question + Spacebar answer + text
card work end-to-end.

Project folder on Shreyas's PC (Windows):  C:\personal\shreyas\workOS\hackathons\vihaan\project
The exact repo root (the folder containing backend/ and frontend/) is recorded in
docs/m3/REPO_STATE.md. Git branch for M3 work: m3-voice.
Path convention: "docs/m3/..." always means <project folder>\docs\m3\... ; code paths such as
"backend/voice/..." and "frontend/src/..." are relative to the repo root from REPO_STATE.md
(usually the same folder).

---

## 2. How Shreyas works (rules for every agent)

1. Work is split into small tasks in two parallel lanes:
   - Lane A = backend voice (Python, backend/voice/)
   - Lane B = frontend voice UI (TypeScript/React)
   The lanes never wait on each other. Lane B uses mocks until the join task J1.
2. Every task runs in its OWN fresh chat. Builds happen in Antigravity with Gemini 3.8 Flash.
   Reviews happen in Claude Code with Claude Sonnet 5.5 (or Opus 5.5 for the hard tasks).
3. PROMPTS OVER TERMINAL COMMANDS. Agents run commands themselves. Never hand Shreyas a list of
   terminal commands. If Shreyas must do something physically (paste an API key, allow the
   microphone, speak into the mic, look at the screen), give him short plain-language steps.
4. Every build task ends by writing a handoff file: docs/m3/handoffs/<TASK_ID>.md (template in §6).
5. Build agents NEVER run git commit. Only the Claude reviewer commits, and only after a PASS.
6. Only the Claude reviewer edits docs/m3/STATUS.md (prevents the two lanes overwriting it).
7. File ownership rule (§3) is absolute. Breaking it is an automatic review FAIL.
8. Windows + PowerShell. Use paths and commands that work on Windows.
9. Never put secrets in committed files. API keys live only in backend/.env (git-ignored).
10. Communication style with Shreyas: concept-first explanations (the "why" before the "how"),
    detailed answers are welcome, and if he makes a grammar mistake, correct it briefly at the end.

---

## 3. File ownership (what M3 may touch)

M3 may create/edit ONLY these paths:

Backend (relative to repo root):
- backend/voice/__init__.py
- backend/voice/config.py              (M3 addition: env + logging config)
- backend/voice/stt_service.py
- backend/voice/tts_service.py
- backend/voice/audio_utils.py
- backend/voice/dev_server.py          (M3 addition: standalone dev/mock server, never used in prod)
- backend/voice/selftest.py            (M3 addition: self-test script)
- backend/voice/filler_cache/**        (M3 addition: pre-generated filler MP3s, committed)
- backend/.env                         (local only, never committed; only add M3 keys)

Frontend:
- frontend/src/services/audioRecorder.ts
- frontend/src/components/ExaminerPanel.tsx
- frontend/examiner-dev.html           (M3 addition: dev-only page, Vite serves it, not in prod build)
- frontend/src/dev/**                  (M3 addition: dev-only harness + mock turns)
- m3-playground/**                     (ONLY if frontend/ is not scaffolded yet — see TASKS B1)

Docs:
- docs/m3/**

Everything else belongs to someone else: requirements.txt, .env.example, .gitignore, main.py,
models/schemas.py, brain/*, ingestion/*, sandbox/*, demo_cache/*, package.json, vite.config.ts,
App.tsx, main.tsx, apiClient.ts, types/api.ts, other components. You may READ and IMPORT from
them. You may NOT edit them. If M3 needs a change there, record it in the task handoff under
"Requests for other members"; task J1 compiles these into docs/m3/NOTES_FOR_TEAM.md.

Installing Python/npm packages into the local environment is allowed (it does not edit
requirements.txt or package.json). npm packages must NOT be added to frontend/package.json — M3
frontend code uses only browser APIs + React, so no new npm packages should be needed.

---

## 4. The shared contract (from M1's backend/models/schemas.py)

TurnResponse (frozen by M1 — mirror these names exactly):

    session_id: str
    student_transcript: str
    verdict: 'start' | 'strong' | 'partial' | 'weak' | 'no_answer'
    ack_text: str            # e.g. "Good point on cosine similarity."
    question_text: str       # shown as text AND spoken aloud
    audio_base64: str        # MP3 bytes, base64, for instant playback ("" = no audio)
    topic: str
    depth_level: int         # 1..4
    highlight: Optional[CodeHighlight]   # {file_path, line_start, line_end}
    diagram_node_id: Optional[str]
    paper_excerpt: Optional[str]
    coding_challenge: Optional[CodingChallenge]
    done: bool = False

TurnRequest is NOT defined in the spec. M3's proposal (use M1's real one if schemas.py has it):

    session_id: str
    student_text: Optional[str]      # typed answer
    audio_base64: Optional[str]      # recorded answer, base64, no "data:" prefix
    audio_mime: Optional[str]        # e.g. "audio/webm;codecs=opus"

---

## 5. M3 interfaces (decided — implement exactly these names and signatures)

### 5.1 backend/voice/config.py
- Best-effort load of backend/.env (python-dotenv, wrapped in try/except so it never crashes).
- Constants read from env with defaults:
  GROQ_API_KEY (""), GROQ_STT_MODEL ("whisper-large-v3-turbo"), STT_TIMEOUT_S (10),
  TTS_VOICE ("en-IN-PrabhatNeural"), TTS_RATE ("+0%"), TTS_TIMEOUT_S (8),
  ELEVENLABS_API_KEY (""), ELEVENLABS_VOICE_ID (""), FILLER_CACHE_DIR (backend/voice/filler_cache)
- log = logging.getLogger("vivavoce.voice")

### 5.2 backend/voice/tts_service.py
    async def synthesize_speech(text: str) -> str
        # returns base64 MP3; returns "" on total failure; NEVER raises
        # provider chain: edge-tts (TTS_VOICE, TTS_RATE) -> ElevenLabs (only if key set) -> ""
        # in-memory LRU cache keyed by (voice, rate, speakable_text), max 128 entries
        # each provider wrapped in asyncio.wait_for(TTS_TIMEOUT_S); logs provider + milliseconds
    def synthesize_speech_sync(text: str) -> str          # asyncio.run wrapper for scripts only
    def to_speakable(text: str) -> str
        # text for the voice only (the card still shows the original):
        # strip markdown (backticks, *, #, >), remove "()" after identifiers,
        # snake_case underscores -> spaces, "L12-L20" / "lines 12-20" -> "lines 12 to 20",
        # collapse whitespace, cap at ~600 characters
    def build_spoken_text(ack_text: str, question_text: str) -> str
        # "ack. question" with clean punctuation; handles empty ack

### 5.3 backend/voice/audio_utils.py
    def detect_audio_format(audio_bytes: bytes) -> str
        # magic bytes -> 'webm' | 'wav' | 'ogg' | 'mp4' | 'mp3' | 'unknown'
    def is_probably_silent_or_too_short(audio_bytes: bytes, fmt: str | None = None) -> bool
        # empty or < 2 KB -> True; WAV: duration < 0.3 s or RMS below threshold -> True
    def trim_silence(wav_bytes: bytes, threshold_db: float = -40.0, pad_ms: int = 150) -> bytes
        # WAV PCM16 only, stdlib wave + array (no numpy); any other format returned unchanged
    def normalize_audio(audio_bytes: bytes, mime_type: str | None = None) -> tuple[bytes, str]
        # returns (bytes, filename) e.g. (b"...", "answer.webm"); trims silence for WAV
    FILLER_TEXTS: list[str]   # exactly 3 short clips:
        # "Let me check that line..."
        # "Interesting, checking your implementation..."
        # "Hmm, give me a second to think about that."
    async def warm_filler_cache() -> None
        # creates filler_cache/filler_1.mp3..filler_3.mp3 + fillers.json via synthesize_speech;
        # skips files that exist; never raises
    def get_filler_audio() -> str             # random filler as base64, "" if none
    def get_all_fillers() -> list[dict]       # [{"id": "filler_1", "text": "...", "audio_base64": "..."}]

### 5.4 backend/voice/stt_service.py
    async def transcribe_audio(audio_bytes: bytes, lang: str | None = "en",
                               domain_terms: list[str] | None = None,
                               mime_type: str | None = None) -> str
        # Groq AsyncGroq, model GROQ_STT_MODEL, temperature 0
        # pre-check with audio_utils: empty / silent / too short -> "" WITHOUT calling the API
        # normalize_audio gives the right filename extension for Groq
        # prompt = build_domain_prompt(domain_terms)
        # timeout STT_TIMEOUT_S, retry once on timeout/5xx, then return "" (log it); NEVER raises
        # no GROQ_API_KEY -> log a warning once, return ""
        # post-process: strip, drop known Whisper silence hallucinations
        #   ("thank you for watching", "thanks for watching", "subtitles by", "you", ".", etc.)
        #   when they are the WHOLE transcript -> ""
    def build_domain_prompt(domain_terms: list[str] | None) -> str
        # Hinglish-friendly style sentence, e.g. "Technical viva. The student may mix Hindi and
        # English, like 'haan, toh basically yeh function cosine similarity return karta hai'."
        # + up to 40 identifiers, total kept under ~600 characters (Whisper prompt limit)
    def transcribe_audio_sync(...same args...) -> str     # scripts only

### 5.5 backend/voice/__init__.py
Re-exports: synthesize_speech, synthesize_speech_sync, to_speakable, build_spoken_text,
transcribe_audio, transcribe_audio_sync, build_domain_prompt, get_filler_audio,
get_all_fillers, warm_filler_cache, voice_router.

voice_router = fastapi.APIRouter (JSON only — no multipart, so no python-multipart dependency):
- GET  /health      -> {"stt_ready": bool, "tts_provider": "edge-tts", "fillers": int}
- GET  /fillers     -> get_all_fillers()
- POST /transcribe  body {audio_base64, mime_type?, lang?, domain_terms?} -> {"text": str, "ms": int}
- POST /speak       body {text}                                           -> {"audio_base64": str, "ms": int}

M1 mounts it with: app.include_router(voice_router, prefix="/api/voice")

### 5.6 backend/voice/dev_server.py (dev only)
Standalone FastAPI app: `app`. Run from backend/ as: python -m uvicorn voice.dev_server:app --port 8000
- CORS for http://localhost:5173, http://127.0.0.1:5173, http://localhost:5174, http://127.0.0.1:5174
- mounts voice_router at /api/voice; warms filler cache on startup
- GET  /api/dev/start      -> first TurnResponse-shaped dict (verdict "start", depth 1)
- POST /api/viva/turn      -> MOCK of M1's endpoint: accepts TurnRequest proposal (§4);
  transcribes audio if present; picks the next canned question (6 questions cycling depth 1..4,
  last one done=true); verdict by simple rule (empty -> no_answer, > 40 chars -> strong, else
  partial); synthesizes build_spoken_text(ack, question); returns a TurnResponse-shaped dict.
  If backend/models/schemas.py exists, import TurnResponse (read-only) to validate the shape.

### 5.7 backend/voice/selftest.py
Run from backend/ as: python -m voice.selftest   -> prints PASS/FAIL/SKIP table, exit code 1 on any FAIL.

### 5.8 frontend/src/services/audioRecorder.ts
    export interface RecordedAudio { blob: Blob; base64: string /* no data: prefix */;
                                     mimeType: string; durationMs: number }
    export type RecorderStatus = 'idle' | 'requesting-permission' | 'recording' | 'denied'
                                 | 'unsupported' | 'error'
    export function usePushToTalkRecorder(options: {
        onRecordingComplete: (rec: RecordedAudio) => void;
        enabled?: boolean;          // default true
        bindSpacebar?: boolean;     // default true
        minDurationMs?: number;     // default 300 (shorter = discarded)
        maxDurationMs?: number;     // default 60000 (auto-stop)
        onTooShort?: () => void;
    }): { status: RecorderStatus; isRecording: boolean; error: string | null;
          startRecording(): void; stopRecording(): void; cancelRecording(): void;
          getInputLevel(): number /* 0..1 mic level */ }
    export interface AudioPlayback { done: Promise<void>; stop(): void;
                                     getLevel(): number /* 0..1 */; getProgress(): number /* 0..1 */ }
    export function playBase64Audio(b64: string, mimeType?: string /* 'audio/mpeg' */): AudioPlayback
    export function speakWithBrowserTTS(text: string): AudioPlayback   // fallback when audio_base64 === ""
    export function stopAllPlayback(): void
    export function unlockAudio(): void          // resume shared AudioContext on a user gesture
    export function blobToBase64(blob: Blob): Promise<string>

Spacebar rules: ignore event.repeat; ignore when focus is in input / textarea / select /
contenteditable or inside .monaco-editor; preventDefault when handled (stops page scroll).
Mime preference: audio/webm;codecs=opus -> audio/webm -> audio/mp4 -> browser default.
Keep one mic stream open while mounted (no permission prompt every press); release on unmount.
One shared AudioContext; only one playback at a time (new playback stops the old one).

### 5.9 frontend/src/components/ExaminerPanel.tsx
    export interface ExaminerTurnLike { session_id: string; student_transcript: string;
        verdict: 'start'|'strong'|'partial'|'weak'|'no_answer'; ack_text: string;
        question_text: string; audio_base64: string; topic: string; depth_level: number;
        done: boolean; [extra: string]: unknown }
      // If src/types/api.ts exists and exports TurnResponse, use that type instead (import type).
    export interface ExaminerPanelProps {
        initialTurn?: ExaminerTurnLike | null;
        onSubmitAudio: (audio: RecordedAudio) => Promise<ExaminerTurnLike>;
        onSubmitText: (text: string) => Promise<ExaminerTurnLike>;
        onTurn?: (turn: ExaminerTurnLike) => void;      // App uses it to drive IDE highlight etc.
        onRequestReport?: () => void;
        fillersUrl?: string;                            // default '/api/voice/fillers'
        disabled?: boolean;
    }
    export default function ExaminerPanel(props: ExaminerPanelProps)

The panel owns: recording, filler playback, speaking, the orb, transcript history, depth meter.
The parent (M4's App.tsx) owns API calls (through the two submit props) and the left workspace.
All sub-components (VoiceOrb, QuestionCard, DepthMeter, TranscriptHistory, PushToTalkButton,
TextFallbackInput) live inside ExaminerPanel.tsx because M3 owns only that one component file.
Styling: Tailwind classes, dark slate theme, fills the right 35% column, full height.
Panel states: idle | listening | thinking | speaking | done.

---

## 6. Handoff file template (every build task writes docs/m3/handoffs/<TASK_ID>.md)

    # Handoff <TASK_ID> — <task name>
    ## Project in one paragraph            (VivaVoce + M3's role, 3–5 lines)
    ## How Shreyas works                   (copy the 10 rules of CONTEXT §2 in short form)
    ## What this task did
    ## Files created / changed             (M3-owned only, with one line each)
    ## Public interface as implemented     (exact signatures; flag any difference from CONTEXT §5)
    ## How to test                         (what the agent ran + result; plain steps for Shreyas if he must act)
    ## Deviations from CONTEXT.md and why
    ## Requests for other members          (deps for requirements.txt, env vars, routes, props, etc.)
    ## Known issues / TODO
    ## What the next task in this lane must know
    ## Review                              (left empty — filled by the Claude reviewer)

---

## 7. Definition of done for any task
- Acceptance criteria in TASKS.md for that task are met and were actually tested by the agent.
- No file outside §3 was modified (check with git status).
- Handoff file written.
- The agent's final message ends with: READY FOR REVIEW: <TASK_ID>

