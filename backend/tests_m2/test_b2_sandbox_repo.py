"""Tests for TASK B2: Sandbox repo copy, async wrapper, and warm-up."""

import asyncio
import os
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

import pytest

from ingestion.models import SandboxResult
from sandbox.sandbox_runner import (
    SANDBOX_COPY_MAX_BYTES,
    _copy_repo_files,
    execute_verification,
    execute_verification_async,
    warm_up_sandbox,
)


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """Create a sample multi-file repository structure for sandbox verification.

    Layout:
    repo/
      pkg/
        __init__.py
        core.py (imports pkg.utils.helpers)
        utils/
          __init__.py
          helpers.py (provides add and multiply)
      .git/
        HEAD
        hooks/
          dummy.py
      venv/
        lib/
          site.py
      __pycache__/
        cached.py
      node_modules/
        bundle.py
      build/
        build_artifact.py
      dist/
        dist_artifact.py
    """
    repo = tmp_path / "fixture_repo"
    pkg = repo / "pkg"
    utils = pkg / "utils"
    utils.mkdir(parents=True, exist_ok=True)

    (pkg / "__init__.py").write_text("# pkg init\n", encoding="utf-8")
    (utils / "__init__.py").write_text("# utils init\n", encoding="utf-8")

    (utils / "helpers.py").write_text(
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n\n"
        "def multiply(a: int, b: int) -> int:\n"
        "    return a * b\n",
        encoding="utf-8",
    )

    # Buggy starter code: adds instead of multiplies
    (pkg / "core.py").write_text(
        "from pkg.utils.helpers import add, multiply\n\n"
        "def compute(a: int, b: int) -> int:\n"
        "    # Buggy: should multiply\n"
        "    return add(a, b)\n",
        encoding="utf-8",
    )

    # Populate skipped directories with .py files to verify skip rules
    for skip_dir in [
        ".git/hooks",
        "venv/lib",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
    ]:
        d = repo / skip_dir
        d.mkdir(parents=True, exist_ok=True)
        (d / "ignored.py").write_text(
            "# should not be copied\nSECRET_KEY = 'leak'\n", encoding="utf-8"
        )

    return repo


CHALLENGE_TEST = """
from pkg.core import compute

def test_compute_multiplication():
    assert compute(3, 4) == 12

def test_compute_positive():
    assert compute(5, 6) == 30
"""

CORRECT_FIX = """
from pkg.utils.helpers import multiply

def compute(a: int, b: int) -> int:
    return multiply(a, b)
"""

WRONG_FIX = """
from pkg.utils.helpers import add

def compute(a: int, b: int) -> int:
    return add(a, b)
"""


def test_repo_copy_correct_fix_passes(fixture_repo: Path):
    """P0-2.2 'done when': A correct fix overwriting a repo file passes verification."""
    res = execute_verification(
        file_path="pkg/core.py",
        student_code=CORRECT_FIX,
        test_code=CHALLENGE_TEST,
        repo_root=str(fixture_repo),
    )
    assert res.passed is True
    assert res.tests_passed == 2
    assert res.tests_failed == 0
    assert res.error is None
    assert res.timed_out is False
    assert res.runtime_ms > 0


def test_repo_copy_wrong_fix_fails(fixture_repo: Path):
    """P0-2.2 'done when': A wrong fix overwriting a repo file fails verification."""
    res = execute_verification(
        file_path="pkg/core.py",
        student_code=WRONG_FIX,
        test_code=CHALLENGE_TEST,
        repo_root=str(fixture_repo),
    )
    assert res.passed is False
    assert res.tests_failed >= 1
    assert res.timed_out is False


def test_repo_copy_new_file_inside_repo(fixture_repo: Path):
    """Student code can target a new file inside the repo structure."""
    new_code = """
from pkg.utils.helpers import add

def add_ten(x: int) -> int:
    return add(x, 10)
"""
    test_code = """
from pkg.new_mod import add_ten

def test_new_feature():
    assert add_ten(5) == 15
"""
    res = execute_verification(
        file_path="pkg/new_mod.py",
        student_code=new_code,
        test_code=test_code,
        repo_root=str(fixture_repo),
    )
    assert res.passed is True
    assert res.tests_passed == 1
    assert res.tests_failed == 0


def test_target_outside_repo_rejected(fixture_repo: Path):
    """Target paths that attempt traversal or exit the repo must be rejected."""
    malicious_paths = [
        "../outside.py",
        "../../evil.py",
        "pkg/../../outside.py",
        "/abs/path.py",
        "C:/Windows/System32/evil.py",
        "",
        "   ",
        None,
        "\0evil.py",
        "test_vivavoce_challenge.py",
    ]
    for bad_path in malicious_paths:
        res = execute_verification(
            file_path=bad_path,  # type: ignore
            student_code=CORRECT_FIX,
            test_code=CHALLENGE_TEST,
            repo_root=str(fixture_repo),
        )
        assert res.passed is False, f"Expected {bad_path} to be rejected"
        assert res.error is not None


