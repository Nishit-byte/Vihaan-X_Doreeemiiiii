"""Tests for Task A1: GitHub URL validation, cloning, cleanup, and Python file ranking."""

import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.config import WORK_DIR
from ingestion.models import IngestionError
from ingestion.repo_parser import (
    cleanup_repo,
    clone_repo,
    rank_python_files,
    validate_github_url,
)


# ============================================================================
# 1. URL VALIDATION TABLE TESTS
# ============================================================================


@pytest.mark.parametrize(
    "url,expected_owner,expected_repo",
    [
        ("https://github.com/pallets/flask", "pallets", "flask"),
        ("https://github.com/pallets/flask/", "pallets", "flask"),
        ("https://github.com/pallets/flask.git", "pallets", "flask"),
        ("https://github.com/pallets/flask.git/", "pallets", "flask"),
        ("https://github.com/octocat/Hello-World", "octocat", "Hello-World"),
        ("https://github.com/shreyas-269/vivavoce-m2", "shreyas-269", "vivavoce-m2"),
        ("https://github.com/user_123/repo_456", "user_123", "repo_456"),
        ("https://github.com/psf/requests.git", "psf", "requests"),
        ("  https://github.com/pallets/flask  ", "pallets", "flask"),
    ],
)
def test_validate_github_url_valid(url: str, expected_owner: str, expected_repo: str) -> None:
    owner, repo = validate_github_url(url)
    assert owner == expected_owner
    assert repo == expected_repo


@pytest.mark.parametrize(
    "invalid_url,reason",
    [
        ("http://github.com/pallets/flask", "Not HTTPS"),
        ("git@github.com:pallets/flask.git", "SSH URL"),
        ("file:///path/to/repo", "File protocol"),
        ("https://gitlab.com/pallets/flask", "Non-GitHub host"),
        ("https://bitbucket.org/pallets/flask", "Non-GitHub host"),
        ("https://github.com/pallets/flask/tree/main", "Extra path segments (tree)"),
        ("https://github.com/pallets/flask/blob/main/app.py", "Extra path segments (blob)"),
        ("https://github.com/pallets/flask/pulls", "Extra path segments (pulls)"),
        ("https://github.com/pallets", "Missing repository segment"),
        ("https://github.com//flask", "Empty owner segment"),
        ("https://github.com/pallets//", "Empty repo segment"),
        ("https://github.com/", "Empty owner and repo"),
        ("https://github.com", "No path"),
        ("https://github.com/pallets/flask?tab=readme", "Query parameters"),
        ("https://github.com/pallets/flask#section", "Fragment"),
        ("https://notgithub.com/pallets/flask", "Invalid domain"),
        ("not-a-url", "Not a URL"),
        ("", "Empty string"),
        ("   ", "Whitespace string"),
    ],
)
def test_validate_github_url_invalid(invalid_url: str, reason: str) -> None:
    with pytest.raises(IngestionError) as exc_info:
        validate_github_url(invalid_url)
    err = exc_info.value
    assert isinstance(err.user_message, str)
    assert len(err.user_message) > 0


# ============================================================================
# 2. PYTHON FILE RANKING FIXTURE TESTS
# ============================================================================


