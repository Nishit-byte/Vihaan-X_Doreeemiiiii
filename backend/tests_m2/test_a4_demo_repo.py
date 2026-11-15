"""Tests for Task A4: Demo repo 'studysync' build script, bundle, planted bug, and challenge."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from demo_cache.build_sample_repo import build_sample_repo
from ingestion.config import DEMO_CACHE_DIR, DEMO_REPO_URL
from ingestion.models import AuthorStat, OwnedSymbol, RepoIndex


@pytest.fixture(scope="module")
def demo_cache_paths():
    """Ensure sample repo is built and return dictionary of artifact paths."""
    cache_dir = Path(DEMO_CACHE_DIR)
    bundle_file = cache_dir / "sample_repo.bundle"
    index_file = cache_dir / "sample_repo_index.json"
    authors_file = cache_dir / "sample_repo_authors.json"
    challenge_file = cache_dir / "sample_repo_challenge.json"

    # If any artifact is missing, run the build script
    if not (
        bundle_file.exists()
        and index_file.exists()
        and authors_file.exists()
        and challenge_file.exists()
    ):
        build_sample_repo()

    return {
        "bundle": bundle_file,
        "index": index_file,
        "authors": authors_file,
        "challenge": challenge_file,
    }


def test_artifacts_exist(demo_cache_paths):
    """Verify all four demo cache artifact files exist and are non-empty."""
    for key, path in demo_cache_paths.items():
        assert path.is_file(), f"Artifact '{key}' missing at {path}"
        assert path.stat().st_size > 0, f"Artifact '{key}' is empty: {path}"


def test_bundle_size_under_200kb(demo_cache_paths):
    """Verify sample_repo.bundle is within reasonable size limits (< 200 KB)."""
    bundle_size = demo_cache_paths["bundle"].stat().st_size
    assert (
        0 < bundle_size < 200 * 1024
    ), f"Bundle size {bundle_size} bytes exceeds 200 KB limit"


def test_bundle_clones_cleanly_with_commits_and_authors(demo_cache_paths, tmp_path):
    """Verify the bundle clones into a functional repository with expected commits and authors."""
    clone_dest = tmp_path / "cloned_studysync"
    subprocess.run(
        ["git", "clone", str(demo_cache_paths["bundle"]), str(clone_dest)],
        check=True,
        capture_output=True,
    )

    # Check key files exist
    expected_files = [
        "models.py",
        "similarity.py",
        "ranking.py",
        "data_loader.py",
        "cli.py",
        "utils/__init__.py",
        "utils/vector_ops.py",
    ]
    for rel_path in expected_files:
        assert (clone_dest / rel_path).is_file(), f"Expected file {rel_path} missing in cloned repo"

    # Check commit count (between 12 and 15)
    rev_count = int(
        subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"], cwd=clone_dest, text=True
        ).strip()
    )
    assert 12 <= rev_count <= 15, f"Expected 12-15 commits, found {rev_count}"

    # Check authors in git log
    log_output = subprocess.check_output(
        ["git", "log", "--format=%an <%ae>"], cwd=clone_dest, text=True
    )
    assert "Aman Verma <aman@example.com>" in log_output
    assert "Priya Nair <priya@example.com>" in log_output
    assert "Rohan Gupta <rohan@example.com>" in log_output


def test_index_json_loads_into_repo_index(demo_cache_paths):
    """Verify sample_repo_index.json parses into RepoIndex and helper methods work."""
    index_raw = demo_cache_paths["index"].read_text(encoding="utf-8")
    repo_index = RepoIndex.model_validate_json(index_raw)

    assert repo_index.source_url == DEMO_REPO_URL
    assert repo_index.local_path == ""
    assert repo_index.from_cache is True
    assert repo_index.total_py_files == 7
    assert repo_index.truncated is False
    assert len(repo_index.files) == 7

    # Test RepoIndex helper methods
    sim_file = repo_index.get_file("similarity.py")
    assert sim_file is not None
    assert any(fn.name == "cosine_similarity" for fn in sim_file.functions)

    # Identifiers
    idents = repo_index.identifiers(limit=30)
    assert "cosine_similarity" in idents
    assert "Student" in idents

    # Numbered source
    numbered = repo_index.numbered_source("similarity.py", 1, 5)
    assert "1 |" in numbered

    # Function lookup
    fn = repo_index.find_function("similarity.py", 10)
    assert fn is not None
    assert fn.name == "cosine_similarity"

    # Citation range snapping
    snapped = repo_index.snap_range("similarity.py", 8, 12)
    assert snapped[0] == "similarity.py"
    assert snapped[1] >= fn.line_start
    assert snapped[2] <= fn.line_end


def test_author_shares_and_split(demo_cache_paths):
    """Verify sample_repo_authors.json reflects roughly 50/30/20 split and exact ownership."""
    authors_data = json.loads(demo_cache_paths["authors"].read_text(encoding="utf-8"))

    assert "author_map" in authors_data
    assert "authorship_stats" in authors_data

    # Parse into Pydantic models
    stats = [AuthorStat.model_validate(s) for s in authors_data["authorship_stats"]]
    assert len(stats) == 3

    # Check shares sum to 1.0
    total_share = sum(s.share_of_lines for s in stats)
    assert pytest.approx(1.0, abs=0.002) == total_share

    # Check author shares roughly 50/30/20
    stat_dict = {s.author: s.share_of_lines for s in stats}
    assert 0.45 <= stat_dict["Aman Verma"] <= 0.55, f"Aman share {stat_dict['Aman Verma']} out of range"
    assert 0.25 <= stat_dict["Priya Nair"] <= 0.35, f"Priya share {stat_dict['Priya Nair']} out of range"
    assert 0.15 <= stat_dict["Rohan Gupta"] <= 0.25, f"Rohan share {stat_dict['Rohan Gupta']} out of range"

    # Check symbol ownership
    author_map = {
        author: [OwnedSymbol.model_validate(sym) for sym in syms]
        for author, syms in authors_data["author_map"].items()
    }

    # Priya must own cosine_similarity
    priya_sym_names = [s.symbol for s in author_map["Priya Nair"]]
    assert "cosine_similarity" in priya_sym_names

    # Aman must own score_student_pair and top_k_partners
    aman_sym_names = [s.symbol for s in author_map["Aman Verma"]]
    assert "score_student_pair" in aman_sym_names
    assert "top_k_partners" in aman_sym_names

    # Rohan must own data_loader functions
    rohan_sym_names = [s.symbol for s in author_map["Rohan Gupta"]]
    assert "parse_student_record" in rohan_sym_names


def test_challenge_json_schema(demo_cache_paths):
    """Verify sample_repo_challenge.json contains all required fields."""
    challenge = json.loads(demo_cache_paths["challenge"].read_text(encoding="utf-8"))

    required_keys = {
        "description",
        "target_file",
        "function",
        "starter_code",
        "test_code",
        "reference_solution",
    }
    assert required_keys.issubset(challenge.keys())
    assert challenge["target_file"] == "similarity.py"
    assert challenge["function"] == "cosine_similarity"
    assert "ZeroDivisionError" in challenge["description"]
    assert "def cosine_similarity" in challenge["starter_code"]
    assert "def cosine_similarity" in challenge["reference_solution"]
    assert "test_cosine_similarity" in challenge["test_code"]


def test_challenge_starter_fails_and_reference_passes(demo_cache_paths, tmp_path):
    """Verify challenge test suite fails on starter code and passes on reference solution."""
    challenge = json.loads(demo_cache_paths["challenge"].read_text(encoding="utf-8"))

    # Clone the repo into tmp_path
    repo_copy = tmp_path / "repo_copy"
    subprocess.run(
        ["git", "clone", str(demo_cache_paths["bundle"]), str(repo_copy)],
        check=True,
        capture_output=True,
    )

    # Write pytest.ini so pythonpath includes repo root
    (repo_copy / "pytest.ini").write_text("[pytest]\npythonpath = .\n", encoding="utf-8")

    # Write challenge test_code to test_vivavoce_challenge.py
    test_file = repo_copy / "test_vivavoce_challenge.py"
    test_file.write_text(challenge["test_code"], encoding="utf-8")

    # 1. Run pytest on starter code (should FAIL with ZeroDivisionError)
    res_starter = subprocess.run(
        [sys.executable, "-m", "pytest", "test_vivavoce_challenge.py", "-q"],
        cwd=repo_copy,
        capture_output=True,
        text=True,
    )
    assert res_starter.returncode != 0, "Starter code should fail the test suite"
    assert "ZeroDivisionError" in res_starter.stdout or "FAILED" in res_starter.stdout

    # 2. Overwrite similarity.py with reference_solution (should PASS)
    (repo_copy / "similarity.py").write_text(challenge["reference_solution"], encoding="utf-8")
    res_ref = subprocess.run(
        [sys.executable, "-m", "pytest", "test_vivavoce_challenge.py", "-q"],
        cwd=repo_copy,
        capture_output=True,
        text=True,
    )
    assert res_ref.returncode == 0, f"Reference solution should pass the test suite:\n{res_ref.stdout}\n{res_ref.stderr}"
    assert "passed" in res_ref.stdout


def test_deterministic_build(tmp_path):
    """Verify build_sample_repo is strictly deterministic across independent executions."""
    out_dir_1 = tmp_path / "run1"
    out_dir_2 = tmp_path / "run2"

    res1 = build_sample_repo(str(out_dir_1))
    res2 = build_sample_repo(str(out_dir_2))

    for key in ["index", "authors", "challenge"]:
        content1 = Path(res1[key]).read_text(encoding="utf-8")
        content2 = Path(res2[key]).read_text(encoding="utf-8")
        assert content1 == content2, f"Artifact '{key}' is not deterministic across runs"

    # Check commit SHAs from bundles
    repo1 = tmp_path / "clone1"
    repo2 = tmp_path / "clone2"
    subprocess.run(["git", "clone", res1["bundle"], str(repo1)], check=True, capture_output=True)
    subprocess.run(["git", "clone", res2["bundle"], str(repo2)], check=True, capture_output=True)

    sha1 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo1, text=True).strip()
    sha2 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo2, text=True).strip()
    assert sha1 == sha2, f"HEAD commit SHA mismatch between builds: {sha1} vs {sha2}"
