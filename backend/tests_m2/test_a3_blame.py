"""Unit and integration tests for TASK A3: git blame author map, authorship stats, and identity normalization."""

import os
import subprocess
from pathlib import Path
from typing import Optional

import pytest

from ingestion.git_blame import (
    blame_file,
    compute_authorship_stats,
    extract_author_map,
    list_authors,
    normalize_identity,
)
from ingestion.models import AuthorStat, IngestionError, OwnedSymbol, RepoIndex


def _run_git(
    repo_dir: Path,
    args: list[str],
    author_name: Optional[str] = None,
    author_email: Optional[str] = None,
) -> subprocess.CompletedProcess:
    cmd_env = os.environ.copy()
    cmd_env["GIT_TERMINAL_PROMPT"] = "0"
    cmd_env["GCM_INTERACTIVE"] = "never"
    cmd_env["GIT_ASKPASS"] = "echo"

    if author_name:
        cmd_env["GIT_AUTHOR_NAME"] = author_name
        cmd_env["GIT_COMMITTER_NAME"] = author_name
    if author_email:
        cmd_env["GIT_AUTHOR_EMAIL"] = author_email
        cmd_env["GIT_COMMITTER_EMAIL"] = author_email

    res = subprocess.run(
        ["git"] + args,
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=cmd_env,
        check=True,
    )
    return res


