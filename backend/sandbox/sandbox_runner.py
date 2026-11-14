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


def _sanitize_cpp_code(code: str) -> str:
    """
    Sanitizes C++ source and driver code to fix common LLM formatting quirks:
    - Replaces invalid directives like `#iostream` or `#vector` with `#include <iostream>`
    - Corrects `#include<iostream>` or `#include iostream` to `#include <iostream>`
    - Sanitizes unrecognized invalid preprocessor directives that break g++
    """
    if not code:
        return ""

    valid_directives = {
        "include", "define", "ifdef", "ifndef", "endif", "if", "else", "elif",
        "pragma", "line", "error", "warning", "undef"
    }
    known_headers = {
        "iostream", "vector", "string", "algorithm", "cmath", "climits", "map", "set",
        "queue", "deque", "stack", "sstream", "iomanip", "bits/stdc++.h", "cstdio",
        "cstring", "cstdlib", "cassert", "numeric", "functional", "tuple", "utility",
        "chrono", "random", "unordered_map", "unordered_set", "list", "forward_list",
        "bitset", "regex", "fstream", "cctype"
    }

    sanitized_lines = []
    for line in code.splitlines():
        # Match standard directives: e.g. #include <iostream>, #include<vector>, #define X
        m = re.match(r"^\s*#\s*([a-zA-Z_][a-zA-Z0-9_]*)(.*)", line)
        if m:
            directive = m.group(1).strip()
            rest = m.group(2).strip()
            if directive in valid_directives:
                if directive == "include":
                    if rest.startswith('"') and rest.endswith('"'):
                        line = f"#include {rest}"
                    else:
                        header_name = rest.strip('<>" \t')
                        if header_name:
                            line = f"#include <{header_name}>"
                        else:
                            line = "// [sanitized empty include]"
            elif directive in known_headers:
                line = f"#include <{directive}>"
            else:
                line = f"// [sanitized] {line}"
        else:
            # Check for naked #<header>
            m_angle = re.match(r"^\s*#\s*<([a-zA-Z0-9_/\.]+)>", line)
            if m_angle:
                line = f"#include <{m_angle.group(1)}>"
            elif re.match(r"^\s*#\s*[^\s]", line):
                # Any unrecognized line starting with # that isn't a valid directive
                line = f"// [sanitized] {line}"

        sanitized_lines.append(line)
    return "\n".join(sanitized_lines)


def _strip_solution_class_braces(code: str) -> str:
    """Removes any class Solution { ... }; block using brace-depth matching, ignoring strings and comments."""
    if not code:
        return ""
    pattern = re.compile(r"\b(?:(?:public|private|protected)\s+)?class\s+Solution\b[^{]*\{")
    max_loops = 5
    while max_loops > 0:
        max_loops -= 1
        match = pattern.search(code)
        if not match:
            break
        start = match.start()
        depth = 1
        pos = match.end()
        n = len(code)
        in_line_comment = False
        in_block_comment = False
        in_str = None

        while pos < n and depth > 0:
            ch = code[pos]
            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
            elif in_block_comment:
                if ch == '*' and pos + 1 < n and code[pos + 1] == '/':
                    in_block_comment = False
                    pos += 1
            elif in_str:
                if ch == '\\':
                    pos += 1  # skip escaped character
                elif ch == in_str:
                    in_str = None
            else:
                if ch == '/' and pos + 1 < n and code[pos + 1] == '/':
                    in_line_comment = True
                    pos += 1
                elif ch == '/' and pos + 1 < n and code[pos + 1] == '*':
                    in_block_comment = True
                    pos += 1
                elif ch in ('"', "'"):
                    in_str = ch
                elif ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
            pos += 1

        if depth == 0:
            while pos < n and code[pos] in (' ', '\t', ';'):
                pos += 1
            if pos < n and code[pos] == '\n':
                pos += 1
            code = code[:start] + code[pos:]
        else:
            # Unmatched braces: abort safely without truncating file
            break

    return code


