# VivaVoce M3 (Voice Pipeline) — Integration Notes for the Team

**Author:** Shreyas (M3 Voice Lead)  
**Date:** 2026-11-14  
**Git Branch:** `m3-voice`  
**Status:** Complete, Verified, Ready to Merge

---

## 1. Executive Summary

The Voice Pipeline (M3) is fully built, hardened, and verified end-to-end against live audio synthesis and transcription:
- **STT (Groq Whisper `whisper-large-v3-turbo`):** ~800ms transcription latency with domain keyword biasing (`cosine`, `dot product`, `embeddings`, `L2-norm`) and silence artifact filtering.
- **TTS (Edge-TTS `en-IN-PrabhatNeural`):** Cold synthesis ~1.0s, in-memory LRU cache ~0.08ms, ElevenLabs fallback support.
- **Filler Audio:** 3 pre-generated clips stored on disk (`filler_cache/`) and served via `/api/voice/fillers` for instant sub-200ms acoustic feedback while student answers are evaluated.
- **Frontend UI (`ExaminerPanel`):** Push-to-talk with Spacebar / touch hold, live audio-reactive `VoiceOrb` (canvas 60fps), word-by-word karaoke highlighting of examiner questions synced to audio progress, 4-level Bloom's depth meter, collapsible transcript history, text fallback, inline error banner with 'Retry', and barge-in.
- **Verification:** 15/15 checks pass in `python -m voice.selftest`, 46/46 unit tests pass in `test_b6.cjs`, 0 TypeScript errors (`tsc --noEmit`), and full automated multi-turn viva runs from Turn 1 to `done=True` in 817ms response latency.

---

## 2. Notes for M1 (Nishit — Team Lead & AI Brain Monolith)

### 2.1 Dependencies & Environment Variables
- `groq>=0.11.0` and `edge-tts>=6.1.12` are already present in `backend/requirements.txt`.
- `backend/.env` requires:
  ```env
  GROQ_API_KEY=gsk_...
  ```
- Optional voice config overrides (all have sensible defaults in `backend/voice/config.py`):
  ```env
  GROQ_STT_MODEL=whisper-large-v3-turbo
  STT_TIMEOUT_S=10
  TTS_VOICE=en-IN-PrabhatNeural
  TTS_RATE=+0%
  TTS_TIMEOUT_S=8
  ELEVENLABS_API_KEY=
  ELEVENLABS_VOICE_ID=
  ```

### 2.2 Mount the Voice Router in `backend/main.py`
Add two lines to `backend/main.py`:
```python
from backend.voice import voice_router, warm_filler_cache

# 1. In FastAPI lifespan / startup:
@asynccontextmanager
async def lifespan(app: FastAPI):
    await warm_filler_cache()
    yield

# 2. Mount voice router:
app.include_router(voice_router, prefix="/api/voice")
```
This automatically exposes:
- `GET  /api/voice/health` -> `{"stt_ready": bool, "tts_provider": "edge-tts", "fillers": 3}`
- `GET  /api/voice/fillers` -> `list[{"id": str, "text": str, "audio_base64": str}]`
- `POST /api/voice/transcribe` -> `{"text": str, "ms": int}` (validates base64, HTTP 400 on bad data)
- `POST /api/voice/speak` -> `{"audio_base64": str, "ms": int}` (edge-tts MP3)

### 2.3 Exact Signatures for `backend/main.py`
M3 exports all required functions from `backend.voice`:
```python
from backend.voice import (
    transcribe_audio,      # async def (audio_bytes, lang="en", domain_terms=None, mime_type=None, domain_prompt=None) -> str
    synthesize_speech,     # async def (text) -> str (base64 MP3; returns "" on error, NEVER raises)
    build_spoken_text,     # def (ack_text, question_text) -> str (clean punctuation merge)
    to_speakable,          # def (text) -> str (cleans markdown, snake_case, line ranges for voice)
)
```

#### Inside `POST /api/viva/turn`:
```python
# 1. Transcribe student audio (if submitted)
student_transcript = ""
if req.audio_base64 and req.audio_base64.strip():
    raw_b64 = req.audio_base64.strip()
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]
    audio_bytes = base64.b64decode(raw_b64)
    student_transcript = await transcribe_audio(
        audio_bytes=audio_bytes,
        mime_type=getattr(req, "audio_mime", None),  # TurnRequest has no audio_mime yet; format is sniffed from bytes
        domain_terms=[s.name for s in session.repo_index.symbols[:40]],
    )
elif req.student_text:
    student_transcript = req.student_text.strip()

# 2. Synthesize examiner speech for question card + audio playback
spoken_text = build_spoken_text(ack_text, question_text)
audio_base64 = await synthesize_speech(spoken_text)  # Returns base64 MP3, never throws
```

*Note on compatibility:* M1's existing adapter helpers in `backend/main.py` lines 398–440 (`_invoke_m3_stt` and `_invoke_m3_tts`) work as-is. `domain_prompt` is accepted as a comma-separated identifier string (what `_invoke_m3_stt` passes) and is merged into the Hinglish style prompt, capped at ~600 chars.

