"""Replay package for VivaVoce M2: offline demo session recording and playback."""

import os
try:
    from ..ingestion.config import DEMO_RECORD, DEMO_REPLAY
except ImportError:
    from ingestion.config import DEMO_RECORD, DEMO_REPLAY


def is_replay_enabled() -> bool:
    """Return True if offline demo replay mode is enabled."""
    val = os.getenv("DEMO_REPLAY")
    if val is None:
        return DEMO_REPLAY
    return val.strip().lower() in ("1", "true", "yes", "on")


def is_record_enabled() -> bool:
    """Return True if demo session recording mode is enabled."""
    val = os.getenv("DEMO_RECORD")
    if val is None:
        return DEMO_RECORD
    return val.strip().lower() in ("1", "true", "yes", "on")


from .middleware import ReplayMiddleware
from .store import ReplayStore

__all__ = [
    "ReplayStore",
    "ReplayMiddleware",
    "is_replay_enabled",
    "is_record_enabled",
]
