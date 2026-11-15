# VivaVoce Offline Demo Replay Mode (P0-2.4)

This directory (`backend/demo_cache/replay/`) stores recorded HTTP session responses and extracted audio assets for 100% offline demo reliability during live hackathon judging.

---

## 1. Why Replay Mode Exists

Hackathon venue Wi-Fi is notoriously unpredictable, and live LLM endpoints (Gemini, Speech-to-Text, Text-to-Speech) can suffer from latency spikes, rate limits, or network timeouts during a 3-minute pitch.

Replay mode guarantees:
1. **Zero External Dependencies**: Zero calls to Google Gemini, GitHub, or voice APIs during judging.
2. **Deterministic Playback**: Identical spoken audio responses, AST-grounded questions, and report scores on every run.
3. **Instantaneous Latency**: All API responses resolve in < 10 ms from local disk cache.
4. **Repeatability**: Playback cursors can be reset via `POST /api/replay/reset` for back-to-back judge demos without restarting the server.

---

## 2. Directory Structure

```
backend/demo_cache/replay/
├── README.md            # This guide
├── session.jsonl        # Recorded JSON request-response pairs (one per line)
└── audio/               # Extracted MP3 audio clips (<n>.mp3)
    ├── 1.mp3
    ├── 2.mp3
    └── ...
```

During recording:
- Every `audio_base64` payload at any nesting depth is extracted, saved to `audio/<n>.mp3`, and replaced in `session.jsonl` with `@audio:<n>.mp3`.

During replay:
- The middleware restores `@audio:<n>.mp3` placeholders to complete base64 strings so frontend Monaco / Voice components receive the exact expected payloads.

---

## 3. How to Record at Integration (Checkpoint 5 / Hour 20)

> **Important**: Recording should be performed once the merged FastAPI backend is stable and all team modules (M1, M2, M3, M4) are wired together.

> **Middleware order in `main.py`**: call `app.add_middleware(ReplayMiddleware)` **before**
> `app.add_middleware(CORSMiddleware, ...)`. Starlette makes the last-added middleware the
> outermost, and CORS must wrap Replay; otherwise browser preflights get 409 and replayed
> responses lack `Access-Control-Allow-Origin`, so the frontend sees every call fail.

> **Re-recording**: recording *appends* to `session.jsonl`. Delete `session.jsonl` and
> `audio/` first (or call `ReplayStore().clear()`). Error responses (4xx/5xx) are recorded and
> replayed too, so redo the run if anything failed during it.

1. In `backend/.env`, enable recording mode:
   ```env
   DEMO_RECORD=1
   DEMO_REPLAY=0
   ```
2. Start the merged backend server:
   ```powershell
   cd backend
   .\.venv\Scripts\uvicorn main:app --port 8000
   ```
3. Open the frontend UI and run through the scripted demo viva from start to finish:
   - Ingest the demo repository (`POST /api/ingest-repo`)
   - Complete Viva turns L1 through L4 (`POST /api/viva/turn`)
   - Execute the code mutation fix challenge (`POST /api/run-code`)
   - Generate the final competency report (`GET /api/report/{id}`)
4. Stop the backend server (`Ctrl + C`).
5. Verify that `session.jsonl` and `audio/*.mp3` exist in `backend/demo_cache/replay/`.

---

## 4. How to Replay in the Live Demo (Wi-Fi Off)

1. In `backend/.env`, switch to replay mode:
   ```env
   DEMO_RECORD=0
   DEMO_REPLAY=1
   ```
2. **Turn off Wi-Fi** or disconnect Ethernet on the presentation laptop.
3. Start the backend server:
   ```powershell
   cd backend
   .\.venv\Scripts\uvicorn main:app --port 8000
   ```
4. Start the frontend:
   ```powershell
   cd frontend
   npm run dev
   ```
5. Run the live demo:
   - `ReplayMiddleware` intercepts all `/api/*` endpoints.
   - Downstream LLMs and backend handlers are never called.
   - If a route's recorded queue is exhausted, the middleware returns `409 Conflict` with `{error, detail}`.

---

## 5. Control Endpoints

`ReplayMiddleware` handles these endpoints directly:

- **`GET /api/replay/status`**:
  Returns current mode, total recorded calls, and remaining queue counts per normalized route.
  ```json
  {
    "mode": "replay",
    "recorded_calls": 5,
    "remaining": {
      "POST /api/ingest-repo": 0,
      "POST /api/viva/turn": 2,
      "GET /api/report/{id}": 1
    }
  }
  ```

- **`POST /api/replay/reset`**:
  Resets all queue cursors back to the beginning so the demonstration can be re-run immediately.
  ```json
  {
    "status": "ok",
    "message": "Replay cursors reset"
  }
  ```
