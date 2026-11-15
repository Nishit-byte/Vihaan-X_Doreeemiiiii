"""Tests for Task A5: Demo loader, in-memory caching, materialization, and cache wiring."""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ingestion.config import DEMO_CACHE_DIR, DEMO_REPO_URL
from ingestion.demo_loader import (
    _reset_demo_cache,
    is_demo_source,
    load_demo_challenge,
    load_demo_repo,
    materialize_demo_repo,
)
from ingestion.models import AuthorStat, IngestionError, OwnedSymbol, RepoIndex
from ingestion.repo_parser import cleanup_repo, clone_and_index_repo


@pytest.fixture(autouse=True)
def clean_cache_state():
    """Ensure in-memory cache is reset before each test."""
    _reset_demo_cache()
    yield
    _reset_demo_cache()


# ---------------------------------------------------------------------------
# 1. is_demo_source tests
# ---------------------------------------------------------------------------


def test_is_demo_source_variants():
    """Verify is_demo_source recognizes all URL variants and 'demo' case-insensitively."""
    variants = [
        DEMO_REPO_URL,
        f"{DEMO_REPO_URL}.git",
        f"{DEMO_REPO_URL}/",
        f"{DEMO_REPO_URL}.git/",
        f"  {DEMO_REPO_URL}  ",
        f"  {DEMO_REPO_URL}.git/  ",
        DEMO_REPO_URL.upper(),
        f"{DEMO_REPO_URL}.GIT",
        f"{DEMO_REPO_URL.upper()}/",
        "demo",
        "DEMO",
        "Demo",
        "  demo  ",
        "  DEMO  ",
        # Scheme-less variants
        DEMO_REPO_URL.replace("https://", ""),
        f"{DEMO_REPO_URL.replace('https://', '')}.git",
        "shreyas-269/vivavoce-demo-repo",
    ]
    for candidate in variants:
        assert is_demo_source(candidate) is True, f"Failed to match demo source: {candidate!r}"


def test_is_demo_source_negative_cases():
    """Verify is_demo_source rejects non-demo repositories, random strings, and invalid types."""
    negatives = [
        "https://github.com/octocat/Hello-World",
        "https://github.com/shreyas-269/other-repo",
        "https://github.com/shreyas-269/vivavoce-demo-repo-fork",
        "random_repo",
        "demox",
        "demo_repo",
        "not_demo",
        "",
        "   ",
        None,
        12345,
    ]
    for candidate in negatives:
        assert is_demo_source(candidate) is False, f"Incorrectly matched non-demo source: {candidate!r}"


# ---------------------------------------------------------------------------
# 2. load_demo_repo tests (timing, data integrity, zero network)
# ---------------------------------------------------------------------------


def test_load_demo_repo_timing_and_content():
    """Verify load_demo_repo loads valid models in < 0.2 s (cold and warm)."""
    # Cold load measurement
    t0 = time.perf_counter()
    repo_index, author_map, stats = load_demo_repo()
    cold_time = time.perf_counter() - t0

    assert cold_time < 0.2, f"Cold load time {cold_time:.4f} s exceeded 0.2 s threshold"
    print(f"\n[A5 Benchmark] load_demo_repo cold load: {cold_time * 1000:.2f} ms")

    # Warm load measurement
    t1 = time.perf_counter()
    repo_index2, author_map2, stats2 = load_demo_repo()
    warm_time = time.perf_counter() - t1

    assert warm_time < 0.2, f"Warm load time {warm_time:.4f} s exceeded 0.2 s threshold"
    print(f"[A5 Benchmark] load_demo_repo warm load: {warm_time * 1000:.2f} ms")

    # Verify RepoIndex properties
    assert isinstance(repo_index, RepoIndex)
    assert repo_index.from_cache is True
    assert repo_index.source_url == DEMO_REPO_URL
    assert repo_index.commit_sha != ""
    assert len(repo_index.files) >= 5
    assert len(repo_index.file_tree) >= 5
    assert repo_index.get_file("similarity.py") is not None
    assert repo_index.get_file("models.py") is not None

    # Verify author_map
    assert isinstance(author_map, dict)
    assert "Aman Verma" in author_map
    assert "Priya Nair" in author_map
    assert "Rohan Gupta" in author_map
    for author, symbols in author_map.items():
        assert len(symbols) > 0
        for s in symbols:
            assert isinstance(s, OwnedSymbol)
            assert 0.0 <= s.share <= 1.0

    # Verify authorship stats
    assert isinstance(stats, list)
    assert len(stats) == 3
    total_share = sum(st.share_of_lines for st in stats)
    assert abs(total_share - 1.0) <= 0.001
    for st in stats:
        assert isinstance(st, AuthorStat)
        assert st.lines > 0