def _clean_driver_cpp(code: str) -> str:
    """Strips class Solution, duplicate #include and using namespace lines from driver_code."""
    if not code:
        return ""
    sanitized = _sanitize_cpp_code(code)
    stripped = _strip_solution_class_braces(sanitized)
    
    # If stripping somehow removed main, recover from sanitized
    if "main(" not in stripped and "main(" in sanitized:
        main_pos = sanitized.find("int main")
        if main_pos == -1:
            main_pos = sanitized.find("main(")
        if main_pos != -1:
            stripped = sanitized[main_pos:]
        else:
            stripped = sanitized

    lines = []
    for line in stripped.splitlines():
        trimmed = line.strip()
        if (
            trimmed.startswith("#include")
            or trimmed.startswith("// [sanitized]")
            or trimmed == "using namespace std;"
            or re.match(r"^\s*#\s*iostream\b", trimmed)
            or re.match(r"^\s*#\s*vector\b", trimmed)
            or re.match(r"^\s*#\s*string\b", trimmed)
        ):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _generate_fallback_cpp_main(source_code: str) -> Optional[str]:
    """
    Synthesizes a minimal C++ stdin/stdout driver by inspecting public methods in class Solution.
    Handles standard single-method classes with strings, integers, and vectors.
    """
    if not source_code:
        return None

    # Find public method in class Solution
    pattern = re.compile(
        r"(?:int|bool|string|long\s+long|double|void|vector<int>|vector<string>)\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)"
    )
    match = pattern.search(source_code)
    if not match:
        return None

    method_name = match.group(1)
    if method_name in ("main", "if", "for", "while", "switch"):
        return None

    raw_params = [p.strip() for p in match.group(2).split(",") if p.strip()]
    if not raw_params:
        return (
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n"
            "    Solution sol;\n"
            f"    cout << sol.{method_name}() << \"\\n\";\n"
            "    return 0;\n"
            "}"
        )

    # Detect parameter types
    if len(raw_params) == 2 and "string" in raw_params[0] and "int" in raw_params[1]:
        return (
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n"
            "    string s;\n"
            "    int k;\n"
            "    if (cin >> s >> k) {\n"
            "        Solution sol;\n"
            f"        cout << sol.{method_name}(s, k) << \"\\n\";\n"
            "    }\n"
            "    return 0;\n"
            "}"
        )
    elif len(raw_params) == 2 and "vector<int>" in raw_params[0] and "int" in raw_params[1]:
        return (
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n"
            "    int n, k;\n"
            "    if (cin >> n >> k) {\n"
            "        vector<int> nums(n);\n"
            "        for (int i = 0; i < n; i++) cin >> nums[i];\n"
            "        Solution sol;\n"
            f"        cout << sol.{method_name}(nums, k) << \"\\n\";\n"
            "    }\n"
            "    return 0;\n"
            "}"
        )
    elif len(raw_params) == 1 and "vector<int>" in raw_params[0]:
        return (
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n"
            "    int n;\n"
            "    if (cin >> n) {\n"
            "        vector<int> nums(n);\n"
            "        for (int i = 0; i < n; i++) cin >> nums[i];\n"
            "        Solution sol;\n"
            f"        cout << sol.{method_name}(nums) << \"\\n\";\n"
            "    }\n"
            "    return 0;\n"
            "}"
        )
    elif len(raw_params) == 1 and "string" in raw_params[0]:
        return (
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n"
            "    string s;\n"
            "    if (cin >> s) {\n"
            "        Solution sol;\n"
            f"        cout << sol.{method_name}(s) << \"\\n\";\n"
            "    }\n"
            "    return 0;\n"
            "}"
        )

    return None


