# M3 VOICE PIPELINE — TASK LIST

Two lanes run at the same time. Inside a lane, tasks run in order. Lanes never wait on each other
until the join tasks (J1, J2). Each task = one fresh build chat (Antigravity, Gemini 3.8 Flash)
+ one review chat (Claude Code, Sonnet 5.5 or Opus 5.5).

| ID | Lane | Task | Depends on | Review model |
|----|------|------|-----------|--------------|
| S0 | —    | Docs setup + repo scan (this setup step) | — | none |
| A1 | A    | Voice module scaffold, config & local deps | S0 | Sonnet 5.5 |
| A2 | A    | TTS service (edge-tts + fallback + speakable text) | A1 | Sonnet 5.5 |
| A3 | A    | Audio utils (format detect, silence, trim, filler cache) | A2 | Sonnet 5.5 |
| A4 | A    | STT service (Groq Whisper + domain prompt + hallucination filter) | A3 | Sonnet 5.5 |
| A5 | A    | voice_router + dev_server mock backend | A4 | Sonnet 5.5 |
| A6 | A    | Self-test script + hardening | A5 | Sonnet 5.5 |
| B1 | B    | Frontend recon, dev harness page, stubs & mock turns | S0 | Sonnet 5.5 |
| B2 | B    | Push-to-talk recorder hook (mic + Spacebar) | B1 | Opus 5.5 |
| B3 | B    | Audio playback, levels & browser-TTS fallback | B2 | Sonnet 5.5 |
| B4 | B    | ExaminerPanel static layout (card, depth meter, transcript, inputs) | B3 | Sonnet 5.5 |
| B5 | B    | Voice orb animation | B4 | Sonnet 5.5 |
| B6 | B    | Turn-flow wiring (filler, submit, speak, word sync, barge-in, errors) | B5 | Opus 5.5 |
| J1 | Join | End-to-end run against dev_server + NOTES_FOR_TEAM.md | A6, B6 | Sonnet 5.5 |
| J2 | Join | Final integration-readiness review (Claude only) | J1 | Opus 5.5 |

---

## S0 — Docs setup + repo scan
Create docs/m3/ (CONTEXT.md, TASKS.md, STATUS.md, handoffs/), scan the repo and write
docs/m3/REPO_STATE.md, create/check out git branch m3-voice. No code.

---

## LANE A — BACKEND VOICE (Python, backend/voice/)

### A1 — Voice module scaffold, config & local deps
Description: Create the backend/voice/ package with config.py and stub versions of every module,
using the exact names and signatures from CONTEXT §5 (stubs return "" / [] / None). Set up the
local Python environment and install M3's packages into it without touching requirements.txt.
Details:
- Use the existing backend virtualenv if REPO_STATE.md lists one; otherwise create backend/.venv.
- Install: groq, edge-tts, httpx, fastapi, uvicorn, python-dotenv.
- config.py per CONTEXT §5.1. Create backend/.env with placeholder M3 lines if it does not exist
  (GROQ_API_KEY=, TTS_VOICE=en-IN-PrabhatNeural). Confirm .env is git-ignored; if not, record a
  request for M1 and do not commit it.
- If backend/ does not exist yet, create only backend/voice/ (nothing else in backend/).
Acceptance: from backend/, `python -c "import voice; print('ok')"` works; all stub functions exist
with the right signatures; handoff lists packages + env vars for M1.

### A2 — TTS service
Description: Implement backend/voice/tts_service.py per CONTEXT §5.2.
Details:
- edge-tts: edge_tts.Communicate(text, voice, rate=...).stream(), collect "audio" chunks to bytes.
- ElevenLabs fallback only when ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are set: httpx POST
  https://api.elevenlabs.io/v1/text-to-speech/{voice_id}, header xi-api-key, model
  eleven_flash_v2_5, MP3 output.
