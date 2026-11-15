"""Replay store for offline demo recording and session replay."""

import asyncio
import base64
import copy
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

try:
    from ..ingestion.config import REPLAY_DIR
except ImportError:
    from ingestion.config import REPLAY_DIR


class ReplayStore:
    """Store and replay HTTP request-response pairs for offline demo reliability."""

    def __init__(self, replay_dir: str = REPLAY_DIR) -> None:
        effective_dir = (
            os.getenv("REPLAY_DIR", replay_dir)
            if replay_dir == REPLAY_DIR
            else replay_dir
        )
        self.replay_dir = Path(effective_dir)
        self.session_file = self.replay_dir / "session.jsonl"
        self.audio_dir = self.replay_dir / "audio"
        self._queues: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._cursors: dict[tuple[str, str], int] = {}
        self._audio_counter: int = 0
        self._loaded: bool = False
        self._lock: Optional[asyncio.Lock] = None

    @property
    def lock(self) -> asyncio.Lock:
        """Return or lazily create an asyncio lock for store writes."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _ensure_loaded(self) -> None:
        """Ensure session.jsonl entries are indexed into memory queues."""
        if self._loaded:
            return
        self._queues.clear()
        if self.session_file.exists():
            with open(self.session_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        m = str(entry.get("method", "GET")).upper()
                        p = str(
                            entry.get("normalized_path")
                            or self.normalize_path(str(entry.get("path", "")))
                        )
                        key = (m, p)
                        if key not in self._queues:
                            self._queues[key] = []
                        self._queues[key].append(entry)
                    except Exception:
                        continue
        self._loaded = True

    def _save_audio(self, b64_str: str) -> str:
        """Decode base64 audio and save to replay/audio/<n>.mp3, returning filename."""
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        if self._audio_counter == 0 and self.audio_dir.exists():
            existing = [
                int(p.stem)
                for p in self.audio_dir.glob("*.mp3")
                if p.stem.isdigit()
            ]
            self._audio_counter = max(existing, default=0)
        self._audio_counter += 1
        filename = f"{self._audio_counter}.mp3"
        dest_file = self.audio_dir / filename
        dest_file.write_bytes(base64.b64decode(b64_str))
        return filename

    @staticmethod
    def _is_canonical_b64(value: str) -> bool:
        """True if value re-encodes to exactly itself, so moving it to a file is lossless."""
        try:
            decoded = base64.b64decode(value, validate=True)
            return base64.b64encode(decoded).decode("ascii") == value
        except Exception:
            return False

    def _load_audio(self, filename: str) -> str:
        """Load audio file bytes and return base64 encoded string."""
        target = self.audio_dir / filename
        if not target.exists():
            target = self.replay_dir / filename
        if not target.exists():
            return ""
        data = target.read_bytes()
        return base64.b64encode(data).decode("ascii")

    def _extract_audio(self, data: Any) -> Any:
        """Recursively replace audio_base64 string values with @audio:<filename>."""
        if isinstance(data, dict):
            new_dict: dict[str, Any] = {}
            for k, v in data.items():
                if (
                    k == "audio_base64"
                    and isinstance(v, str)
                    and v
                    and self._is_canonical_b64(v)
                ):
                    fn = self._save_audio(v)
                    new_dict[k] = f"@audio:{fn}"
                else:
                    new_dict[k] = self._extract_audio(v)
            return new_dict
        elif isinstance(data, list):
            return [self._extract_audio(item) for item in data]
        return data

    def _rehydrate_audio(self, data: Any) -> Any:
        """Recursively restore @audio:<filename> placeholders to base64 audio."""
        if isinstance(data, dict):
            new_dict: dict[str, Any] = {}
            for k, v in data.items():
                if k == "audio_base64" and isinstance(v, str) and v.startswith("@audio:"):
                    fn = v[len("@audio:") :].strip()
                    new_dict[k] = self._load_audio(fn)
                else:
                    new_dict[k] = self._rehydrate_audio(v)
            return new_dict
        elif isinstance(data, list):
            return [self._rehydrate_audio(item) for item in data]
        return data

    def normalize_path(self, path: str) -> str:
        """Normalize parameterized API paths (e.g. /api/report/abc123 -> /api/report/{id})."""
        if not path:
            return ""
        clean = path.split("?")[0].split("#")[0].strip()
        if len(clean) > 1:
            clean = clean.rstrip("/")
        clean = re.sub(r"^/api/report/[^/]+$", "/api/report/{id}", clean)
        return clean

    def record(self, method: str, path: str, status: int, body: dict) -> None:
        """Record an API response to session.jsonl, extracting audio to files."""
        self._ensure_loaded()
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        norm_path = self.normalize_path(path)
        clean_body = self._extract_audio(copy.deepcopy(body))
        entry = {
            "method": method.upper(),
            "path": path,
            "normalized_path": norm_path,
            "status": status,
            "body": clean_body,
        }
        with open(self.session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()

        key = (method.upper(), norm_path)
        if key not in self._queues:
            self._queues[key] = []
        self._queues[key].append(entry)

    def next(self, method: str, path: str) -> Optional[tuple[int, dict]]:
        """Return the next recorded response for this method and normalized path."""
        self._ensure_loaded()
        norm_path = self.normalize_path(path)
        key = (method.upper(), norm_path)
        queue = self._queues.get(key, [])
        cursor = self._cursors.get(key, 0)
        if cursor < len(queue):
            item = queue[cursor]
            self._cursors[key] = cursor + 1
            rehydrated = self._rehydrate_audio(copy.deepcopy(item["body"]))
            return (int(item["status"]), rehydrated)
        return None

    def reset(self) -> None:
        """Reset replay playback pointers to the beginning of the recorded session."""
        self._cursors.clear()
        self._loaded = False
        self._ensure_loaded()

    def status(self) -> dict:
        """Return status dictionary of recorded sessions and remaining queue counts."""
        self._ensure_loaded()
        total_recorded = sum(len(q) for q in self._queues.values())
        remaining: dict[str, int] = {}
        routes: dict[str, dict[str, int]] = {}
        for (m, p), q in self._queues.items():
            route_key = f"{m} {p}"
            cursor = self._cursors.get((m, p), 0)
            rem = max(0, len(q) - cursor)
            remaining[route_key] = rem
            routes[route_key] = {
                "total": len(q),
                "cursor": cursor,
                "remaining": rem,
            }
        return {
            "recorded_calls": total_recorded,
            "remaining": remaining,
            "routes": routes,
        }

    def clear(self) -> None:
        """Clear all recorded sessions and audio files."""
        self._cursors.clear()
        self._queues.clear()
        self._loaded = False
        self._audio_counter = 0
        if self.session_file.exists():
            try:
                self.session_file.unlink()
            except Exception:
                pass
        if self.audio_dir.exists():
            for p in self.audio_dir.glob("*.mp3"):
                try:
                    p.unlink()
                except Exception:
                    pass