def test_rank_python_files_fixture(tmp_path: Path) -> None:
    """Build a realistic repository fixture and verify skip rules, import counting, and test ranking."""
    repo = tmp_path / "fixture_repo"
    repo.mkdir()

    # Package pkg/ with cross imports
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from . import utils\n" * 5, encoding="utf-8")  # 5 lines
    (pkg / "utils.py").write_text("def helper():\n    return 42\n" * 10, encoding="utf-8")  # 20 lines
    (pkg / "core.py").write_text(
        "from .utils import helper\n"
        "from .sub.helper_sub import sub_helper\n"
        + "def main_func():\n    return helper()\n" * 19,
        encoding="utf-8",
    )  # ~40 lines

    sub = pkg / "sub"
    sub.mkdir()
    (sub / "__init__.py").write_text("", encoding="utf-8")
    (sub / "helper_sub.py").write_text(
        "from ..utils import helper\n"
        + "def sub_helper():\n    return helper() + 1\n" * 7,
        encoding="utf-8",
    )  # ~15 lines

    # Root files
    (repo / "app.py").write_text(
        "from pkg.core import main_func\n"
        + "def run():\n    return main_func()\n" * 24,
        encoding="utf-8",
    )  # ~49 lines

    (repo / "broken.py").write_text(
        "def broken_syntax(:\n    pass\n" * 5,
        encoding="utf-8",
    )  # 10 lines with syntax error

    # Tests folder
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text(
        "from pkg.core import main_func\n"
        + "def test_main():\n    assert main_func() == 42\n" * 29,
        encoding="utf-8",
    )  # ~59 lines
    (tests / "test_utils.py").write_text(
        "from pkg.utils import helper\n"
        + "def test_util():\n    assert helper() == 42\n" * 14,
        encoding="utf-8",
    )  # ~29 lines

    # Ignored directories
    (repo / "venv" / "lib").mkdir(parents=True)
    (repo / "venv" / "lib" / "site.py").write_text("a = 1\n" * 100, encoding="utf-8")

    (repo / ".venv" / "lib").mkdir(parents=True)
    (repo / ".venv" / "lib" / "site.py").write_text("a = 1\n" * 100, encoding="utf-8")

    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "script.py").write_text("a = 1\n" * 100, encoding="utf-8")

    (repo / "migrations").mkdir()
    (repo / "migrations" / "0001_initial.py").write_text("a = 1\n" * 50, encoding="utf-8")

    (repo / "build").mkdir()
    (repo / "build" / "lib.py").write_text("a = 1\n" * 50, encoding="utf-8")

    (repo / "dist").mkdir()
    (repo / "dist" / "dist.py").write_text("a = 1\n" * 50, encoding="utf-8")

    (repo / "__pycache__").mkdir()
    (repo / "__pycache__" / "cached.cpython-313.py").write_text("a = 1\n" * 50, encoding="utf-8")

    # Huge file (> 2000 lines, default MAX_FILE_LINES is 2000)
    (repo / "huge_file.py").write_text("x = 1\n" * 2050, encoding="utf-8")

    # Run ranking
    results = rank_python_files(str(repo))
    ranked_paths = [path for path, _, _ in results]

    # 1. Skipped files must NOT appear
    assert "venv/lib/site.py" not in ranked_paths
    assert ".venv/lib/site.py" not in ranked_paths
    assert "node_modules/script.py" not in ranked_paths
    assert "migrations/0001_initial.py" not in ranked_paths
    assert "build/lib.py" not in ranked_paths
    assert "dist/dist.py" not in ranked_paths
    assert "__pycache__/cached.cpython-313.py" not in ranked_paths
    assert "huge_file.py" not in ranked_paths

    # 2. Paths must be POSIX formatted
    for p in ranked_paths:
        assert "\\" not in p

    # 3. Import counts check:
    results_dict = {p: (lines, imports) for p, lines, imports in results}

    # pkg/utils.py is imported by: pkg/__init__.py, pkg/core.py, pkg/sub/helper_sub.py, and tests/test_utils.py
    assert results_dict["pkg/utils.py"][1] == 4

    # pkg/core.py is imported by: app.py and tests/test_core.py
    assert results_dict["pkg/core.py"][1] == 2

    # pkg/sub/helper_sub.py is imported by: pkg/core.py
    assert results_dict["pkg/sub/helper_sub.py"][1] == 1

    # app.py is not imported by any other repo file
    assert results_dict["app.py"][1] == 0

    # broken.py (syntax error file) is kept with line count counted
    assert "broken.py" in results_dict
    assert results_dict["broken.py"][0] == 10

    # 4. Tests ranked last check:
    # All non-test files must appear before any test file
    test_indices = [i for i, p in enumerate(ranked_paths) if p.startswith("tests/")]
    non_test_indices = [i for i, p in enumerate(ranked_paths) if not p.startswith("tests/")]

    assert len(test_indices) == 2
    assert max(non_test_indices) < min(test_indices)

    # Within tests group, test_core.py has more lines/score than test_utils.py
    assert test_indices[0] == ranked_paths.index("tests/test_core.py")
    assert test_indices[1] == ranked_paths.index("tests/test_utils.py")


def test_rank_python_files_nonexistent_dir() -> None:
    with pytest.raises(IngestionError) as exc_info:
        rank_python_files("path/that/does/not/exist/anywhere")
    assert "does not exist" in exc_info.value.user_message.lower()


# ============================================================================
# 3. WINDOWS-SAFE CLEANUP TESTS
# ============================================================================