def _clean_driver_java(code: str) -> str:
    """Strips class Solution and duplicate import lines from driver_code."""
    if not code:
        return ""
    code = _strip_solution_class_braces(code)
    lines = []
    for line in code.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("import java."):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _clean_driver_python(code: str) -> str:
    """Strips class Solution and duplicate import lines from Python driver_code."""
    if not code:
        return ""
    lines = code.splitlines()
    cleaned = []
    in_solution = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^class\s+Solution\b", stripped):
            in_solution = True
            continue
        if in_solution:
            if not stripped or line.startswith((" ", "\t")):
                continue
            else:
                in_solution = False
        if stripped.startswith((
            "import sys", "from typing import", "import collections",
            "import heapq", "import math", "import bisect"
        )):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _clean_driver_javascript(code: str) -> str:
    """Strips class Solution / var Solution and duplicate fs imports from JS driver_code."""
    if not code:
        return ""
    code = _strip_solution_class_braces(code)
    lines = []
    for line in code.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("const fs = require('fs')") or trimmed.startswith('const fs = require("fs")'):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


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
    driver_code: Optional[str] = None,
) -> RunCodeResponse:
    """
    Compiles (if needed) and executes source code against given test cases or custom input.
    Automatically prepends standard language headers and appends problem driver_code
    so candidate only needs to write inside authentic LeetCode class Solution.
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
            sanitized_source = _sanitize_cpp_code(source_code)
            cleaned_driver = _clean_driver_cpp(driver_code) if driver_code else ""

            has_source_main = bool(re.search(r"\b(?:int|void)\s+main\s*\(", sanitized_source))
            if not has_source_main:
                has_driver_main = bool(re.search(r"\b(?:int|void)\s+main\s*\(", cleaned_driver))
                if not has_driver_main:
                    fallback = _generate_fallback_cpp_main(sanitized_source)
                    if fallback:
                        cleaned_driver = fallback
                    else:
                        return RunCodeResponse(
                            passed=False,
                            verdict="Compilation Error",
                            stdout="",
                            stderr="Missing main() entrypoint in execution driver.",
                            runtime_ms=int((time.perf_counter() - started) * 1000),
                            test_results=[],
                            total_cases=len(test_cases),
                            passed_cases=0,
                        )
                effective_code = f"#include <bits/stdc++.h>\nusing namespace std;\n\n{sanitized_source}\n\n{cleaned_driver}"
            else:
                effective_code = f"#include <bits/stdc++.h>\nusing namespace std;\n\n{sanitized_source}"
            src_file.write_text(effective_code, encoding="utf-8")
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
            sanitized_source = re.sub(r"\bpublic\s+class\s+Solution\b", "class Solution", source_code)
            cleaned_driver = _clean_driver_java(driver_code) if driver_code else ""
            if "public static void main" not in sanitized_source:
                effective_code = f"import java.io.*;\nimport java.util.*;\n\n{sanitized_source}\n\n{cleaned_driver}"
            else:
                effective_code = f"import java.io.*;\nimport java.util.*;\n\n{sanitized_source}"
            src_file.write_text(effective_code, encoding="utf-8")

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
            cleaned_driver = _clean_driver_javascript(driver_code) if driver_code else ""
            if "readFileSync" not in source_code:
                effective_code = f"const fs = require('fs');\n\n{source_code}\n\n{cleaned_driver}"
            else:
                effective_code = source_code
            src_file.write_text(effective_code, encoding="utf-8")
            node_cmd = shutil.which("node") or "node"
            executable_cmd = [node_cmd, str(src_file)]

        else:
            # Default: Python
            src_file = root / "main.py"
            cleaned_driver = _clean_driver_python(driver_code) if driver_code else ""
            if "__main__" not in source_code:
                effective_code = f"from typing import *\nimport sys, math, heapq, bisect, collections\n\n{source_code}\n\n{cleaned_driver}"
            else:
                effective_code = source_code
            src_file.write_text(effective_code, encoding="utf-8")
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