- LRU cache, timeouts, logging of provider + ms, never raises.
- to_speakable test cases (must hold): no backticks/underscores/asterisks/# in output;
  "`compute_cosine_similarity()`" -> "compute cosine similarity"; "L12-L20" -> "lines 12 to 20";
  "lines 12-20" -> "lines 12 to 20".
Acceptance: synthesize_speech on a sample question returns base64 that decodes to MP3 (starts
with ID3 or an MP3 frame header); first-call and cached-call latency printed in the handoff;
empty text returns "" without a network call.

### A3 — Audio utils + filler cache
Description: Implement backend/voice/audio_utils.py per CONTEXT §5.3 and generate the filler clips.
Details:
- Magic bytes: WebM/Matroska 1A 45 DF A3; WAV "RIFF"...."WAVE"; Ogg "OggS"; MP4 "ftyp" at byte 4;
  MP3 "ID3" or 0xFF 0xFB/0xF3/0xF2.
- trim_silence with stdlib wave + array only. Test it on a generated WAV
  (0.5 s silence + 1 s 440 Hz tone + 0.5 s silence): output must be shorter but keep the tone.
- Run warm_filler_cache once so backend/voice/filler_cache/filler_1..3.mp3 + fillers.json exist
  (these get committed so the demo works offline).
Acceptance: 3 filler MP3s exist and play; get_all_fillers returns 3 items with non-empty base64;
format detection correct for all 5 formats (use tiny synthetic headers); silence check works.

### A4 — STT service (Groq Whisper)
Description: Implement backend/voice/stt_service.py per CONTEXT §5.4.
Details:
- Needs GROQ_API_KEY in backend/.env. If missing: STOP and tell Shreyas in plain steps —
  go to console.groq.com, sign in, API Keys -> Create, copy it, paste after GROQ_API_KEY= in
  backend/.env, save, then reply "done".
- groq.AsyncGroq().audio.transcriptions.create(file=(filename, bytes), model=..., prompt=...,
  language=lang, temperature=0, response_format="json").
- Round-trip test (no microphone needed): synthesize a technical sentence with A2's TTS ->
  transcribe it -> print both texts + STT latency. Also one Hinglish-style sentence.
- Empty bytes and a silent WAV must return "" with NO API call.
Acceptance: round-trip transcript is close to the original (identifiers recognisable); latency
recorded in handoff; no exception escapes for bad key / no network (test by temporarily using a
bogus key in-process, not by editing .env).

### A5 — voice_router + dev_server mock backend
Description: Fill backend/voice/__init__.py with the re-exports and voice_router (CONTEXT §5.5)
and build backend/voice/dev_server.py (CONTEXT §5.6) so the frontend lane can test against a
real voice backend without M1's main.py.
Details:
- JSON bodies via small Pydantic models defined inside __init__.py / dev_server.py (not schemas.py).
- 6 canned questions about a fictional repo (e.g. utils/similarity.py), depth 1,1,2,3,4,4 with
  topics and ack texts; the last turn has done=true.
- Start server from backend/ with python -m uvicorn voice.dev_server:app --port 8000, then test
  every endpoint with a small Python httpx script (agent runs it), including a /api/viva/turn
  call with audio_base64 taken from a TTS clip.
Acceptance: all endpoints return 200 with the documented shapes; /api/viva/turn returns
TurnResponse-shaped JSON with non-empty audio_base64; CORS headers present for localhost:5173.

### A6 — Self-test script + hardening
Description: Write backend/voice/selftest.py (CONTEXT §5.7) covering every backend function, and
fix whatever it uncovers.
Checks: to_speakable cases; TTS latency (cold + cached); 3 concurrent synthesize calls; filler
files present; format detection; silence -> "" without API; hallucination filter; STT round-trip
(SKIP if no key); bogus-key path returns "" (no exception); voice_router endpoints via FastAPI
TestClient; Windows event-loop sanity (no "Event loop is closed" errors).
Acceptance: `python -m voice.selftest` from backend/ exits 0 and prints the table; output pasted
into the handoff.

---

## LANE B — FRONTEND VOICE UI (TypeScript/React)