def test_load_demo_repo_zero_network_calls(monkeypatch):
    """Verify load_demo_repo makes zero network calls."""
    def _fail_network(*args, **kwargs):
        raise RuntimeError("Network activity strictly forbidden during demo cache load")

    # Guard low-level socket connections
    monkeypatch.setattr(socket, "socket", _fail_network)

    repo_index, author_map, stats = load_demo_repo()
    assert repo_index.from_cache is True
    assert len(author_map) > 0
    assert len(stats) == 3


def test_load_demo_repo_mutation_isolation():
    """Verify mutations on returned RepoIndex, author_map, and stats do not corrupt cached state."""
    idx1, map1, stats1 = load_demo_repo()

    # Mutate returned objects aggressively
    idx1.repo_id = "CORRUPTED_ID"
    idx1.files[0].content = "MUTATED_CONTENT"
    idx1.file_tree.append("corrupted_file.py")
    idx1.from_cache = False

    map1["Aman Verma"][0].lines_owned = 999999
    map1["MALICIOUS_AUTHOR"] = []

    stats1[0].lines = -999
    stats1.clear()

    # Re-fetch from cache
    idx2, map2, stats2 = load_demo_repo()

    assert idx2.repo_id != "CORRUPTED_ID"
    assert idx2.files[0].content != "MUTATED_CONTENT"
    assert "corrupted_file.py" not in idx2.file_tree
    assert idx2.from_cache is True

    assert map2["Aman Verma"][0].lines_owned != 999999
    assert "MALICIOUS_AUTHOR" not in map2

    assert len(stats2) == 3
    assert stats2[0].lines > 0


# ---------------------------------------------------------------------------
# 3. materialize_demo_repo tests
# ---------------------------------------------------------------------------


def test_materialize_demo_repo_lifecycle():
    """Verify materialize_demo_repo creates a valid repo directory, reuses it, and recovers if deleted."""
    # First materialization
    t0 = time.perf_counter()
    dir1 = materialize_demo_repo()
    mat_time = time.perf_counter() - t0
    print(f"\n[A5 Benchmark] materialize_demo_repo initial clone: {mat_time * 1000:.2f} ms")

    assert os.path.isdir(dir1)
    assert (Path(dir1) / ".git").is_dir()
    assert (Path(dir1) / "similarity.py").is_file()
    assert (Path(dir1) / "models.py").is_file()
    assert (Path(dir1) / "utils" / "vector_ops.py").is_file()

    # Second call must reuse existing valid directory (< 5 ms)
    t1 = time.perf_counter()
    dir2 = materialize_demo_repo()
    reuse_time = time.perf_counter() - t1
    print(f"[A5 Benchmark] materialize_demo_repo reuse: {reuse_time * 1000:.2f} ms")

    assert dir2 == dir1
    assert reuse_time < 0.05

    # Delete directory and verify clean recovery
    cleanup_repo(dir1)
    assert not os.path.exists(dir1)

    dir3 = materialize_demo_repo()
    assert os.path.isdir(dir3)
    assert (Path(dir3) / ".git").is_dir()
    assert (Path(dir3) / "similarity.py").is_file()


# ---------------------------------------------------------------------------
# 4. load_demo_challenge tests
# ---------------------------------------------------------------------------


