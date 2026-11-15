"""Tests for TASK B1: sandbox core execution, security scrub, timeout, and tree kill."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from ingestion.config import SANDBOX_OUTPUT_LIMIT, SANDBOX_TIMEOUT_S
from ingestion.models import SandboxResult
from sandbox import sandbox_runner
from sandbox.sandbox_runner import execute_verification


def test_key_leak_prevention(monkeypatch):
    """Verify parent environment secrets do not leak into the student test execution."""
    # Set fake high-sensitivity keys in the parent process environment
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-secret-xyz-987")
    monkeypatch.setenv("GROQ_API_KEY", "fake-groq-secret-abc-654")
    monkeypatch.setenv("SECRET_TOKEN", "super-secret-token-321")

    student_code = "def get_status():\n    return 'active'\n"
    test_code = """
import os
import sys
import solution

def test_no_keys_in_environment():
    leaked = []
    for key in ['GEMINI_API_KEY', 'GROQ_API_KEY', 'SECRET_TOKEN']:
        if key in os.environ:
            leaked.append(key)
    # Print environment contents to verify stdout does not contain secret values
    print("SANDBOX_ENV_KEYS:", sorted(list(os.environ.keys())))
    assert not leaked, f"Keys leaked into sandbox environment: {leaked}"
    assert solution.get_status() == "active"
"""
    result = execute_verification("solution.py", student_code, test_code)

    assert result.passed is True
    assert result.timed_out is False
    assert result.tests_passed >= 1
    assert result.tests_failed == 0
    assert result.error is None

    # Assert none of the sensitive values appear anywhere in stdout or stderr
    assert "fake-gemini-secret-xyz-987" not in result.stdout
    assert "fake-gemini-secret-xyz-987" not in result.stderr
    assert "fake-groq-secret-abc-654" not in result.stdout
    assert "fake-groq-secret-abc-654" not in result.stderr
    assert "super-secret-token-321" not in result.stdout
    assert "super-secret-token-321" not in result.stderr


def test_passing_verification():
    """Verify normal successful pytest execution parses correctly."""
    student_code = """
def add(a: int, b: int) -> int:
    return a + b

def multiply(a: int, b: int) -> int:
    return a * b
"""
    test_code = """
import solution

def test_add():
    assert solution.add(2, 3) == 5

def test_multiply():
    assert solution.multiply(4, 5) == 20
"""
    result = execute_verification("solution.py", student_code, test_code)

    assert result.passed is True
    assert result.timed_out is False
    assert result.tests_passed == 2
    assert result.tests_failed == 0
    assert result.error is None
    assert result.runtime_ms > 0
    assert isinstance(result.runtime_ms, int)


def test_failing_verification():
    """Verify failing tests are caught, parsed, and recorded as passed=False."""
    student_code = """
def divide(a: int, b: int) -> float:
    return a / b
"""
    test_code = """
import solution

def test_divide():
    assert solution.divide(10, 2) == 3.0  # Incorrect expectation (5.0 != 3.0)
"""
    result = execute_verification("solution.py", student_code, test_code)

    assert result.passed is False
    assert result.timed_out is False
    assert result.tests_passed == 0
    assert result.tests_failed == 1
    assert result.error is None  # Normal test failure, not an infrastructure error
    assert "assert 5.0 == 3.0" in result.stdout or "FAILED" in result.stdout
    assert result.runtime_ms > 0


def test_syntax_error_in_student_code():
    """Verify syntax errors in student code return passed=False with error message."""
    student_code = """