### B1 — Frontend recon, dev harness, stubs & mock turns
Description: Decide where M3 frontend code is developed, create the dev harness page, stub the
two M3 files with the exact exported types from CONTEXT §5.8–5.9, and create mock turns.
Details:
- Read docs/m3/REPO_STATE.md. Mode (a): frontend/package.json exists with react + vite ->
  create frontend/examiner-dev.html (loads /src/dev/examinerDev.tsx). Vite serves any root HTML
  file in dev, so http://localhost:5173/examiner-dev.html works without touching vite.config.ts
  or main.tsx. Import M4's global CSS (e.g. src/index.css) if it exists so Tailwind applies.
  Mode (b): frontend not scaffolded -> create m3-playground/ (Vite react-ts + Tailwind, port 5174)
  with the same folder layout (src/services, src/components, src/dev) so files can later be copied
  1:1 into frontend/.
- Dev page layout: 65% left placeholder ("Workspace — M4"), 35% right column mounting
  ExaminerPanel; a small debug drawer for later tasks.
- src/dev/mockTurns.ts: 6 TurnResponse-like turns (start, strong, partial, weak, no_answer,
  done), depth 1..4, audio_base64 "" (browser TTS will speak them).
- If src/types/api.ts exists and exports TurnResponse, ExaminerPanel uses it (import type).
- No new npm packages in frontend/package.json.
Acceptance: dev page loads with no console errors (check with Antigravity's browser if
available); TypeScript compiles for M3 files; handoff states which mode (a/b) and the URL.

### B2 — Push-to-talk recorder hook
Description: Implement usePushToTalkRecorder + blobToBase64 in audioRecorder.ts per CONTEXT §5.8.
Details: MediaRecorder with mime preference list; start(250) timeslice; keep the mic stream open
while mounted; AnalyserNode on the mic for getInputLevel(); Spacebar rules (repeat, inputs,
contenteditable, .monaco-editor, preventDefault); min/max duration; cancel (Esc) support;
permission denied -> status 'denied'; no MediaRecorder -> 'unsupported'; clean up on unmount.
Add a "Recorder debug" box to the dev page: status, live level bar, last clip duration/size/mime,
and a play-back button (object URL) for the last clip.
Shreyas test steps (put in handoff): open the dev page, allow mic, hold Space and talk, release,
press play-back; type in a text box and press Space (must NOT record).
Acceptance: all rules above hold in Chrome and Edge; base64 has no "data:" prefix.

### B3 — Audio playback, levels & browser-TTS fallback
Description: Implement playBase64Audio, speakWithBrowserTTS, stopAllPlayback, unlockAudio.
Details: base64 -> ArrayBuffer -> decodeAudioData -> AudioBufferSourceNode -> AnalyserNode ->
destination; getProgress from AudioContext time; getLevel = RMS 0..1; one playback at a time;
done resolves on end or stop. Browser TTS: prefer an en-IN voice, else en-US; progress from
'boundary' charIndex; simulated level while speaking. unlockAudio on first pointerdown/keydown.
Dev page: "Play MP3 file" (file picker -> base64 -> play) and "Speak with browser TTS" buttons,
each with a live level + progress bar.
Acceptance: both paths play, progress goes 0 -> 1, stop() works mid-play, starting a second
playback stops the first, no "AudioContext was not allowed to start" warnings after a click.

### B4 — ExaminerPanel static layout
Description: Build the visual panel with mock data (no recording/speaking logic yet).
Sub-components inside ExaminerPanel.tsx: header (title + status pill), orb placeholder,
QuestionCard (topic chip, depth chip, muted ack_text, bold large question_text, aria-live polite),
DepthMeter (L1 Recall, L2 Comprehension, L3 Analysis, L4 Evaluation; active segment highlighted,
animated change), TranscriptHistory (collapsible; examiner question + student transcript + verdict
badge: strong green, partial amber, weak red, no_answer gray), PushToTalkButton (press-and-hold
with mouse/touch; label "Hold Space to answer"), TextFallbackInput (Enter submits, Shift+Enter
newline), done state ("Viva complete" + "View report" button -> onRequestReport).
Dev page: buttons to step through mockTurns and switch panel states.
Acceptance: looks clean at 1366x768 and 1920x1080 in the 35% column, no overflow, dark theme,
keyboard accessible.