@pytest.fixture
def blame_fixture_repo(tmp_path: Path):
    """Create a fixture git repository with 3 authors:
    1. Aman Verma: commits under two names ('Aman Verma', 'Aman V.') and two emails
       ('aman@example.com', 'aman.work@example.com') to test alias_map and frequency merging.
    2. priya-dev: commits with a GitHub noreply email ('12345+priya-dev@users.noreply.github.com').
    3. Rohan Gupta: commits with standard name and email ('Rohan Gupta', 'rohan@example.com').
    """
    repo_dir = tmp_path / "blame_repo"
    repo_dir.mkdir()

    _run_git(repo_dir, ["init", "-b", "main"])
    _run_git(repo_dir, ["config", "user.name", "Initial Author"])
    _run_git(repo_dir, ["config", "user.email", "initial@example.com"])

    # Commit 1: Aman Verma (spelling 1, email 1)
    # Creates calculator.py and helper.py
    calc_path = repo_dir / "calculator.py"
    calc_path.write_text(
        "# Calculator Module\n"
        "import math\n"
        "\n"
        "\n"
        "def add(a: int, b: int) -> int:\n"
        "    \"\"\"Add two numbers.\"\"\"\n"
        "    result = a + b\n"
        "    return result\n"
        "\n"
        "\n"
        "def multiply(a: int, b: int) -> int:\n"
        "    return a * b\n",
        encoding="utf-8",
    )
    helper_path = repo_dir / "helper.py"
    helper_path.write_text(
        "MAX_RETRIES = 3\n"
        "\n"
        "\n"
        "def log_msg(msg: str) -> None:\n"
        "    print(msg)\n",
        encoding="utf-8",
    )

    _run_git(repo_dir, ["add", "."])
    _run_git(
        repo_dir,
        ["commit", "-m", "Initial commit by Aman Verma"],
        author_name="Aman Verma",
        author_email="aman@example.com",
    )

    # Commit 2: priya-dev (GitHub noreply email)
    # Adds tie_check function and modifies multiply
    calc_path.write_text(
        "# Calculator Module\n"
        "import math\n"
        "\n"
        "\n"
        "def add(a: int, b: int) -> int:\n"
        "    \"\"\"Add two numbers.\"\"\"\n"
        "    result = a + b\n"
        "    return result\n"
        "\n"
        "\n"
        "def multiply(a: int, b: int) -> int:\n"
        "    if a == 0 or b == 0:\n"
        "        return 0\n"
        "    return a * b\n"
        "\n"
        "\n"
        "def tie_check(x: int) -> int:\n"
        "    # Line 1 by Priya\n"
        "    return x\n",
        encoding="utf-8",
    )
    _run_git(repo_dir, ["add", "calculator.py"])
    _run_git(
        repo_dir,
        ["commit", "-m", "Priya adds tie_check and updates multiply"],
        author_name="priya-dev",
        author_email="12345+priya-dev@users.noreply.github.com",
    )

    # Commit 3: Rohan Gupta
    # Adds subtract, and modifies tie_check (adding 1 line to create tie with Priya)
    calc_path.write_text(
        "# Calculator Module\n"
        "import math\n"
        "\n"
        "\n"
        "def add(a: int, b: int) -> int:\n"
        "    \"\"\"Add two numbers.\"\"\"\n"
        "    result = a + b\n"
        "    return result\n"
        "\n"
        "\n"
        "def multiply(a: int, b: int) -> int:\n"
        "    if a == 0 or b == 0:\n"
        "        return 0\n"
        "    return a * b\n"
        "\n"
        "\n"
        "def tie_check(x: int) -> int:\n"
        "    # Line 1 by Priya\n"
        "    val = x * 2\n",
        encoding="utf-8",
    )
    # Also add a rohan_util function in helper.py
    helper_path.write_text(
        "MAX_RETRIES = 3\n"
        "\n"
        "\n"
        "def log_msg(msg: str) -> None:\n"
        "    print(msg)\n"
        "\n"
        "\n"
        "def rohan_util(val: int) -> int:\n"
        "    \"\"\"Utility function by Rohan.\"\"\"\n"
        "    return val * 10\n",
        encoding="utf-8",
    )
    _run_git(repo_dir, ["add", "."])
    _run_git(
        repo_dir,
        ["commit", "-m", "Rohan adds tie_check edit and rohan_util"],
        author_name="Rohan Gupta",
        author_email="rohan@example.com",
    )

    # Commit 4: Aman V. (spelling 2, email 2: aman.work@example.com)
    # Adds divide to calculator.py
    calc_path.write_text(
        "# Calculator Module\n"
        "import math\n"
        "\n"
        "\n"
        "def add(a: int, b: int) -> int:\n"
        "    \"\"\"Add two numbers.\"\"\"\n"
        "    result = a + b\n"
        "    return result\n"
        "\n"
        "\n"
        "def multiply(a: int, b: int) -> int:\n"
        "    if a == 0 or b == 0:\n"
        "        return 0\n"
        "    return a * b\n"
        "\n"
        "\n"
        "def tie_check(x: int) -> int:\n"
        "    # Line 1 by Priya\n"
        "    val = x * 2\n"
        "\n"
        "\n"
        "def divide(a: int, b: int) -> float:\n"
        "    \"\"\"Divide safely.\"\"\"\n"
        "    if b == 0:\n"
        "        raise ZeroDivisionError(\"division by zero\")\n"
        "    return a / b\n",
        encoding="utf-8",
    )
    _run_git(repo_dir, ["add", "calculator.py"])
    _run_git(
        repo_dir,
        ["commit", "-m", "Aman V. adds divide"],
        author_name="Aman V.",
        author_email="aman.work@example.com",
    )

    return repo_dir


