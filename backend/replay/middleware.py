"""Pure ASGI middleware for capturing or replaying VivaVoce API sessions."""

import asyncio
import json
import os
from typing import Any, Callable, Optional

try:
    from ..ingestion.config import REPLAY_DIR
except ImportError:
    from ingestion.config import REPLAY_DIR

try:
    from . import is_record_enabled, is_replay_enabled
except ImportError:
    from replay import is_record_enabled, is_replay_enabled

from .store import ReplayStore


class ReplayMiddleware:
    """Pure ASGI middleware for offline demo recording and replay."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._store: Optional[ReplayStore] = None
        self._write_lock: Optional[asyncio.Lock] = None

    @property
    def store(self) -> ReplayStore:
        """Return or lazily initialize the backing ReplayStore."""
        if self._store is None:
            state_store = getattr(
                getattr(self.app, "state", None), "replay_store", None
            )
            if state_store is not None and isinstance(state_store, ReplayStore):
                self._store = state_store
            else:
                replay_dir = os.getenv("REPLAY_DIR", REPLAY_DIR)
                self._store = ReplayStore(replay_dir=replay_dir)
        return self._store

    @store.setter
    def store(self, value: ReplayStore) -> None:
        self._store = value

    @property
    def write_lock(self) -> asyncio.Lock:
        """Return or lazily initialize an asyncio lock for concurrent store writes."""
        if self._write_lock is None:
            self._write_lock = asyncio.Lock()
        return self._write_lock

    async def _send_json(
        self, send: Callable, status: int, data: dict[str, Any]
    ) -> None:
        """Send a complete JSON response over ASGI."""
        body_bytes = json.dumps(data).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body_bytes)).encode("ascii")),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body_bytes,
                "more_body": False,
            }
        )

    async def __call__(
        self, scope: dict[str, Any], receive: Callable, send: Callable
    ) -> None:
        """Handle ASGI request: intercept for replay, record responses, or pass through."""
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        raw_path: str = scope.get("path", "")
        method: str = scope.get("method", "GET").upper()
        clean_path = raw_path.rstrip("/") if len(raw_path) > 1 else raw_path

        # Direct replay control endpoints (handled directly by middleware)
        if clean_path == "/api/replay/status" and method == "GET":
            mode = (
                "replay"
                if is_replay_enabled()
                else ("record" if is_record_enabled() else "inert")
            )
            status_data = {"mode": mode, **self.store.status()}
            await self._send_json(send, 200, status_data)
            return

        if clean_path == "/api/replay/reset" and method == "POST":
            self.store.reset()
            await self._send_json(
                send, 200, {"status": "ok", "message": "Replay cursors reset"}
            )
            return

        replay_on = is_replay_enabled()
        record_on = is_record_enabled()

        # Inert mode: neither record nor replay enabled
        if not replay_on and not record_on:
            await self.app(scope, receive, send)
            return

        # Only touches /api/* routes; non-/api routes pass through untouched
        if not raw_path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        # REPLAY MODE: Never call downstream app for /api/*
        if replay_on:
            norm_path = self.store.normalize_path(raw_path)
            res = self.store.next(method, raw_path)
            if res is not None:
                status_code, body = res
                await self._send_json(send, status_code, body)
                return
            else:
                error_body = {
                    "error": "Replay exhausted",
                    "detail": f"No more recorded responses for {method} {norm_path}",
                }
                await self._send_json(send, 409, error_body)
                return

        # RECORD MODE: Passes requests through, captures /api/* JSON responses
        response_status: int = 200
        is_json_response: bool = False
        body_chunks: list[bytes] = []

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal response_status, is_json_response, body_chunks
            msg_type = message.get("type")

            if msg_type == "http.response.start":
                response_status = int(message.get("status", 200))
                headers = message.get("headers", [])
                for name, val in headers:
                    if (
                        name.lower() == b"content-type"
                        and b"application/json" in val.lower()
                    ):
                        is_json_response = True
                        break
                await send(message)
            elif msg_type == "http.response.body":
                if is_json_response:
                    body_chunks.append(message.get("body", b""))
                await send(message)
            else:
                await send(message)

        await self.app(scope, receive, send_wrapper)

        # After response completes, record JSON body if applicable
        if is_json_response and body_chunks:
            full_body_bytes = b"".join(body_chunks)
            try:
                body_dict = json.loads(full_body_bytes.decode("utf-8"))
                async with self.write_lock:
                    self.store.record(
                        method, raw_path, response_status, body_dict
                    )
            except Exception:
                pass