### B5 — Voice orb
Description: Build VoiceOrb (inside ExaminerPanel.tsx) driven by a levelSource: () => number prop.
Details: canvas (or SVG with refs) + requestAnimationFrame; smoothed scale 1 + level*0.35;
per-state look — idle: slow breathing slate/indigo; listening: emerald, reacts to mic level;
thinking: amber rotating dashed ring; speaking: indigo/violet ripples reacting to playback level;
no React re-render per frame; loop stops on unmount; prefers-reduced-motion -> static.
Dev page: state switcher + fake level slider, plus "use mic level" (B2) and "use playback level" (B3).
Acceptance: smooth, no console warnings, CPU stays low when idle.

### B6 — Turn-flow wiring
Description: Make the panel fully functional per CONTEXT §5.9 using B2, B3, B5.
Flow: initialTurn spoken on mount (after unlockAudio) -> idle -> Space/hold = listening ->
release = thinking: play a random filler instantly (fillers fetched once from fillersUrl, silently
ignored if it fails) and call onSubmitAudio -> response: stop filler, push to history, call onTurn,
speak audio_base64 (or browser TTS if "") = speaking, with word-by-word "karaoke" bolding of
ack + question synced to getProgress() -> idle. Typed answers go through onSubmitText the same way.
Barge-in: pressing Space while speaking stops playback and starts recording. Esc cancels a recording.
Errors: submit rejects -> inline error with "Retry" that resends the same recording/text;
empty student_transcript or verdict no_answer -> "Didn't catch that — try again or type";
mic denied -> text input becomes the primary input. No double submit while thinking. done=true
-> done state.
Dev page: mock submit functions (900 ms delay, next mockTurn) wired to the panel.
Acceptance: full mock viva runs from start to done using voice and using text; barge-in, retry
and no_answer paths all demonstrated; Shreyas test steps in handoff.

---

## JOIN TASKS

### J1 — End-to-end run against dev_server + NOTES_FOR_TEAM.md
Description: Connect Lane B's dev page to Lane A's dev_server and run a real voice viva; then
write the integration notes for M1 and M4.
Details:
- Dev page toggle "Real backend": GET http://localhost:8000/api/dev/start for initialTurn;
  submits POST http://localhost:8000/api/viva/turn {session_id, audio_base64, audio_mime} or
  {session_id, student_text}; fillersUrl http://localhost:8000/api/voice/fillers.
- If backend/models/schemas.py now defines TurnRequest, align the dev_server mock and the notes
  with its real field names.
- Log "release -> first audio" latency in the console; target under 2.5 s.
- docs/m3/NOTES_FOR_TEAM.md: For M1 — packages for requirements.txt, env vars for .env.example,
  the include_router line, exact code to call transcribe_audio / synthesize_speech /
  build_spoken_text / warm_filler_cache inside main.py and /api/viva/turn, proposed TurnRequest.
  For M4 — how to mount <ExaminerPanel/> in App.tsx's right column, the props and onTurn usage,
  types to add to api.ts, the dev-only files they can ignore. Plus a short ready-to-send team message.
- Collect all "Requests for other members" from handoffs A1–B6 into the notes.
Acceptance: Shreyas completes a real spoken viva (start -> done) on the dev page; latency noted;
NOTES_FOR_TEAM.md complete.

### J2 — Final integration-readiness review (Claude Code, Opus 5.5)
Description: Whole-workstream review: ownership check across the branch, run selftest, read all
M3 files against CONTEXT §5, demo-day failure modes (no Wi-Fi, no Groq key, mic denied, Safari),
and a merge checklist. No Gemini build step.