def broken_syntax(
    return 123
"""
    test_code = """
import solution

def test_syntax():
    assert solution.broken_syntax() == 123
"""
    result = execute_verification("solution.py", student_code, test_code)

    assert result.passed is False
    assert result.timed_out is False
    assert result.tests_passed == 0
    assert result.error is not None
    assert (
        "SyntaxError" in result.error
        or "SyntaxError" in result.stdout
        or "SyntaxError" in result.stderr
    )


def test_infinite_loop_timeout(monkeypatch):
    """Verify execution with infinite loop times out and returns within timeout + 2 s."""
    # Test with a 2-second timeout to verify timing bounds
    monkeypatch.setattr(sandbox_runner, "SANDBOX_TIMEOUT_S", 2)

    student_code = """
def run_forever():
    while True:
        pass
"""
    test_code = """
import solution

def test_infinite():
    solution.run_forever()
"""
    start_time = time.perf_counter()
    result = execute_verification("solution.py", student_code, test_code)
    elapsed = time.perf_counter() - start_time

    assert result.passed is False
    assert result.timed_out is True
    assert result.tests_passed == 0
    assert result.tests_failed == 0
    assert result.error is not None
    assert "timed out" in result.error.lower()
    # Must return within timeout + 2 seconds
    assert elapsed <= 2.0 + 2.0
    assert result.runtime_ms >= 1500


def test_spawned_child_process_killed_on_timeout(tmp_path, monkeypatch):
    """Verify any child process spawned by student code is killed on timeout via process tree kill."""
    monkeypatch.setattr(sandbox_runner, "SANDBOX_TIMEOUT_S", 2)

    pid_file = tmp_path / "child.pid"
    # Student code spawns a background child process that sleeps for 60 seconds
    student_code = f"""
import subprocess
import sys
import time

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
with open(r"{pid_file}", "w") as f:
    f.write(str(child.pid))

# Parent hangs until timeout
time.sleep(60)
"""
    test_code = """
import solution

def test_dummy():
    pass
"""
    result = execute_verification("solution.py", student_code, test_code)

    assert result.passed is False
    assert result.timed_out is True

    assert pid_file.exists(), "Child PID file was not created by student code"
    child_pid = int(pid_file.read_text().strip())
    assert child_pid > 0

    time.sleep(0.5)

    if sys.platform == "win32":
        tasklist_out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {child_pid}"],
            capture_output=True,
            text=True,
        ).stdout
        assert (
            str(child_pid) not in tasklist_out
        ), f"Spawned child PID {child_pid} was not terminated by tree kill"
    else:
        with pytest.raises(OSError):
            os.kill(child_pid, 0)


def test_huge_output_truncated():
    """Verify that excessive stdout/stderr output is truncated to SANDBOX_OUTPUT_LIMIT."""
    student_code = """
import sys

def spam_output():
    # Write a huge amount of output to stderr and stdout
    sys.stderr.write("E" * 25000)
    print("O" * 25000)
    return False
"""
    test_code = """
import solution

def test_spam():
    assert solution.spam_output() is True
"""
    result = execute_verification("solution.py", student_code, test_code)

    assert len(result.stdout) <= SANDBOX_OUTPUT_LIMIT
    assert len(result.stderr) <= SANDBOX_OUTPUT_LIMIT
    assert result.passed is False
    assert result.tests_failed == 1


def test_parent_directory_traversal_rejected():
    """Verify that file_path containing '..' or invalid segments is rejected immediately."""
    student_code = "def safe(): return True\n"
    test_code = "def test_dummy(): pass\n"

    bad_paths = [
        "../outside.py",
        "foo/../../bar.py",
        "..",
        "/absolute/path/file.py",
        "C:/windows/win.ini",
        "test_vivavoce_challenge.py",
    ]

    for bad_path in bad_paths:
        result = execute_verification(bad_path, student_code, test_code)
        assert result.passed is False, f"Path {bad_path} was not rejected"
        assert result.timed_out is False
        assert result.error is not None
        assert result.tests_passed == 0
        assert result.tests_failed == 0


def test_no_tests_ran_handling():
    """Verify handling when pytest finds no test functions in the test code."""
    student_code = "def hello(): return 'world'\n"
    test_code = "# Empty test file with no test functions\nx = 1\n"

    result = execute_verification("solution.py", student_code, test_code)

    assert result.passed is False
    assert result.tests_passed == 0
    assert result.tests_failed == 0
    assert result.error is not None
    assert "no tests" in result.error.lower()


def test_collection_error_handling():
    """Verify collection errors (such as missing imports in test) return passed=False with error."""
    student_code = "def foo(): return 1\n"
    test_code = "import definitely_non_existent_module_12345\ndef test_foo(): pass\n"

    result = execute_verification("solution.py", student_code, test_code)

    assert result.passed is False
    assert result.tests_passed == 0
    assert result.error is not None
    assert (
        "Collection error" in result.error
        or "ModuleNotFoundError" in result.error
        or "ImportError" in result.error
    )


def test_package_subdirectory_import():
    """Verify student code in a subfolder package can be imported via pythonpath."""
    student_code = "def compute() -> int:\n    return 42\n"
    test_code = """
from mypkg.subpkg import math_ops

def test_math():
    assert math_ops.compute() == 42
"""
    result = execute_verification(
        "mypkg/subpkg/math_ops.py", student_code, test_code
    )

    assert result.passed is True
    assert result.tests_passed == 1
    assert result.tests_failed == 0
    assert result.error is None


def test_orphan_killed_after_pass(tmp_path):
    """Verify background processes started by student code are killed even when the test passes."""
    pid_file = tmp_path / "orphan.pid"
    student_code = f"""
import subprocess
import sys

# Start a background process that would live for 30s
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
with open(r"{pid_file}", "w") as f:
    f.write(str(child.pid))

def get_answer():
    return 42
"""
    test_code = """
import solution

def test_correct():
    assert solution.get_answer() == 42
"""
    child_pid = None
    try:
        result = execute_verification("solution.py", student_code, test_code)

        assert result.passed is True
        assert result.timed_out is False
        assert result.tests_passed == 1

        assert pid_file.exists(), "Child PID file was not written"
        child_pid = int(pid_file.read_text().strip())

        time.sleep(0.5)
        if sys.platform == "win32":
            tasklist_out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {child_pid}"],
                capture_output=True,
                text=True,
            ).stdout
            assert (
                str(child_pid) not in tasklist_out
            ), f"Orphan process {child_pid} was not killed on pass"
        else:
            with pytest.raises(OSError):
                os.kill(child_pid, 0)
    finally:
        if child_pid is not None:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(child_pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                try:
                    import signal

                    os.kill(child_pid, signal.SIGKILL)
                except Exception:
                    pass


def test_pipe_holding_grandchild_no_false_timeout(tmp_path):
    """Verify grandchild holding open file descriptors does not cause false timeout."""
    pid_file = tmp_path / "pipe_holder.pid"
    student_code = f"""
import subprocess
import sys

# Grandchild spawned with close_fds=False to hold inherited descriptors
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], close_fds=False)
with open(r"{pid_file}", "w") as f:
    f.write(str(child.pid))