def test_cleanup_repo_readonly_files(tmp_path: Path) -> None:
    """Verify cleanup_repo deletes directories containing read-only .git files."""
    repo_dir = tmp_path / "cloned_repo"
    repo_dir.mkdir()

    git_objects = repo_dir / ".git" / "objects" / "pack"
    git_objects.mkdir(parents=True)

    read_only_file = git_objects / "sample.idx"
    read_only_file.write_text("index data", encoding="utf-8")

    # Set read-only attribute
    os.chmod(str(read_only_file), stat.S_IREAD)

    assert repo_dir.exists()
    cleanup_repo(str(repo_dir))
    assert not repo_dir.exists()


def test_cleanup_repo_idempotent_and_nonexistent(tmp_path: Path) -> None:
    """cleanup_repo should never raise on empty, None, or nonexistent paths."""
    cleanup_repo("")
    cleanup_repo(str(tmp_path / "never_existed_folder"))


# ============================================================================
# 4. CLONE REPO UNIT TESTS (MOCKED SUBPROCESS & SIZE CHECK)
# ============================================================================


def test_clone_repo_invalid_url() -> None:
    with pytest.raises(IngestionError):
        clone_repo("git@github.com:user/repo.git")


def test_clone_repo_private_or_404(tmp_path: Path) -> None:
    """Cloning a nonexistent or private repo raises IngestionError with friendly message."""
    with pytest.raises(IngestionError) as exc_info:
        clone_repo(
            "https://github.com/shreyas-269/vivavoce-test-repo-404-nonexistent-12345",
            dest_dir=str(tmp_path / "target_dest"),
        )
    err = exc_info.value
    assert "was not found or is private" in err.user_message
    assert not (tmp_path / "target_dest").exists()


def test_clone_repo_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Cloning timeout raises IngestionError and cleans up destination."""
    dest = tmp_path / "dest_timeout"

    def mock_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git", "clone"], timeout=45)

    monkeypatch.setattr(subprocess, "run", mock_run)

    with pytest.raises(IngestionError) as exc_info:
        clone_repo("https://github.com/octocat/Hello-World", dest_dir=str(dest))

    assert "timed out" in exc_info.value.user_message
    assert not dest.exists()


def test_clone_repo_full_clone_on_small_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify that when GitHub API reports size <= FULL_CLONE_MAX_KB, --depth is omitted."""
    dest = tmp_path / "dest_small"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"size": 500}  # 500 KB <= 20000 KB

    captured_cmd = []

    def mock_get(*args, **kwargs):
        return mock_resp

    def mock_run(cmd, *args, **kwargs):
        captured_cmd.extend(cmd)
        dest.mkdir(parents=True, exist_ok=True)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        return mock_proc

    monkeypatch.setattr("httpx.get", mock_get)
    monkeypatch.setattr(subprocess, "run", mock_run)

    res = clone_repo("https://github.com/octocat/Hello-World", dest_dir=str(dest))
    assert res == str(dest)
    assert "--depth" not in captured_cmd
    cleanup_repo(str(dest))


def test_clone_repo_shallow_clone_on_large_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify that when GitHub API reports size > FULL_CLONE_MAX_KB, --depth is used."""
    dest = tmp_path / "dest_large"

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"size": 25000}  # 25000 KB > 20000 KB

    captured_cmd = []

    def mock_get(*args, **kwargs):
        return mock_resp

    def mock_run(cmd, *args, **kwargs):
        captured_cmd.extend(cmd)
        dest.mkdir(parents=True, exist_ok=True)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""
        return mock_proc

    monkeypatch.setattr("httpx.get", mock_get)
    monkeypatch.setattr(subprocess, "run", mock_run)

    res = clone_repo("https://github.com/octocat/Hello-World", dest_dir=str(dest))
    assert res == str(dest)
    assert "--depth" in captured_cmd
    cleanup_repo(str(dest))


# ============================================================================
# 5. LIVE NETWORK TEST (RUN WHEN M2_NETWORK_TESTS=1)
# ============================================================================


@pytest.mark.network
def test_clone_repo_network_live() -> None:
    """Clones a tiny public repository over the network and verifies cleanup."""
    test_url = "https://github.com/octocat/Hello-World"
    cloned_path = clone_repo(test_url)
    try:
        assert os.path.exists(cloned_path)
        assert os.path.isdir(cloned_path)
        assert os.path.exists(os.path.join(cloned_path, ".git"))
        assert os.path.exists(os.path.join(cloned_path, "README"))
    finally:
        cleanup_repo(cloned_path)
        assert not os.path.exists(cloned_path)