def test_repo_root_validation(tmp_path: Path):
    """Non-existent repo_root or path to a file must be rejected gracefully."""
    # Non-existent path
    res_missing = execute_verification(
        file_path="pkg/core.py",
        student_code=CORRECT_FIX,
        test_code=CHALLENGE_TEST,
        repo_root=str(tmp_path / "non_existent_dir_12345"),
    )
    assert res_missing.passed is False
    assert "does not exist or is not a directory" in str(res_missing.error)

    # Path to a file instead of a directory
    file_path = tmp_path / "not_a_dir.py"
    file_path.write_text("x = 1\n", encoding="utf-8")
    res_file = execute_verification(
        file_path="pkg/core.py",
        student_code=CORRECT_FIX,
        test_code=CHALLENGE_TEST,
        repo_root=str(file_path),
    )
    assert res_file.passed is False
    assert "does not exist or is not a directory" in str(res_file.error)

    # Empty repo_root string
    res_empty = execute_verification(
        file_path="pkg/core.py",
        student_code=CORRECT_FIX,
        test_code=CHALLENGE_TEST,
        repo_root="",
    )
    assert res_empty.passed is False
    assert "repo_root must be a non-empty string" in str(res_empty.error)


def test_repo_copy_skip_rules(fixture_repo: Path, tmp_path: Path):
    """Verify that skip directories (.git, venv, node_modules, build, dist, __pycache__) are not copied."""
    dest = tmp_path / "copy_dest"
    dest.mkdir(parents=True, exist_ok=True)
    _copy_repo_files(fixture_repo, dest)

    # Legitimate python files must exist
    assert (dest / "pkg" / "__init__.py").exists()
    assert (dest / "pkg" / "core.py").exists()
    assert (dest / "pkg" / "utils" / "helpers.py").exists()

    # Skipped directory contents must not exist
    assert not (dest / ".git").exists()
    assert not (dest / "venv").exists()
    assert not (dest / "__pycache__").exists()
    assert not (dest / "node_modules").exists()
    assert not (dest / "build").exists()
    assert not (dest / "dist").exists()


def test_repo_copy_size_cap(tmp_path: Path):
    """Repo files copy is capped at ~10 MB and does not crash or exceed the limit."""
    huge_repo = tmp_path / "huge_repo"
    huge_repo.mkdir(parents=True, exist_ok=True)

    # Create a 6 MB file and a 6 MB file (total 12 MB)
    chunk = b"# padding\n" + b"x = 1\n" * 100_000  # ~700 KB
    with open(huge_repo / "file1.py", "wb") as f:
        for _ in range(9):
            f.write(chunk)
    with open(huge_repo / "file2.py", "wb") as f:
        for _ in range(9):
            f.write(chunk)

    dest = tmp_path / "dest_capped"
    dest.mkdir(parents=True, exist_ok=True)

    total_copied = _copy_repo_files(huge_repo, dest, max_bytes=SANDBOX_COPY_MAX_BYTES)
    assert total_copied <= SANDBOX_COPY_MAX_BYTES


def test_async_wrapper_in_running_event_loop(fixture_repo: Path):
    """The async wrapper execute_verification_async must work inside a running event loop."""
    async def _run():
        res = await execute_verification_async(
            file_path="pkg/core.py",
            student_code=CORRECT_FIX,
            test_code=CHALLENGE_TEST,
            repo_root=str(fixture_repo),
        )
        return res

    result = asyncio.run(_run())
    assert isinstance(result, SandboxResult)
    assert result.passed is True
    assert result.tests_passed == 2
    assert result.tests_failed == 0
    assert result.runtime_ms > 0


def test_async_wrapper_concurrent(fixture_repo: Path):
    """Multiple execute_verification_async calls can run concurrently via asyncio.gather."""
    async def _run_concurrent():
        return await asyncio.gather(
            execute_verification_async(
                file_path="pkg/core.py",
                student_code=CORRECT_FIX,
                test_code=CHALLENGE_TEST,
                repo_root=str(fixture_repo),
            ),
            execute_verification_async(
                file_path="pkg/core.py",
                student_code=WRONG_FIX,
                test_code=CHALLENGE_TEST,
                repo_root=str(fixture_repo),
            ),
        )

    r1, r2 = asyncio.run(_run_concurrent())
    assert r1.passed is True
    assert r2.passed is False


def test_warm_up_sandbox_runtime_and_limits():
    """warm_up_sandbox runs one trivial pytest, returns ms < 8000, and caches subsequent runs."""
    cold_ms = warm_up_sandbox()
    assert isinstance(cold_ms, int)
    assert cold_ms > 0
    assert cold_ms < 8000, f"Cold warm-up took {cold_ms}ms, expected < 8000ms"

    warm_ms = warm_up_sandbox()
    assert isinstance(warm_ms, int)
    assert warm_ms > 0
    assert warm_ms < 8000, f"Warm warm-up took {warm_ms}ms, expected < 8000ms"


def test_warm_up_sandbox_never_raises(monkeypatch):
    """warm_up_sandbox must catch internal errors and never raise."""
    import sandbox.sandbox_runner as runner

    def _broken_exec(*args, **kwargs):
        raise RuntimeError("Simulated execution failure")

    monkeypatch.setattr(runner, "execute_verification", _broken_exec)

    ms = runner.warm_up_sandbox()
    assert ms == 0
