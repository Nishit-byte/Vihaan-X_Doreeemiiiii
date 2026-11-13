"""Run a student patch and generated pytest checks in a short-lived directory.

This subprocess boundary provides a clean working directory and a hard timeout.
It is useful for a local demo, but it is not an OS-level security sandbox; do not
expose it to untrusted public traffic without container or VM isolation.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from backend.models.schemas import RunCodeResponse


def _safe_python_path(file_path: str) -> Path:
    raw = file_path.strip().replace("\\", "/")
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("file_path must be a relative Python path.")
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ValueError("file_path cannot contain empty, current, or parent path segments.")
    if candidate.suffix.lower() != ".py":
        raise ValueError("Only Python student code can be executed by this runner.")
    return candidate


def _minimal_environment() -> dict[str, str]:
    allowed_keys = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    environment = {key: os.environ[key] for key in allowed_keys if key in os.environ}
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def execute_verification(
    file_path: str,
    student_code: str,
    test_code: str,
) -> RunCodeResponse:
    """Execute pytest in a temporary project and return its output and duration."""
    target = _safe_python_path(file_path)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vivavoce-verify-") as temp_dir:
        root = Path(temp_dir)
        student_file = root / target
        student_file.parent.mkdir(parents=True, exist_ok=True)
        student_file.write_text(student_code, encoding="utf-8")
        # Generated tests often import by basename; mirror the main.py fallback.
        basename_alias = root / target.name
        if basename_alias != student_file:
            basename_alias.write_text(student_code, encoding="utf-8")
        student_alias = root / "student_solution.py"
        if student_alias != student_file and student_alias != basename_alias:
            student_alias.write_text(student_code, encoding="utf-8")
        effective_test_code = test_code.strip() or (
            "def test_syntax_and_import():\n"
            "    import student_solution\n"
            "    assert student_solution is not None\n"
        )
        (root / "test_student_code.py").write_text(effective_test_code, encoding="utf-8")

        command = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                env=_minimal_environment(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=4,
                check=False,
                shell=False,
            )
            stdout = completed.stdout[-12_000:]
            stderr = completed.stderr[-12_000:]
            passed = completed.returncode == 0
        except subprocess.TimeoutExpired as exc:
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            stderr = (stderr + "\nVerification exceeded the 4-second time limit.").strip()
            passed = False
        except OSError as exc:
            stdout = ""
            stderr = f"Could not start pytest: {exc}"
            passed = False

    runtime_ms = int((time.perf_counter() - started) * 1000)
    return RunCodeResponse(
        passed=passed,
        stdout=stdout,
        stderr=stderr,
        runtime_ms=runtime_ms,
    )