def test_normalize_identity():
    """Verify normalize_identity handles lowercased emails, GitHub noreply, and alias maps."""
    # 1. Basic name and email
    assert (
        normalize_identity("Aman Verma", "aman@example.com")
        == "Aman Verma"
    )

    # 2. Lower-cased email matching
    alias_map = {
        "aman.work@example.com": "Aman Verma",
        "Aman V.": "Aman Verma",
        "alias_user@example.com": "Canonical Name",
    }
    assert (
        normalize_identity("Aman V.", "aman.work@example.com", alias_map)
        == "Aman Verma"
    )
    assert (
        normalize_identity("Any", "alias_user@example.com", alias_map)
        == "Canonical Name"
    )
    assert (
        normalize_identity("Aman V.", "other@example.com", alias_map)
        == "Aman Verma"
    )

    # 3. GitHub noreply email normalizes to username
    assert (
        normalize_identity(
            "priya-dev", "12345+priya-dev@users.noreply.github.com"
        )
        == "priya-dev"
    )
    assert (
        normalize_identity("", "12345+octocat@users.noreply.github.com")
        == "octocat"
    )
    assert (
        normalize_identity("Octocat", "octocat@users.noreply.github.com")
        == "octocat"
    )
    assert (
        normalize_identity("Anything", "999+someone@noreply.github.com")
        == "someone"
    )

    # 4. Fallback when name is empty and not noreply
    assert normalize_identity("", "developer@company.org") == "developer"
    assert normalize_identity("", "") == "Unknown"


def test_blame_file_metadata(blame_fixture_repo: Path):
    """Verify blame_file returns accurate line numbers, authors, emails, and commits."""
    blame = blame_file(str(blame_fixture_repo), "calculator.py")
    assert len(blame) > 0

    for item in blame:
        assert "line" in item
        assert isinstance(item["line"], int)
        assert item["line"] >= 1
        assert "author" in item
        assert "email" in item
        assert not item["email"].startswith("<")
        assert not item["email"].endswith(">")
        assert "commit" in item
        assert len(item["commit"]) >= 7


def test_blame_file_skips_uncommitted_lines(blame_fixture_repo: Path):
    """Verify that uncommitted lines ('Not Committed Yet') are skipped."""
    calc_path = blame_fixture_repo / "calculator.py"
    original_blame = blame_file(str(blame_fixture_repo), "calculator.py")
    original_line_count = len(original_blame)

    # Append uncommitted lines without staging or committing
    calc_path.write_text(
        calc_path.read_text(encoding="utf-8") + "\n# Uncommitted line 1\n# Uncommitted line 2\n",
        encoding="utf-8",
    )

    new_blame = blame_file(str(blame_fixture_repo), "calculator.py")
    # All new uncommitted lines must be skipped, leaving only committed lines
    assert len(new_blame) == original_line_count
    for item in new_blame:
        assert item["author"] != "Not Committed Yet"
        assert not item["commit"].startswith("0000000")


def test_blame_file_empty_and_missing(blame_fixture_repo: Path):
    """Verify blame_file handles empty and nonexistent files gracefully."""
    empty_file = blame_fixture_repo / "empty.py"
    empty_file.write_text("", encoding="utf-8")
    _run_git(blame_fixture_repo, ["add", "empty.py"])
    _run_git(blame_fixture_repo, ["commit", "-m", "Add empty file"])

    # Empty file has 0 blamed lines
    assert blame_file(str(blame_fixture_repo), "empty.py") == []

    # Non-existent file returns empty list
    assert blame_file(str(blame_fixture_repo), "nonexistent.py") == []

    # Non-existent repo directory raises IngestionError
    with pytest.raises(IngestionError):
        blame_file(str(blame_fixture_repo / "no_such_dir"), "calculator.py")


