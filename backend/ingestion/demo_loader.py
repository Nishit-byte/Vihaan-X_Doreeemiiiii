"""Offline demo repository and challenge caching loader for venue reliability."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from .config import DEMO_CACHE_DIR, DEMO_REPO_URL, WORK_DIR
from .models import AuthorStat, IngestionError, OwnedSymbol, RepoIndex
from .repo_parser import cleanup_repo

# In-memory caches for fast offline load (< 0.2 s)
_CACHED_REPO_INDEX: Optional[RepoIndex] = None
_CACHED_AUTHOR_MAP: Optional[dict[str, list[OwnedSymbol]]] = None
_CACHED_AUTHOR_STATS: Optional[list[AuthorStat]] = None
_CACHED_CHALLENGE: Optional[dict] = None
_MATERIALIZED_DIR: Optional[str] = None


def _reset_demo_cache() -> None:
    """Reset module-level in-memory cache (primarily used in tests)."""
    global _CACHED_REPO_INDEX, _CACHED_AUTHOR_MAP, _CACHED_AUTHOR_STATS, _CACHED_CHALLENGE, _MATERIALIZED_DIR
    _CACHED_REPO_INDEX = None
    _CACHED_AUTHOR_MAP = None
    _CACHED_AUTHOR_STATS = None
    _CACHED_CHALLENGE = None
    _MATERIALIZED_DIR = None


def _normalize_source(s: str) -> str:
    """Normalize a repo URL or name for case, trailing slashes, and .git extensions."""
    cleaned = s.strip().lower()
    while cleaned.endswith("/"):
        cleaned = cleaned[:-1]
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    while cleaned.endswith("/"):
        cleaned = cleaned[:-1]
    return cleaned


def is_demo_source(url_or_name: str) -> bool:
    """Check if the given URL or name corresponds to the bundled demo repository.

    Accepts DEMO_REPO_URL with or without .git, with or without trailing slash,
    any case, surrounding whitespace, and the word 'demo' (case-insensitive).
    """
    if not url_or_name or not isinstance(url_or_name, str):
        return False

    raw = url_or_name.strip()
    if not raw:
        return False

    if raw.lower() == "demo":
        return True

    norm_input = _normalize_source(raw)
    norm_demo = _normalize_source(DEMO_REPO_URL)

    if norm_input == norm_demo:
        return True

    # Handle comparisons if scheme was omitted in user input
    if norm_demo.startswith("https://"):
        demo_no_scheme = norm_demo[len("https://") :]
        input_no_scheme = (
            norm_input[len("https://") :]
            if norm_input.startswith("https://")
            else (
                norm_input[len("http://") :]
                if norm_input.startswith("http://")
                else norm_input
            )
        )
        if input_no_scheme == demo_no_scheme:
            return True
        if "/" in demo_no_scheme:
            demo_slug = demo_no_scheme.split("/", 1)[1]
            if input_no_scheme == demo_slug:
                return True

    return False


def load_demo_repo() -> tuple[RepoIndex, dict[str, list[OwnedSymbol]], list[AuthorStat]]:
    """Load cached RepoIndex, author map, and authorship stats for demo repo (< 0.2 s).

    Parses sample_repo_index.json and sample_repo_authors.json from DEMO_CACHE_DIR,
    caches parsed objects in memory after the first load, and returns safe deep
    copies with from_cache=True. Makes zero network calls.
    """
    global _CACHED_REPO_INDEX, _CACHED_AUTHOR_MAP, _CACHED_AUTHOR_STATS

    if _CACHED_REPO_INDEX is None or _CACHED_AUTHOR_MAP is None or _CACHED_AUTHOR_STATS is None:
        cache_path = Path(DEMO_CACHE_DIR)
        index_file = cache_path / "sample_repo_index.json"
        authors_file = cache_path / "sample_repo_authors.json"

        if not index_file.is_file():
            raise IngestionError(
                "Demo repository index cache file not found.",
                detail=f"Missing {index_file}",
            )
        if not authors_file.is_file():
            raise IngestionError(
                "Demo repository authors cache file not found.",
                detail=f"Missing {authors_file}",
            )

        try:
            index_text = index_file.read_text(encoding="utf-8")
            repo_idx = RepoIndex.model_validate_json(index_text)
            repo_idx.from_cache = True
        except Exception as e:
            raise IngestionError(
                "Failed to parse demo repository index cache.",
                detail=str(e),
            ) from e

        try:
            authors_data = json.loads(authors_file.read_text(encoding="utf-8"))
            raw_author_map = authors_data.get("author_map", {})
            raw_stats = authors_data.get("authorship_stats", [])

            parsed_author_map = {
                author: [OwnedSymbol.model_validate(sym) for sym in syms]
                for author, syms in raw_author_map.items()
            }
            parsed_stats = [AuthorStat.model_validate(stat) for stat in raw_stats]
        except Exception as e:
            raise IngestionError(
                "Failed to parse demo repository authors cache.",
                detail=str(e),
            ) from e

        _CACHED_REPO_INDEX = repo_idx
        _CACHED_AUTHOR_MAP = parsed_author_map
        _CACHED_AUTHOR_STATS = parsed_stats

    # Return safe deep copies so mutations cannot corrupt cache
    copy_index = _CACHED_REPO_INDEX.model_copy(deep=True)
    copy_index.from_cache = True
    copy_author_map = {
        author: [sym.model_copy(deep=True) for sym in syms]
        for author, syms in _CACHED_AUTHOR_MAP.items()
    }
    copy_stats = [stat.model_copy(deep=True) for stat in _CACHED_AUTHOR_STATS]

    return copy_index, copy_author_map, copy_stats


def _is_valid_repo_dir(dir_path: str | Path) -> bool:
    """Check if a materialized repository folder exists and has expected git artifacts."""
    p = Path(dir_path)
    if not p.is_dir():
        return False
    git_dir = p / ".git"
    if not git_dir.exists():
        return False
    # Verify at least one key sample repository file exists
    if not (p / "similarity.py").is_file():
        return False
    return True


def materialize_demo_repo() -> str:
    """Clone sample_repo.bundle into a deterministic folder inside WORK_DIR.

    Reuses the existing directory if present and valid; re-clones cleanly if
    missing or deleted. Uses Windows-safe git subprocess flags so it never hangs.
    """
    global _MATERIALIZED_DIR

    target_dir = os.path.join(WORK_DIR, "studysync")

    if _MATERIALIZED_DIR and os.path.abspath(target_dir) == _MATERIALIZED_DIR:
        if _is_valid_repo_dir(target_dir):
            return _MATERIALIZED_DIR

    if _is_valid_repo_dir(target_dir):
        _MATERIALIZED_DIR = os.path.abspath(target_dir)
        return _MATERIALIZED_DIR

    # Missing, deleted, or corrupted: clean up any partial artifacts
    if os.path.exists(target_dir):
        cleanup_repo(target_dir)

    os.makedirs(WORK_DIR, exist_ok=True)

    bundle_path = Path(DEMO_CACHE_DIR) / "sample_repo.bundle"
    if not bundle_path.is_file():
        raise IngestionError(
            "Demo repository git bundle not found in demo_cache.",
            detail=f"Missing bundle at {bundle_path}",
        )

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "echo"

    try:
        proc = subprocess.run(
            ["git", "clone", str(bundle_path), str(target_dir)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        cleanup_repo(target_dir)
        raise IngestionError(
            "Materializing demo repository from bundle timed out.",
            detail=str(e),
        ) from e
    except FileNotFoundError as e:
        cleanup_repo(target_dir)
        raise IngestionError(
            "Git command-line executable was not found on this system.",
            detail=str(e),
        ) from e
    except Exception as e:
        cleanup_repo(target_dir)
        raise IngestionError(
            "Failed to materialize demo repository from bundle.",
            detail=str(e),
        ) from e

    if proc.returncode != 0:
        cleanup_repo(target_dir)
        raise IngestionError(
            "Failed to clone demo repository from bundle.",
            detail=proc.stderr.strip(),
        )

    _MATERIALIZED_DIR = os.path.abspath(target_dir)
    return _MATERIALIZED_DIR


def load_demo_challenge() -> dict:
    """Load the pre-packaged coding challenge for the demo repository.

    Loads sample_repo_challenge.json from DEMO_CACHE_DIR, caches in memory
    after the first load, and returns a safe deep copy.
    """
    global _CACHED_CHALLENGE

    if _CACHED_CHALLENGE is None:
        cache_path = Path(DEMO_CACHE_DIR)
        challenge_file = cache_path / "sample_repo_challenge.json"

        if not challenge_file.is_file():
            raise IngestionError(
                "Demo challenge cache file not found.",
                detail=f"Missing {challenge_file}",
            )

        try:
            _CACHED_CHALLENGE = json.loads(
                challenge_file.read_text(encoding="utf-8")
            )
        except Exception as e:
            raise IngestionError(
                "Failed to parse demo challenge cache.",
                detail=str(e),
            ) from e

    return copy.deepcopy(_CACHED_CHALLENGE)