**Requests for M1:** (1) `voice_router` is NOT mounted in `main.py` yet — until it is, `GET /api/voice/fillers` 404s and the panel plays no fillers. (2) Optional: add `audio_mime: Optional[str] = None` to `TurnRequest`; the frontend already sends it (Pydantic currently ignores it). (3) Add the §2.1 voice vars to `.env.example` (A1 request).

---

## 3. Notes for M4 (Frontend Workspace & Layout Lead)

### 3.1 Mounting `ExaminerPanel` in `frontend/src/App.tsx`
`ExaminerPanel` is a self-contained component filling the right 35% column of the viva workspace:

```tsx
import ExaminerPanel from './components/ExaminerPanel'
import type { TurnResponse } from './types/api'
import type { RecordedAudio } from './services/audioRecorder'

// In App.tsx right column:
<aside className="min-w-0 lg:basis-[35%] flex flex-col h-full overflow-hidden bg-midnight-panel">
  <ExaminerPanel
    initialTurn={currentTurn}
    onSubmitAudio={handleAudioSubmit}
    onSubmitText={handleTextSubmit}
    onTurn={handleTurnUpdate}
    onRequestReport={handleOpenReportModal}
    fillersUrl="/api/voice/fillers"
    disabled={isBusy}
  />
</aside>
```

### 3.2 Component Props Contract
| Prop Name | Type | Description |
|-----------|------|-------------|
| `initialTurn` | `TurnResponse \| null` | Opening turn (from `POST /api/viva/start`). Spoken aloud automatically once on mount. |
| `onSubmitAudio` | `(rec: RecordedAudio) => Promise<TurnResponse>` | Called on PTT release. Body: `{ session_id, audio_base64: rec.base64, audio_mime: rec.mimeType }`. |
| `onSubmitText` | `(text: string) => Promise<TurnResponse>` | Called on typed answer submit. Body: `{ session_id, student_text: text }`. |
| `onTurn` | `(turn: TurnResponse) => void` | Called whenever a new turn arrives. M4 uses this to drive Monaco IDE line highlight (`turn.highlight`), paper node highlight, etc. |
| `onRequestReport` | `() => void` | Called when the student clicks "View report" after the viva reaches `done=True`. M4 opens `ReportModal`. |
| `fillersUrl` | `string` (optional) | Defaults to `"/api/voice/fillers"`. Pre-cached filler clips fetched once on mount. |
| `disabled` | `boolean` (optional) | Disables PTT and text input when workspace is busy. |

### 3.3 Spacebar PTT Behavior & Keyboard Accessibility
- **Push-to-Talk Spacebar Guard:** While `ExaminerPanel` is mounted, holding <kbd>Space</kbd> starts recording and calls `e.preventDefault()`. It also automatically blurs non-text controls (like checkboxes or buttons) page-wide so Space **never scrolls the page** and never triggers buttons accidentally.
- **Typing Protection:** Inside `<input>`, `<textarea>`, `contenteditable`, and Monaco Editor (`.monaco-editor`), Space works completely normally as a space character and does **not** trigger recording.
- **Button Activation:** To activate focused buttons or checkboxes via keyboard, students can press <kbd>Enter</kbd>.

### 3.4 Dev-Only Files to Ignore in Production Build
These files are M3 development harnesses and test runners:
- `frontend/examiner-dev.html` (Vite dev harness page)
- `frontend/src/dev/**` (mock turns & dev toolbar)
- `backend/voice/dev_server.py` (standalone dev server)
- `backend/voice/selftest.py` (unit test suite)

---

## 4. Ready-to-Send Team Message (Slack / Discord / WhatsApp)

```
Hey @Nishit @M2 @M4 — M3 Voice Pipeline is done and 100% verified! 🎉

Here is the quick TL;DR for integrating:

1. Backend (Nishit):
   - In requirements.txt: groq and edge-tts are already there.
   - In backend/main.py:
     from backend.voice import voice_router, warm_filler_cache
     app.include_router(voice_router, prefix="/api/voice")
   - In lifespan: await warm_filler_cache()
   - To transcribe: await transcribe_audio(audio_bytes, mime_type="audio/webm", domain_prompt=...)
   - To speak: audio_base64 = await synthesize_speech(build_spoken_text(ack, q))
   (Your helper hooks in main.py lines 398-440 are already 100% compatible!)

2. Frontend (M4):
   - Import ExaminerPanel from './components/ExaminerPanel'.
   - Drop it into App.tsx right 35% column with initialTurn, onSubmitAudio, onSubmitText, onTurn, and onRequestReport.
   - Note: Spacebar is captured page-wide for push-to-talk with preventDefault() (doesn't scroll the page; native typing in inputs & Monaco editor is preserved; Enter activates buttons).

You can preview the live voice examiner right now at:
http://localhost:5173/examiner-dev.html (backed by python -m uvicorn voice.dev_server:app --port 8000)
```