def test_load_demo_challenge_content_and_isolation():
    """Verify load_demo_challenge returns required challenge keys and protects cache against mutation."""
    t0 = time.perf_counter()
    chal1 = load_demo_challenge()
    chal_time = time.perf_counter() - t0
    print(f"\n[A5 Benchmark] load_demo_challenge load: {chal_time * 1000:.2f} ms")

    assert isinstance(chal1, dict)
    for expected_key in [
        "description",
        "target_file",
        "function",
        "starter_code",
        "test_code",
        "reference_solution",
    ]:
        assert expected_key in chal1
        assert isinstance(chal1[expected_key], str)
        assert len(chal1[expected_key]) > 0

    assert chal1["target_file"] == "similarity.py"
    assert chal1["function"] == "cosine_similarity"

    # Mutate dictionary
    chal1["starter_code"] = "MUTATED_CODE"
    chal1["INJECTED_KEY"] = "INJECTED_VALUE"

    # Re-fetch
    chal2 = load_demo_challenge()
    assert chal2["starter_code"] != "MUTATED_CODE"
    assert "INJECTED_KEY" not in chal2


# ---------------------------------------------------------------------------
# 5. clone_and_index_repo wiring tests
# ---------------------------------------------------------------------------


def test_clone_and_index_repo_demo_source_wiring(monkeypatch):
    """Verify clone_and_index_repo with use_cache=True loads demo source in < 0.2 s without calling clone_repo."""
    def _raise_on_network_clone(github_url, dest_dir=None):
        raise AssertionError(f"clone_repo should NEVER be called for demo source! (got {github_url})")

    monkeypatch.setattr("ingestion.repo_parser.clone_repo", _raise_on_network_clone)

    # Test with canonical DEMO_REPO_URL
    t0 = time.perf_counter()
    idx_url = clone_and_index_repo(DEMO_REPO_URL, use_cache=True)
    url_duration = time.perf_counter() - t0
    print(f"\n[A5 Benchmark] clone_and_index_repo(DEMO_REPO_URL) duration: {url_duration * 1000:.2f} ms")

    assert url_duration < 0.2, f"clone_and_index_repo took {url_duration:.4f} s (expected < 0.2 s)"
    assert idx_url.from_cache is True
    assert idx_url.local_path != ""
    assert os.path.isdir(idx_url.local_path)
    assert (Path(idx_url.local_path) / "similarity.py").is_file()

    # Test with string 'demo'
    t1 = time.perf_counter()
    idx_demo = clone_and_index_repo("demo", use_cache=True)
    demo_duration = time.perf_counter() - t1
    print(f"[A5 Benchmark] clone_and_index_repo('demo') duration: {demo_duration * 1000:.2f} ms")

    assert demo_duration < 0.2, f"clone_and_index_repo('demo') took {demo_duration:.4f} s (expected < 0.2 s)"
    assert idx_demo.from_cache is True
    assert idx_demo.local_path == idx_url.local_path

    # Test with variant 'DEMO'
    idx_upper = clone_and_index_repo("DEMO", use_cache=True)
    assert idx_upper.from_cache is True


def test_clone_and_index_repo_cache_disabled_behavior(monkeypatch):
    """Verify use_cache=False does not use demo cache and attempts network / validation."""
    # With 'demo' and use_cache=False, validate_github_url should reject 'demo'
    with pytest.raises(IngestionError) as exc_info:
        clone_and_index_repo("demo", use_cache=False)
    assert "Invalid repository host" in exc_info.value.user_message or "Invalid GitHub URL" in exc_info.value.user_message

    # With DEMO_REPO_URL and use_cache=False, it should attempt clone_repo
    called_clone = []

    def _mock_clone(github_url, dest_dir=None):
        called_clone.append(github_url)
        raise RuntimeError("clone_repo was invoked as expected when use_cache=False")

    monkeypatch.setattr("ingestion.repo_parser.clone_repo", _mock_clone)

    with pytest.raises(RuntimeError, match="clone_repo was invoked"):
        clone_and_index_repo(DEMO_REPO_URL, use_cache=False)

    assert len(called_clone) == 1
