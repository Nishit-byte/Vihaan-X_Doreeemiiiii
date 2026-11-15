"""Tests for TASK B6: Replay mode store and pure ASGI middleware."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from replay import (
    ReplayMiddleware,
    ReplayStore,
    is_record_enabled,
    is_replay_enabled,
)


def _make_sample_audio_b64(tag: str = "sample") -> str:
    """Generate deterministic dummy base64 audio payload."""
    raw_audio = f"ID3\x04\x00\x00\x00fake-mp3-stream-{tag}".encode("utf-8")
    return base64.b64encode(raw_audio).decode("ascii")


def _build_toy_app() -> FastAPI:
    """Build a toy FastAPI app with representative VivaVoce routes."""
    app = FastAPI()

    # Route 1: ingest-repo
    @app.post("/api/ingest-repo")
    async def ingest_repo(req: Request) -> dict[str, Any]:
        return {
            "session_id": "sess-toy-101",
            "repo_name": "studysync",
            "files": ["main.py", "utils.py"],
            "authors": ["Aman", "Priya"],
        }

    # Route 2: viva turn (returns audio_base64)
    turn_counter = {"count": 0}

    @app.post("/api/viva/turn")
    async def viva_turn(req: Request) -> dict[str, Any]:
        turn_counter["count"] += 1
        t = turn_counter["count"]
        return {
            "session_id": "sess-toy-101",
            "turn": t,
            "question_text": f"Grounded question for turn {t}",
            "audio_base64": _make_sample_audio_b64(f"turn-{t}"),
            "done": t >= 3,
        }

    # Route 3: report/{id} (returns report + audio_base64)
    @app.get("/api/report/{id}")
    async def get_report(id: str) -> dict[str, Any]:
        return {
            "session_id": id,
            "overall_score": 94.5,
            "audio_base64": _make_sample_audio_b64("closing-remark"),
            "summary": "Demonstrated strong understanding of cosine similarity.",
        }

    # Route 4: Non-/api route (should pass through untouched)
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # Route 5: Non-JSON /api route (should pass through untouched)
    @app.get("/api/plain-text")
    async def plain_text() -> PlainTextResponse:
        return PlainTextResponse("Hello, raw plain text!")

    app.add_middleware(ReplayMiddleware)
    return app


def test_normalize_path():
    """Verify normalize_path maps parameterized routes and cleans whitespace/slashes."""
    store = ReplayStore()
    assert store.normalize_path("/api/report/abc123") == "/api/report/{id}"
    assert store.normalize_path("/api/report/abc123/") == "/api/report/{id}"
    assert (
        store.normalize_path("/api/report/sess-xyz-987?filter=all")
        == "/api/report/{id}"
    )
    assert store.normalize_path("/api/report/{id}") == "/api/report/{id}"
    assert store.normalize_path("/api/viva/turn") == "/api/viva/turn"
    assert store.normalize_path("/api/viva/turn/") == "/api/viva/turn"
    assert store.normalize_path("/api/ingest-repo") == "/api/ingest-repo"
    assert store.normalize_path("/health") == "/health"
    assert store.normalize_path("") == ""


def test_record_and_replay_session_with_swapped_handlers(tmp_path, monkeypatch):
    """Core B6 acceptance test: record 5 calls, swap handlers to raise, replay identical responses."""
    # Point replay directory to isolated tmp_path
    monkeypatch.setenv("REPLAY_DIR", str(tmp_path))

    # 1. Enable RECORD MODE
    monkeypatch.setenv("DEMO_RECORD", "1")
    monkeypatch.setenv("DEMO_REPLAY", "0")
    assert is_record_enabled() is True
    assert is_replay_enabled() is False

    app = _build_toy_app()
    client = TestClient(app)

    # Make 5 recorded calls
    # Call 1: ingest-repo
    r1 = client.post("/api/ingest-repo", json={"github_url": "demo"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["repo_name"] == "studysync"

    # Call 2: turn 1
    r2 = client.post("/api/viva/turn", json={"student_text": "start"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["turn"] == 1
    assert d2["audio_base64"] == _make_sample_audio_b64("turn-1")

    # Call 3: turn 2
    r3 = client.post("/api/viva/turn", json={"student_text": "answer 1"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["turn"] == 2
    assert d3["audio_base64"] == _make_sample_audio_b64("turn-2")

    # Call 4: turn 3
    r4 = client.post("/api/viva/turn", json={"student_text": "answer 2"})
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["turn"] == 3
    assert d4["audio_base64"] == _make_sample_audio_b64("turn-3")

    # Call 5: report
    r5 = client.get("/api/report/sess-toy-101")
    assert r5.status_code == 200
    d5 = r5.json()
    assert d5["overall_score"] == 94.5
    assert d5["audio_base64"] == _make_sample_audio_b64("closing-remark")

    # Verify disk files created in tmp_path
    session_file = tmp_path / "session.jsonl"
    audio_dir = tmp_path / "audio"
    assert session_file.exists()
    assert audio_dir.exists()

    # Read session.jsonl lines
    lines = [
        json.loads(line)
        for line in session_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 5

    # Verify that in session.jsonl, audio_base64 was replaced by @audio:<file>
    assert lines[1]["body"]["audio_base64"] == "@audio:1.mp3"
    assert lines[2]["body"]["audio_base64"] == "@audio:2.mp3"
    assert lines[3]["body"]["audio_base64"] == "@audio:3.mp3"
    assert lines[4]["body"]["audio_base64"] == "@audio:4.mp3"

    # Verify actual audio files exist on disk
    assert (audio_dir / "1.mp3").exists()
    assert (audio_dir / "2.mp3").exists()
    assert (audio_dir / "3.mp3").exists()
    assert (audio_dir / "4.mp3").exists()

    # 2. Switch to REPLAY MODE
    monkeypatch.setenv("DEMO_RECORD", "0")
    monkeypatch.setenv("DEMO_REPLAY", "1")
    assert is_record_enabled() is False
    assert is_replay_enabled() is True

    # Swap ALL route handlers to ASGI callables that raise RuntimeError
    # This definitively proves downstream app handlers are never invoked for /api/* !
    def make_exploder(route_path: str):
        async def exploder(scope, receive, send):
            raise RuntimeError(
                f"Downstream app handler for {route_path} called during replay!"
            )

        return exploder

    for route in app.routes:
        route.app = make_exploder(getattr(route, "path", "unknown"))

    # Create fresh client in replay mode
    replay_client = TestClient(app)

    # Replay Call 1
    replay_r1 = replay_client.post(
        "/api/ingest-repo", json={"github_url": "demo"}
    )
    assert replay_r1.status_code == 200
    assert replay_r1.json() == d1

    # Replay Call 2
    replay_r2 = replay_client.post(
        "/api/viva/turn", json={"student_text": "start"}
    )
    assert replay_r2.status_code == 200
    assert replay_r2.json() == d2
    assert replay_r2.json()["audio_base64"] == d2["audio_base64"]

    # Replay Call 3
    replay_r3 = replay_client.post(
        "/api/viva/turn", json={"student_text": "answer 1"}
    )
    assert replay_r3.status_code == 200
    assert replay_r3.json() == d3
    assert replay_r3.json()["audio_base64"] == d3["audio_base64"]

    # Replay Call 4
    replay_r4 = replay_client.post(
        "/api/viva/turn", json={"student_text": "answer 2"}
    )
    assert replay_r4.status_code == 200
    assert replay_r4.json() == d4
    assert replay_r4.json()["audio_base64"] == d4["audio_base64"]

    # Replay Call 5 (even with different report id parameter, normalized path matches)
    replay_r5 = replay_client.get("/api/report/sess-any-id-999")
    assert replay_r5.status_code == 200
    assert replay_r5.json() == d5
    assert replay_r5.json()["audio_base64"] == d5["audio_base64"]

    # 3. Exhausted queue -> 409
    replay_r6 = replay_client.post("/api/viva/turn", json={})
    assert replay_r6.status_code == 409
    err = replay_r6.json()
    assert "error" in err
    assert "detail" in err
    assert "Replay" in err["error"]

    # 4. Reset -> returns 200, and queues replay from start
    reset_resp = replay_client.post("/api/replay/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "ok"

    # Now calling viva/turn again returns turn 1 response!
    reset_turn1 = replay_client.post("/api/viva/turn", json={})
    assert reset_turn1.status_code == 200
    assert reset_turn1.json()["turn"] == 1
    assert reset_turn1.json()["audio_base64"] == d2["audio_base64"]

    # 5. Status endpoint
    status_resp = replay_client.get("/api/replay/status")
    assert status_resp.status_code == 200
    stat = status_resp.json()
    assert stat["mode"] == "replay"
    assert stat["recorded_calls"] == 5
    assert "remaining" in stat
    assert "POST /api/viva/turn" in stat["remaining"]
    assert stat["remaining"]["POST /api/viva/turn"] == 2  # 3 total - 1 called

    # 6. Non-/api route is NOT intercepted by replay middleware, reaching downstream exploder!
    with pytest.raises(
        RuntimeError, match="Downstream app handler for /health called"
    ):
        replay_client.get("/health")


def test_inert_mode_and_non_api_pass_through(tmp_path, monkeypatch):
    """Verify that when DEMO_RECORD and DEMO_REPLAY are unset, middleware is completely inert."""
    monkeypatch.setenv("REPLAY_DIR", str(tmp_path))
    monkeypatch.setenv("DEMO_RECORD", "0")
    monkeypatch.setenv("DEMO_REPLAY", "0")
    assert is_record_enabled() is False
    assert is_replay_enabled() is False

    app = _build_toy_app()
    client = TestClient(app)

    # Healthy check passes to downstream handler
    h_resp = client.get("/health")
    assert h_resp.status_code == 200
    assert h_resp.json() == {"status": "ok"}

    # Ingest repo passes to downstream handler
    ing_resp = client.post("/api/ingest-repo", json={})
    assert ing_resp.status_code == 200
    assert ing_resp.json()["repo_name"] == "studysync"

    # Status endpoint still works
    stat = client.get("/api/replay/status").json()
    assert stat["mode"] == "inert"

    # No session file should have been recorded
    assert not (tmp_path / "session.jsonl").exists()


def test_streaming_and_non_json_not_recorded(tmp_path, monkeypatch):
    """Verify non-JSON responses (e.g. plain text, stream) pass through without recording."""
    monkeypatch.setenv("REPLAY_DIR", str(tmp_path))
    monkeypatch.setenv("DEMO_RECORD", "1")
    monkeypatch.setenv("DEMO_REPLAY", "0")

    app = _build_toy_app()
    client = TestClient(app)

    # Call plain text endpoint
    resp = client.get("/api/plain-text")
    assert resp.status_code == 200
    assert resp.text == "Hello, raw plain text!"

    # Session file should not exist or have 0 entries
    session_file = tmp_path / "session.jsonl"
    if session_file.exists():
        assert session_file.read_text(encoding="utf-8").strip() == ""


def test_nested_audio_extraction_and_rehydration(tmp_path):
    """Verify extraction and rehydration of audio_base64 at arbitrary depth in dicts/lists."""
    store = ReplayStore(replay_dir=str(tmp_path))
    audio_1 = _make_sample_audio_b64("nested-1")
    audio_2 = _make_sample_audio_b64("nested-2")
    audio_3 = _make_sample_audio_b64("nested-3")

    payload = {
        "session_id": "sess-deep",
        "turn": {
            "title": "Nested turn",
            "audio_base64": audio_1,
        },
        "history": [
            {"id": "h1", "audio_base64": audio_2},
            {"id": "h2", "audio_base64": audio_3},
        ],
        "empty_audio": {"audio_base64": ""},
    }

    # Record payload
    store.record("POST", "/api/viva/turn", 200, payload)

    # Next call
    result = store.next("POST", "/api/viva/turn")
    assert result is not None
    status, rehydrated = result
    assert status == 200
    assert rehydrated["turn"]["audio_base64"] == audio_1
    assert rehydrated["history"][0]["audio_base64"] == audio_2
    assert rehydrated["history"][1]["audio_base64"] == audio_3
    assert rehydrated["empty_audio"]["audio_base64"] == ""


def test_store_clear_and_reset(tmp_path):
    """Verify ReplayStore clear and reset behaviors."""
    store = ReplayStore(replay_dir=str(tmp_path))
    store.record("GET", "/api/test", 200, {"key": "val1"})
    store.record("GET", "/api/test", 200, {"key": "val2"})

    # Advance cursor once
    res1 = store.next("GET", "/api/test")
    assert res1 is not None and res1[1]["key"] == "val1"

    status_before = store.status()
    assert status_before["recorded_calls"] == 2
    assert status_before["remaining"]["GET /api/test"] == 1

    # Reset cursor
    store.reset()
    status_after = store.status()
    assert status_after["remaining"]["GET /api/test"] == 2

    res_after_reset = store.next("GET", "/api/test")
    assert res_after_reset is not None and res_after_reset[1]["key"] == "val1"

    # Clear everything
    store.clear()
    assert not (tmp_path / "session.jsonl").exists()
    assert store.status()["recorded_calls"] == 0
    assert store.next("GET", "/api/test") is None


def test_audio_data_url_and_unpadded_handling(tmp_path):
    """Verify audio extraction handles data: URLs and strange padding."""
    store = ReplayStore(replay_dir=str(tmp_path))
    raw_bytes = b"ID3\x04\x00data-url-audio-sample"
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    data_url = f"data:audio/mp3;base64,{b64}"

    store.record("POST", "/api/viva/turn", 200, {"audio_base64": data_url})

    # Non-canonical base64 (data: URL) stays inline so replay is byte-identical
    assert not (tmp_path / "audio" / "1.mp3").exists()
    _, rehydrated = store.next("POST", "/api/viva/turn")
    assert rehydrated["audio_base64"] == data_url


def test_concurrent_recording_lock(tmp_path, monkeypatch):
    """Verify concurrent requests in record mode coordinate writes without file corruption."""
    import httpx

    monkeypatch.setenv("REPLAY_DIR", str(tmp_path))
    monkeypatch.setenv("DEMO_RECORD", "1")
    monkeypatch.setenv("DEMO_REPLAY", "0")

    app = _build_toy_app()

    async def _run_concurrent():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            tasks = [
                client.post(
                    "/api/ingest-repo", json={"github_url": f"repo-{i}"}
                )
                for i in range(12)
            ]
            return await asyncio.gather(*tasks)

    responses = asyncio.run(_run_concurrent())
    assert len(responses) == 12
    for r in responses:
        assert r.status_code == 200

    session_file = tmp_path / "session.jsonl"
    assert session_file.exists()
    lines = [
        line.strip()
        for line in session_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 12

