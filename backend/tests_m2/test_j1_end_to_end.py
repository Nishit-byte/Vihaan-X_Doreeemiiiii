"""End-to-end integration and dev_cli test suite for Task J1."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ingestion.config import BACKEND_DIR, DEMO_CACHE_DIR, DEMO_REPO_URL
from ingestion.demo_loader import (
    load_demo_challenge,
    load_demo_repo,
    materialize_demo_repo,
)
from ingestion.dev_cli import main
from ingestion.pdf_parser import parse_research_paper
from ingestion.repo_parser import clone_and_index_repo
from replay.store import ReplayStore
from sandbox.sandbox_runner import execute_verification, warm_up_sandbox


@pytest.fixture
def sample_pdf_path() -> Path:
    """Return path to the committed sample paper PDF."""
    pdf = Path(DEMO_CACHE_DIR) / "sample_paper.pdf"
    assert pdf.exists(), f"sample_paper.pdf missing at {pdf}"
    return pdf


def test_cli_repo_demo(capsys: pytest.CaptureFixture) -> None:
    """dev_cli repo demo prints complete index summary, author stats, and identifiers."""
    ret = main(["repo", "demo"])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "REPO INDEXING: demo" in captured
    assert "Repo ID:" in captured
    assert "Commit SHA:" in captured
    assert "From Cache:    True" in captured
    assert "similarity.py" in captured
    assert "models.py" in captured
    assert "Aman Verma" in captured
    assert "Priya Nair" in captured
    assert "Rohan Gupta" in captured
    assert "Top Identifiers" in captured
    assert "cosine_similarity" in captured


def test_cli_repo_invalid_url(capsys: pytest.CaptureFixture) -> None:
    """dev_cli repo with invalid URL prints friendly error and returns exit code 1."""
    ret = main(["repo", "https://notgithub.com/bad/repo"])
    assert ret == 1

    captured = capsys.readouterr().out
    assert "INGESTION ERROR:" in captured


def test_cli_pdf_sample_paper(sample_pdf_path: Path, capsys: pytest.CaptureFixture) -> None:
    """dev_cli pdf prints title, page count, sections, concept nodes, and Mermaid diagram."""
    ret = main(["pdf", str(sample_pdf_path)])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "PDF PARSING:" in captured
    assert "Adaptive Spaced Repetition with Peer Matching" in captured
    assert "Page Count:    3" in captured
    assert "Source:        cache" in captured
    assert "Sections (12):" in captured
    assert "[N1]" in captured
    assert "[N6]" in captured
    assert "flowchart TD" in captured
    assert "classDef active stroke-width:4px;" in captured


def test_cli_pdf_nonexistent_file(capsys: pytest.CaptureFixture) -> None:
    """dev_cli pdf with non-existent file path prints error and returns exit code 1."""
    ret = main(["pdf", "does_not_exist_sample.pdf"])
    assert ret == 1

    captured = capsys.readouterr().out
    assert "ERROR: File not found" in captured


def test_cli_challenge_demo(capsys: pytest.CaptureFixture) -> None:
    """dev_cli challenge demo runs starter (fails) and reference (passes), returning 0."""
    ret = main(["challenge", "demo"])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "CODING CHALLENGE RUN: demo" in captured
    assert "similarity.py -> cosine_similarity()" in captured
    assert "Running STARTER CODE" in captured
    assert "Passed:       False" in captured
    assert "Running REFERENCE SOLUTION" in captured
    assert "Passed:       True" in captured
    assert "Starter code failed as expected:       True" in captured
    assert "Reference solution passed as expected: True" in captured
    assert "VERDICT: PASS" in captured


def test_cli_challenge_unsupported_target(capsys: pytest.CaptureFixture) -> None:
    """dev_cli challenge with unsupported target prints error and returns exit code 1."""
    ret = main(["challenge", "nonexistent_challenge"])
    assert ret == 1

    captured = capsys.readouterr().out
    assert "ERROR: Unsupported challenge target" in captured


def test_cli_sandbox_leak(capsys: pytest.CaptureFixture) -> None:
    """dev_cli sandbox-leak verifies no secrets in child environment and restores parent env."""
    ret = main(["sandbox-leak"])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "SANDBOX CREDENTIAL LEAK CHECK" in captured
    assert "VERDICT: PASS" in captured
    assert "No secrets in the child environment (same-user file reads are NOT blocked; see NOTES §4)" in captured

    # Verify parent environment does not retain any fake keys
    assert "fake_gemini_key_dev_cli_12345" not in os.environ.get("GEMINI_API_KEY", "")
    assert "fake_groq_key_dev_cli_67890" not in os.environ.get("GROQ_API_KEY", "")
    assert "super_secret_token_dev_cli_xyz" not in os.environ.get("SECRET_TOKEN", "")


def test_cli_replay_status(capsys: pytest.CaptureFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """dev_cli replay-status displays valid JSON status without corrupting disk store."""
    replay_dir = tmp_path / "replay_test"
    monkeypatch.setenv("REPLAY_DIR", str(replay_dir))

    ret = main(["replay-status"])
    assert ret == 0

    captured = capsys.readouterr().out
    assert "REPLAY STORE STATUS" in captured
    assert '"recorded_calls": 0' in captured

    # Verify no persistent pollution in demo_cache/replay/
    official_replay_session = Path(DEMO_CACHE_DIR) / "replay" / "session.jsonl"
    assert not official_replay_session.exists(), "Replay store session.jsonl should not exist in demo_cache/replay/"


def test_end_to_end_pipeline_offline(sample_pdf_path: Path) -> None:
    """Test full integration pipeline in memory: Repo -> Citation -> STT terms -> PDF -> Sandbox."""
    # 1. Warm-up sandbox
    warm_ms = warm_up_sandbox()
    assert warm_ms < 8000

    # 2. Ingest repository (offline demo cache)
    repo_index = clone_and_index_repo("demo", use_cache=True)
    assert repo_index.from_cache is True
    assert len(repo_index.files) == 7

    # 3. Citation snap_range guard (P0-1.2)
    path, start, end = repo_index.snap_range("similarity.py", 1, 5)
    assert path == "similarity.py"
    assert start >= 1 and end >= start

    # 4. Speech-to-text domain terms (P1-3.5)
    domain_terms = repo_index.identifiers(limit=25)
    assert len(domain_terms) > 0
    assert "cosine_similarity" in domain_terms

    # 5. Parse research paper (offline cache)
    pdf_bytes = sample_pdf_path.read_bytes()
    paper_index = parse_research_paper(pdf_bytes, use_cache=True)
    assert paper_index.source == "cache"
    assert len(paper_index.nodes) == 6
    assert all(n.id.startswith("N") for n in paper_index.nodes)
    assert "flowchart TD" in paper_index.mermaid

    # 6. Materialize and execute coding challenge in sandbox
    challenge = load_demo_challenge()
    repo_root = materialize_demo_repo()
    assert os.path.exists(repo_root)

    res_starter = execute_verification(
        challenge["target_file"],
        challenge["starter_code"],
        challenge["test_code"],
        repo_root=repo_root,
    )
    assert res_starter.passed is False
    assert res_starter.tests_failed > 0

    res_ref = execute_verification(
        challenge["target_file"],
        challenge["reference_solution"],
        challenge["test_code"],
        repo_root=repo_root,
    )
    assert res_ref.passed is True
    assert res_ref.tests_passed == 6
