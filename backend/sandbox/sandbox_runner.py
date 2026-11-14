"""
Multi-Language Isolated Code Sandbox Runner (backend/sandbox/sandbox_runner.py).
Owner: Senior Full-Stack Engineer (VivaVoce)

Executes candidate code across C++, Python, Java, and JavaScript inside an
isolated temporary directory with standard input/output evaluation against
test cases.

Features:
- Time limit: 4.0 seconds per testcase
- C++ (g++ 20 / C++17): g++ -O2 -std=c++17 main.cpp -o main.exe
- Python 3: python main.py
- Java: javac Main.java && java Main
- JavaScript: node main.js
- Custom input execution
- Detailed per-testcase execution feedback and real verdicts
- Backward compatibility for Repo Viva pytest verification
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from backend.models.schemas import (
    OATestCase,
    RunCodeResponse,
    TestCaseResult,
)


def _minimal_environment() -> dict[str, str]:
    allowed_keys = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    env = {k: os.environ[k] for k in allowed_keys if k in os.environ}
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def execute_multi_language_sandbox(
    language: str,
    source_code: str,
    test_cases: List[OATestCase],
    run_hidden: bool = False,
    custom_input: Optional[str] = None,
) -> RunCodeResponse:
    """
    Compiles (if needed) and executes source code against given test cases or custom input.
    Returns real verdict: Accepted, Wrong Answer, Compilation Error, Runtime Error, Time Limit Exceeded.
    """
    lang_clean = (language or "python").lower().strip()
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="vivavoce-oa-") as temp_dir:
        root = Path(temp_dir)
        env = _minimal_environment()

        # Determine target file and compile command
        executable_cmd: List[str] = []

        if lang_clean in ("cpp", "c++", "c"):
            src_file = root / "main.cpp"
            src_file.write_text(source_code, encoding="utf-8")
            exe_path = root / ("main.exe" if sys.platform == "win32" else "main")

            # Look up g++ binary
            gpp_cmd = shutil.which("g++") or "g++"
            compile_res = subprocess.run(
                [gpp_cmd, "-O2", "-std=c++17", str(src_file), "-o", str(exe_path)],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if compile_res.returncode != 0:
                return RunCodeResponse(
                    passed=False,
                    verdict="Compilation Error",
                    stdout="",
                    stderr=compile_res.stderr or compile_res.stdout or "Compilation failed.",
                    runtime_ms=int((time.perf_counter() - started) * 1000),
                    test_results=[],
                    total_cases=len(test_cases),
                    passed_cases=0,
                )
            executable_cmd = [str(exe_path)]

        elif lang_clean in ("java", "openjdk"):
            src_file = root / "Main.java"
            src_file.write_text(source_code, encoding="utf-8")

            javac_cmd = shutil.which("javac") or "javac"
            try:
                compile_res = subprocess.run(
                    [javac_cmd, str(src_file)],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if compile_res.returncode != 0:
                    return RunCodeResponse(
                        passed=False,
                        verdict="Compilation Error",
                        stdout="",
                        stderr=compile_res.stderr or "Java compilation failed.",
                        runtime_ms=int((time.perf_counter() - started) * 1000),
                        test_results=[],
                        total_cases=len(test_cases),
                        passed_cases=0,
                    )
            except OSError as exc:
                return RunCodeResponse(
                    passed=False,
                    verdict="Compilation Error",
                    stdout="",
                    stderr=f"Java compiler (javac) not found: {exc}",
                    runtime_ms=int((time.perf_counter() - started) * 1000),
                    test_results=[],
                    total_cases=len(test_cases),
                    passed_cases=0,
                )

            java_cmd = shutil.which("java") or "java"
            executable_cmd = [java_cmd, "-cp", str(root), "Main"]

        elif lang_clean in ("javascript", "js", "node"):
            src_file = root / "main.js"
            src_file.write_text(source_code, encoding="utf-8")
            node_cmd = shutil.which("node") or "node"
            executable_cmd = [node_cmd, str(src_file)]

        else:
            # Default: Python
            src_file = root / "main.py"
            src_file.write_text(source_code, encoding="utf-8")
            executable_cmd = [sys.executable, str(src_file)]

        # Determine which test cases to run
        active_cases: List[OATestCase] = []
        if custom_input is not None:
            active_cases = [OATestCase(stdin=custom_input, expected_output="", is_hidden=False)]
        else:
            active_cases = [tc for tc in test_cases if run_hidden or not tc.is_hidden]
            if not active_cases and test_cases:
                active_cases = test_cases  # fallback to all if no visible

        test_results: List[TestCaseResult] = []
        passed_count = 0
        overall_verdict = "Accepted"
        last_stderr = ""
        total_stdout = ""

        for idx, tc in enumerate(active_cases, start=1):
            try:
                run_res = subprocess.run(
                    executable_cmd,
                    cwd=root,
                    env=env,
                    input=tc.stdin,
                    capture_output=True,
                    text=True,
                    timeout=4.0,
                    check=False,
                )
                actual_out = run_res.stdout
                actual_err = run_res.stderr

                if run_res.returncode != 0:
                    overall_verdict = "Runtime Error"
                    last_stderr = actual_err or f"Process exited with code {run_res.returncode}"
                    test_results.append(
                        TestCaseResult(
                            case_num=idx,
                            stdin=tc.stdin,
                            expected_output=tc.expected_output,
                            actual_output=actual_out,
                            passed=False,
                            is_hidden=tc.is_hidden,
                            error=last_stderr,
                        )
                    )
                    break

                expected_clean = tc.expected_output.strip()
                actual_clean = actual_out.strip()

                # If checking against expected output (standard testcase)
                is_custom = custom_input is not None
                passed = is_custom or (actual_clean == expected_clean)
                if passed and not is_custom:
                    passed_count += 1
                elif not passed:
                    if overall_verdict == "Accepted":
                        overall_verdict = "Wrong Answer"

                total_stdout += actual_out
                test_results.append(
                    TestCaseResult(
                        case_num=idx,
                        stdin=tc.stdin,
                        expected_output=tc.expected_output,
                        actual_output=actual_out,
                        passed=passed,
                        is_hidden=tc.is_hidden,
                        error=None,
                    )
                )

            except subprocess.TimeoutExpired:
                overall_verdict = "Time Limit Exceeded"
                last_stderr = "Time limit exceeded (4.0s)."
                test_results.append(
                    TestCaseResult(
                        case_num=idx,
                        stdin=tc.stdin,
                        expected_output=tc.expected_output,
                        actual_output="",
                        passed=False,
                        is_hidden=tc.is_hidden,
                        error="Execution timed out after 4 seconds.",
                    )
                )
                break
            except OSError as exc:
                overall_verdict = "Runtime Error"
                last_stderr = str(exc)
                test_results.append(
                    TestCaseResult(
                        case_num=idx,
                        stdin=tc.stdin,
                        expected_output=tc.expected_output,
                        actual_output="",
                        passed=False,
                        is_hidden=tc.is_hidden,
                        error=str(exc),
                    )
                )
                break

    runtime_ms = int((time.perf_counter() - started) * 1000)
    all_passed = (passed_count == len(active_cases)) and len(active_cases) > 0 and overall_verdict == "Accepted"

    return RunCodeResponse(
        passed=all_passed or (custom_input is not None and overall_verdict != "Runtime Error"),
        verdict=overall_verdict if custom_input is None else "Executed",
        stdout=total_stdout,
        stderr=last_stderr,
        runtime_ms=runtime_ms,
        test_results=test_results,
        total_cases=len(active_cases),
        passed_cases=passed_count,
    )


def execute_verification(
    file_path: str,
    student_code: str,
    test_code: str,
) -> RunCodeResponse:
    """Legacy backward-compatible pytest runner for Repo Viva L4 code verification."""
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="vivavoce-pytest-") as temp_dir:
        root = Path(temp_dir)
        student_file = root / "student_solution.py"
        student_file.write_text(student_code, encoding="utf-8")

        test_file = root / "test_student_code.py"
        test_file.write_text(test_code, encoding="utf-8")

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
            )
            stdout = completed.stdout[-12_000:]
            stderr = completed.stderr[-12_000:]
            passed = completed.returncode == 0
            verdict = "Accepted" if passed else "Wrong Answer"
        except subprocess.TimeoutExpired as exc:
            stdout = ""
            stderr = "Verification exceeded 4-second time limit."
            passed = False
            verdict = "Time Limit Exceeded"
        except OSError as exc:
            stdout = ""
            stderr = f"Could not start pytest: {exc}"
            passed = False
            verdict = "Runtime Error"

    runtime_ms = int((time.perf_counter() - started) * 1000)
    return RunCodeResponse(
        passed=passed,
        verdict=verdict,
        stdout=stdout,
        stderr=stderr,
        runtime_ms=runtime_ms,
        test_results=[],
        total_cases=1 if passed else 0,
        passed_cases=1 if passed else 0,
    )
