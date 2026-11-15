"""Sandbox execution runner: pytest sandboxed with a timeout and process-tree cleanup.

Wording convention: student code is 'sandboxed with a timeout'.
Note: the child gets a minimal env dict (no API keys) and a time limit, but it runs as the
same OS user: it can still read files (e.g. backend/.env), read ancestor processes'
environments (e.g. via psutil), and use the network.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

try:
    from ..ingestion.config import SANDBOX_OUTPUT_LIMIT, SANDBOX_TIMEOUT_S
    from ..ingestion.models import SandboxResult
except ImportError:
    from ingestion.config import SANDBOX_OUTPUT_LIMIT, SANDBOX_TIMEOUT_S
    from ingestion.models import SandboxResult

from .multi_language import execute_multi_language_sandbox  # re-export, team code

log = logging.getLogger("vivavoce.sandbox")

SANDBOX_COPY_MAX_BYTES = 10 * 1024 * 1024  # Cap ~10 MB

SKIP_DIR_NAMES = {
    ".git",
    "venv",
    ".venv",
    "env",
    ".env",
    "node_modules",
    "site-packages",
    "migrations",
    "build",
    "dist",
    "__pycache__",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    CREATE_SUSPENDED = 0x00000004
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008  # caps fork bombs
    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200  # caps memory bombs
    JobObjectExtendedLimitInformation = 9

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryLimit", ctypes.c_size_t),
            ("PeakJobMemoryLimit", ctypes.c_size_t),
        ]

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ntdll = ctypes.WinDLL("ntdll")

        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]

        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]

        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]

        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        ntdll.NtResumeProcess.restype = wintypes.LONG
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    except Exception as exc:
        log.warning("Failed to initialize Windows Job Object functions: %s", exc)
        kernel32 = None  # type: ignore
        ntdll = None  # type: ignore
else:
    kernel32 = None  # type: ignore
    ntdll = None  # type: ignore


def _validate_relative_path(file_path: str, temp_dir: Path) -> Path:
    """Validate that file_path is relative, has no '..' segments, and stays in temp_dir."""
    if not isinstance(file_path, str):
        raise ValueError("file_path must be a string")
    if "\0" in file_path:
        raise ValueError("file_path cannot contain NUL bytes")
    raw = file_path.strip().replace("\\", "/")
    if not raw:
        raise ValueError("file_path cannot be empty")
    if raw.startswith("/") or raw.startswith("\\"):
        raise ValueError("file_path must be a relative path")
    parts = [p for p in raw.split("/") if p]
    if ".." in parts:
        raise ValueError("file_path cannot contain '..' segments")
    p = Path(raw)
    if p.is_absolute() or re.match(r"^[A-Za-z]:", raw):
        raise ValueError("file_path must be a relative path")
    if p.name == "test_vivavoce_challenge.py":
        raise ValueError(
            "file_path cannot be 'test_vivavoce_challenge.py' (reserved for test harness)"
        )
    target = (temp_dir / p).resolve()
    temp_dir_resolved = temp_dir.resolve()
    try:
        target.relative_to(temp_dir_resolved)
    except ValueError:
        raise ValueError("file_path must stay inside the sandbox directory")
    if target == temp_dir_resolved:
        raise ValueError("file_path cannot be the sandbox root directory")
    return target


def _copy_repo_files(
    repo_root: Path,
    temp_dir: Path,
    max_bytes: int = SANDBOX_COPY_MAX_BYTES,
) -> int:
    """Copy all .py files from repo_root into temp_dir, preserving folder structure.

    Skips .git, venvs, node_modules, site-packages, migrations, build/dist, __pycache__,
    caches, symlinks, and stops if aggregate copied bytes exceed max_bytes (~10 MB).
    Package __init__.py files are preserved. Re-implemented locally without importing lane A.

    Returns total bytes copied.
    """
    total_bytes = 0
    repo_root = repo_root.resolve()

    for root, dirs, files in os.walk(repo_root, followlinks=False):
        dirs[:] = [
            d
            for d in dirs
            if d not in SKIP_DIR_NAMES
            and not d.endswith(".egg-info")
            and not d.endswith(".dist-info")
            and not os.path.islink(os.path.join(root, d))
        ]

        for file_name in files:
            if not file_name.endswith(".py"):
                continue

            full_path = os.path.join(root, file_name)
            if os.path.islink(full_path):
                continue

            try:
                rel_path = Path(full_path).relative_to(repo_root)
            except ValueError:
                continue

            if any(
                p in SKIP_DIR_NAMES
                or p.endswith(".egg-info")
                or p.endswith(".dist-info")
                for p in rel_path.parts[:-1]
            ):
                continue

            if rel_path == Path("test_vivavoce_challenge.py"):
                continue

            try:
                file_size = os.path.getsize(full_path)
            except OSError:
                continue

            if total_bytes + file_size > max_bytes:
                log.warning(
                    "Sandbox repo copy exceeded %d bytes limit; stopped copying at %d bytes",
                    max_bytes,
                    total_bytes,
                )
                return total_bytes

            dest_path = temp_dir / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(full_path, dest_path)
                total_bytes += file_size
            except OSError as exc:
                log.warning("Failed to copy %s to sandbox: %s", full_path, exc)

    return total_bytes


def _build_minimal_env(temp_dir_path: Path) -> dict[str, str]:
    """Build a brand-new minimal environment dictionary without copying os.environ.

    Contains only essential system paths and forces non-persistent, safe python settings.
    No parent API keys or secrets are propagated.
    """
    temp_str = str(temp_dir_path)
    env: dict[str, str] = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "TEMP": temp_str,
        "TMP": temp_str,
        "HOME": temp_str,
        "USERPROFILE": temp_str,
    }
    # Windows system environment variables needed for system DLLs and processes
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    elif sys.platform == "win32":
        env["SYSTEMROOT"] = r"C:\Windows"

    if "WINDIR" in os.environ:
        env["WINDIR"] = os.environ["WINDIR"]
    elif sys.platform == "win32":
        env["WINDIR"] = r"C:\Windows"

    if "SYSTEMDRIVE" in os.environ:
        env["SYSTEMDRIVE"] = os.environ["SYSTEMDRIVE"]

    return env


def _kill_process_tree(pid: int) -> None:
    """Kill the process and its entire process tree (on Windows: taskkill /T /F /PID)."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                check=False,
                timeout=5,
            )
        except Exception as exc:
            log.warning("taskkill failed for PID %d: %s", pid, exc)
    else:
        # POSIX process group kill fallback
        try:
            import signal

            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            try:
                import signal

                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass


def _truncate_output(text: str, limit: int) -> str:
    """Truncate text to limit characters, preserving the tail where summaries live."""
    if len(text) <= limit:
        return text
    prefix = "[... truncated ...]\n"
    if limit <= len(prefix):
        return text[:limit]
    return prefix + text[-(limit - len(prefix)) :]


def _read_output_tail(file_path: Path, limit: int) -> str:
    """Read at most the tail of a file, decoding as UTF-8 and truncating to limit chars."""
    if not file_path.exists():
        return ""
    try:
        file_size = file_path.stat().st_size
    except OSError:
        return ""
    if file_size == 0:
        return ""
    bytes_to_read = min(file_size, limit * 4)
    try:
        with open(file_path, "rb") as f:
            if file_size > bytes_to_read:
                f.seek(file_size - bytes_to_read)
            raw_bytes = f.read()
    except OSError:
        return ""
    text = raw_bytes.decode("utf-8", errors="replace")
    return _truncate_output(text, limit)


def _parse_pytest_output(
    stdout: str, stderr: str, returncode: int
) -> tuple[bool, int, int, Optional[str]]:
    """Parse pass/fail counts and status from pytest output.

    Returns (passed, tests_passed, tests_failed, error).
    """
    combined = f"{stdout}\n{stderr}"

    # Take the LAST match: pytest's summary line comes after any captured test output
    passed_match = re.findall(r"\b(\d+)\s+passed\b", combined)
    failed_match = re.findall(r"\b(\d+)\s+failed\b", combined)
    error_match = re.findall(r"\b(\d+)\s+error(?:s)?\b", combined)

    tests_passed = int(passed_match[-1]) if passed_match else 0
    tests_failed = int(failed_match[-1]) if failed_match else 0
    errors_count = int(error_match[-1]) if error_match else 0

    # Clean exit code with real passes is authoritative (warning text may mention "SyntaxError:")
    if returncode == 0 and tests_passed > 0 and tests_failed == 0 and errors_count == 0:
        return True, tests_passed, 0, None

    # Handle 'no tests ran'
    if "no tests ran" in combined:
        return False, 0, 0, "No tests ran"

    # Handle SyntaxError
    syntax_match = re.search(r"SyntaxError:\s*([^\n\r]+)", combined)
    if syntax_match:
        return False, tests_passed, tests_failed, f"SyntaxError: {syntax_match.group(1).strip()}"

    # Handle collection errors
    if "error during collection" in combined or "ERROR collecting" in combined:
        mod_match = re.search(
            r"((?:ModuleNotFoundError|ImportError|NameError|AttributeError):\s*[^\n\r]+)",
            combined,
        )
        if mod_match:
            return (
                False,
                tests_passed,
                tests_failed,
                f"Collection error: {mod_match.group(1).strip()}",
            )
        return False, tests_passed, tests_failed, "Collection error during pytest discovery"

    # Successful run with passed tests and no failures or errors
    if returncode == 0 and tests_passed > 0 and tests_failed == 0 and errors_count == 0:
        return True, tests_passed, 0, None

    # Failed test run
    if returncode != 0:
        if tests_failed > 0 or errors_count > 0:
            return False, tests_passed, tests_failed + errors_count, None
        return False, tests_passed, tests_failed, f"Pytest failed with exit code {returncode}"

    # Returncode is 0 but no passed tests
    return (tests_passed > 0 and tests_failed == 0), tests_passed, tests_failed, None