def get_answer():
    return 100
"""
    test_code = """
import solution

def test_correct():
    assert solution.get_answer() == 100
"""
    child_pid = None
    try:
        start_time = time.perf_counter()
        result = execute_verification("solution.py", student_code, test_code)
        elapsed = time.perf_counter() - start_time

        assert result.passed is True
        assert result.timed_out is False
        assert result.tests_passed == 1
        assert elapsed < SANDBOX_TIMEOUT_S

        assert pid_file.exists(), "Child PID file was not written"
        child_pid = int(pid_file.read_text().strip())

        time.sleep(0.5)
        if sys.platform == "win32":
            tasklist_out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {child_pid}"],
                capture_output=True,
                text=True,
            ).stdout
            assert (
                str(child_pid) not in tasklist_out
            ), f"Pipe-holding process {child_pid} was not killed"
        else:
            with pytest.raises(OSError):
                os.kill(child_pid, 0)
    finally:
        if child_pid is not None:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(child_pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                try:
                    import signal

                    os.kill(child_pid, signal.SIGKILL)
                except Exception:
                    pass


def test_huge_output_streamed_is_bounded():
    """Verify streaming ~5 MB of output does not deadlock, blow memory, and is bounded."""
    student_code = """
import sys

def spam_5mb():
    chunk = "A" * 100000
    for _ in range(50):  # 5 MB total
        sys.stdout.write(chunk)
    sys.stdout.flush()
    return False
"""
    test_code = """
import solution

def test_spam_fail():
    assert solution.spam_5mb() is True  # Fails
"""
    start_time = time.perf_counter()
    result = execute_verification("solution.py", student_code, test_code)
    elapsed = time.perf_counter() - start_time

    assert result.passed is False
    assert result.timed_out is False
    assert result.tests_failed == 1
    assert len(result.stdout) <= SANDBOX_OUTPUT_LIMIT
    assert elapsed < SANDBOX_TIMEOUT_S