def test_extract_author_map_ownership_and_ties(blame_fixture_repo: Path):
    """Verify extract_author_map function ownership, tie-breaking, shares, and loose lines."""
    alias_map = {
        "aman.work@example.com": "Aman Verma",
        "Aman V.": "Aman Verma",
    }
    files = ["calculator.py", "helper.py"]

    # Call with index=None to test automatic AST indexing fallback
    author_map = extract_author_map(
        str(blame_fixture_repo), files=files, index=None, alias_map=alias_map
    )

    assert "Aman Verma" in author_map
    assert "priya-dev" in author_map
    assert "Rohan Gupta" in author_map

    # 1. Check Aman Verma's ownership
    aman_symbols = {s.symbol for s in author_map["Aman Verma"] if s.symbol}
    assert "add" in aman_symbols
    assert "divide" in aman_symbols  # Written as Aman V., merged to Aman Verma

    add_sym = next(s for s in author_map["Aman Verma"] if s.symbol == "add")
    assert add_sym.file_path == "calculator.py"
    assert add_sym.share == 1.0
    assert add_sym.lines_owned == (add_sym.line_end - add_sym.line_start + 1)

    # 2. Check tie-breaking: tie_check was written by Priya (line 1) and Rohan (line 2)
    # Tie broken by earliest line -> Priya wins
    priya_symbols = {s.symbol for s in author_map["priya-dev"] if s.symbol}
    assert "tie_check" in priya_symbols
    tie_sym = next(s for s in author_map["priya-dev"] if s.symbol == "tie_check")
    assert tie_sym.lines_owned >= 1
    assert 0.0 < tie_sym.share <= 1.0

    # 3. Check Rohan Gupta's ownership
    rohan_symbols = {s.symbol for s in author_map["Rohan Gupta"] if s.symbol}
    assert "rohan_util" in rohan_symbols

    # 4. Check loose lines (lines outside functions grouped per file with symbol=None)
    all_syms = [s for sym_list in author_map.values() for s in sym_list]
    loose_syms = [s for s in all_syms if s.symbol is None]
    assert len(loose_syms) > 0
    for ls in loose_syms:
        assert ls.symbol is None
        assert ls.line_start <= ls.line_end
        assert ls.lines_owned >= 1
        assert 0.0 < ls.share <= 1.0


def test_compute_authorship_stats(blame_fixture_repo: Path):
    """Verify compute_authorship_stats returns descending shares summing to 1.0."""
    alias_map = {
        "aman.work@example.com": "Aman Verma",
        "Aman V.": "Aman Verma",
    }
    files = ["calculator.py", "helper.py"]

    stats = compute_authorship_stats(
        str(blame_fixture_repo), files=files, alias_map=alias_map
    )

    # Exactly 3 authors merged
    authors = [s.author for s in stats]
    assert set(authors) == {"Aman Verma", "priya-dev", "Rohan Gupta"}

    # Sorted descending by share_of_lines
    shares = [s.share_of_lines for s in stats]
    assert shares == sorted(shares, reverse=True)

    # Sum of shares equals 1.0 (±0.001)
    assert abs(sum(shares) - 1.0) <= 0.001

    # Check email presence
    for s in stats:
        assert isinstance(s.lines, int)
        assert s.lines > 0
        assert isinstance(s.email, str)
        assert "@" in s.email or s.author == "priya-dev"

    # Verify shallow-clone limitation is documented in docstring (P2-2.9)
    doc = compute_authorship_stats.__doc__ or ""
    assert "shallow" in doc.lower()
    assert "P2-2.9" in doc


def test_list_authors_order(blame_fixture_repo: Path):
    """Verify list_authors returns authors ordered descending by total lines owned."""
    alias_map = {
        "aman.work@example.com": "Aman Verma",
        "Aman V.": "Aman Verma",
    }
    files = ["calculator.py", "helper.py"]

    author_map = extract_author_map(
        str(blame_fixture_repo), files=files, alias_map=alias_map
    )
    ordered_authors = list_authors(author_map)

    # Check all authors are in list
    assert set(ordered_authors) == {"Aman Verma", "priya-dev", "Rohan Gupta"}

    # Check ordering by total lines owned descending
    lines_owned = [
        sum(s.lines_owned for s in author_map[a]) for a in ordered_authors
    ]
    assert lines_owned == sorted(lines_owned, reverse=True)

    # Aman Verma should have the most lines in this fixture
    assert ordered_authors[0] == "Aman Verma"


def test_empty_repository_inputs(tmp_path: Path):
    """Verify git_blame functions handle empty file lists and invalid directories safely."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    # Empty files list returns empty structures
    assert extract_author_map(str(empty_dir), files=[]) == {}
    assert compute_authorship_stats(str(empty_dir), files=[]) == []
    assert list_authors({}) == []