def execute_verification(
    file_path: str,
    student_code: str,
    test_code: str,
    repo_root: Optional[str] = None,
) -> SandboxResult:
    """Execute pytest against student code in a temporary directory with timeout.

    Runs student code sandboxed with a timeout. Never raises exceptions.
    """
    started = time.perf_counter()
    try:
        repo_root_path: Optional[Path] = None
        if repo_root is not None:
            if not isinstance(repo_root, (str, Path)) or not str(repo_root).strip():
                return SandboxResult(
                    passed=False,
                    stdout="",
                    stderr="",
                    runtime_ms=int((time.perf_counter() - started) * 1000),
                    timed_out=False,
                    tests_passed=0,
                    tests_failed=0,
                    error="repo_root must be a non-empty string or Path",
                )
            repo_root_path = Path(repo_root).resolve()
            if not repo_root_path.exists() or not repo_root_path.is_dir():
                return SandboxResult(
                    passed=False,
                    stdout="",
                    stderr="",
                    runtime_ms=int((time.perf_counter() - started) * 1000),
                    timed_out=False,
                    tests_passed=0,
                    tests_failed=0,
                    error=f"repo_root does not exist or is not a directory: {repo_root}",
                )

        timeout_s = getattr(
            sys.modules[__name__], "SANDBOX_TIMEOUT_S", SANDBOX_TIMEOUT_S
        )
        output_limit = getattr(
            sys.modules[__name__], "SANDBOX_OUTPUT_LIMIT", SANDBOX_OUTPUT_LIMIT
        )

        with tempfile.TemporaryDirectory(
            prefix="vivavoce-sandbox-", ignore_cleanup_errors=True
        ) as temp_dir, tempfile.TemporaryDirectory(
            prefix="vivavoce-sandbox-io-", ignore_cleanup_errors=True
        ) as io_dir:
            temp_dir_path = Path(temp_dir).resolve()
            io_dir_path = Path(io_dir).resolve()

            # 1. If repo_root provided, copy repo .py files first
            if repo_root_path is not None:
                _copy_repo_files(repo_root_path, temp_dir_path)

            # 2. Validate and write student code (overwrites existing file or creates new)
            target_file = _validate_relative_path(file_path, temp_dir_path)
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(student_code, encoding="utf-8")

            # Ensure __init__.py exists in any intermediate directories for packages
            curr = target_file.parent
            while curr != temp_dir_path and temp_dir_path in curr.parents:
                init_file = curr / "__init__.py"
                if not init_file.exists():
                    init_file.write_text("", encoding="utf-8")
                curr = curr.parent

            # 3. Write test code
            test_file = temp_dir_path / "test_vivavoce_challenge.py"
            test_file.write_text(test_code, encoding="utf-8")

            # 4. Write pytest.ini
            pytest_ini = temp_dir_path / "pytest.ini"
            pytest_ini.write_text("[pytest]\npythonpath = .\n", encoding="utf-8")

            # 4. Build command and minimal env
            command = [
                sys.executable,
                "-I",
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "--noconftest",
                "test_vivavoce_challenge.py",
            ]
            clean_env = _build_minimal_env(temp_dir_path)

            stdout_file = io_dir_path / "stdout.log"
            stderr_file = io_dir_path / "stderr.log"

            job_handle = None
            suspended = False
            if sys.platform == "win32" and kernel32 is not None:
                try:
                    job = kernel32.CreateJobObjectW(None, None)
                    if job:
                        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                        info.BasicLimitInformation.LimitFlags = (
                            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                            | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                            | JOB_OBJECT_LIMIT_JOB_MEMORY
                        )
                        info.BasicLimitInformation.ActiveProcessLimit = 32
                        info.JobMemoryLimit = 1024 * 1024 * 1024  # 1 GB for the whole run
                        success = kernel32.SetInformationJobObject(
                            job,
                            JobObjectExtendedLimitInformation,
                            ctypes.byref(info),
                            ctypes.sizeof(info),
                        )
                        if success:
                            job_handle = job
                        else:
                            log.warning(
                                "SetInformationJobObject failed: %s",
                                ctypes.get_last_error(),
                            )
                            kernel32.CloseHandle(job)
                except Exception as exc:
                    log.warning("CreateJobObjectW failed: %s", exc)

            creationflags = 0
            if sys.platform == "win32" and job_handle:
                creationflags |= CREATE_SUSPENDED
                suspended = True

            proc: Optional[subprocess.Popen] = None
            timed_out = False

            with open(stdout_file, "wb") as f_out, open(stderr_file, "wb") as f_err:
                try:
                    proc = subprocess.Popen(
                        command,
                        cwd=temp_dir_path,
                        env=clean_env,
                        stdin=subprocess.DEVNULL,
                        stdout=f_out,
                        stderr=f_err,
                        creationflags=creationflags,
                        # POSIX: own process group, so killpg() never hits the server's group
                        start_new_session=(sys.platform != "win32"),
                    )

                    if suspended and proc is not None:
                        if job_handle:
                            try:
                                handle_val = wintypes.HANDLE(int(proc._handle))
                                assigned = kernel32.AssignProcessToJobObject(
                                    job_handle, handle_val
                                )
                                if not assigned:
                                    log.warning(
                                        "AssignProcessToJobObject failed: %s",
                                        ctypes.get_last_error(),
                                    )
                            except Exception as exc:
                                log.warning("AssignProcessToJobObject error: %s", exc)

                        if ntdll is not None:
                            try:
                                ntdll.NtResumeProcess(
                                    wintypes.HANDLE(int(proc._handle))
                                )
                            except Exception as exc:
                                log.warning("NtResumeProcess error: %s", exc)

                    try:
                        proc.wait(timeout=timeout_s)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        if proc.pid:
                            _kill_process_tree(proc.pid)

                finally:
                    if job_handle:
                        try:
                            kernel32.TerminateJobObject(job_handle, 1)
                        except Exception:
                            pass
                        try:
                            kernel32.CloseHandle(job_handle)
                        except Exception:
                            pass
                        job_handle = None

                    if sys.platform != "win32" and proc is not None and proc.pid:
                        try:
                            import signal

                            os.killpg(proc.pid, signal.SIGKILL)
                        except Exception:
                            pass

                    if proc is not None:
                        try:
                            proc.wait(timeout=2)
                        except Exception:
                            pass

            runtime_ms = int((time.perf_counter() - started) * 1000)

            raw_stdout = _read_output_tail(stdout_file, output_limit)
            raw_stderr = _read_output_tail(stderr_file, output_limit)

            if timed_out:
                return SandboxResult(
                    passed=False,
                    stdout=raw_stdout,
                    stderr=raw_stderr,
                    runtime_ms=runtime_ms,
                    timed_out=True,
                    tests_passed=0,
                    tests_failed=0,
                    error=f"Execution timed out after {timeout_s}s",
                )

            returncode = proc.returncode if proc is not None else 1
            passed, tests_passed, tests_failed, error = _parse_pytest_output(
                raw_stdout, raw_stderr, returncode
            )

            return SandboxResult(
                passed=passed,
                stdout=raw_stdout,
                stderr=raw_stderr,
                runtime_ms=runtime_ms,
                timed_out=False,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                error=error,
            )

    except Exception as exc:
        runtime_ms = int((time.perf_counter() - started) * 1000)
        return SandboxResult(
            passed=False,
            stdout="",
            stderr="",
            runtime_ms=runtime_ms,
            timed_out=False,
            tests_passed=0,
            tests_failed=0,
            error=str(exc),
        )


async def execute_verification_async(
    file_path: str,
    student_code: str,
    test_code: str,
    repo_root: Optional[str] = None,
) -> SandboxResult:
    """Async wrapper around execute_verification via asyncio.to_thread."""
    return await asyncio.to_thread(
        execute_verification,
        file_path,
        student_code,
        test_code,
        repo_root,
    )


def warm_up_sandbox() -> int:
    """Warm up pytest process execution on server startup; returns runtime in ms.

    Runs one trivial pytest run to pre-warm python/pytest startup and caches.
    Never raises an exception.
    """
    try:
        t0 = time.perf_counter()
        res = execute_verification(
            file_path="_warmup_target.py",
            student_code="def _warmup_check() -> bool:\n    return True\n",
            test_code="from _warmup_target import _warmup_check\n\ndef test_warmup():\n    assert _warmup_check() is True\n",
            repo_root=None,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return elapsed_ms if elapsed_ms > 0 else res.runtime_ms
    except Exception as exc:
        log.warning("warm_up_sandbox encountered an unexpected error: %s", exc)
        return 0
