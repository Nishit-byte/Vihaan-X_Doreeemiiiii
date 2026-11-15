"""Git blame extraction, author identity normalization, and symbol ownership mapping."""

from __future__ import annotations

import collections
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .config import log
from .models import AuthorStat, FileIndex, IngestionError, OwnedSymbol, RepoIndex
from .repo_parser import _parse_python_file, index_repo_path

# Regex to identify GitHub noreply emails:
# e.g. "12345+username@users.noreply.github.com", "username@users.noreply.github.com",
# "12345+username@noreply.github.com", "username@noreply.github.com"
_NOREPLY_RE = re.compile(
    r"^(?:[0-9]+\+)?([^@]+)@(?:users\.)?noreply\.github\.com$", re.IGNORECASE
)

# Header line pattern in git blame --line-porcelain:
# <sha> <orig_line> <final_line> [<group_size>]
_BLAME_HEADER_RE = re.compile(r"^([0-9a-fA-F^]{7,40})\s+(\d+)\s+(\d+)(?:\s+\d+)?$")


def blame_file(repo_path: str, file_path: str) -> list[dict]:
    """Execute git blame --line-porcelain -w on a file and return per-line metadata.

    Returns:
        list[dict]: List of line blame dicts with keys:
            - 'line': int (final line number, 1-based)
            - 'author': str (author name)
            - 'email': str (author email with <> stripped)
            - 'commit': str (commit SHA)
        Uncommitted lines ('Not Committed Yet') are skipped.
    """
    repo_root = Path(repo_path).resolve()
    if not repo_root.is_dir():
        raise IngestionError(
            f"Repository directory not found: {repo_path}",
            detail="Directory does not exist",
        )

    # Resolve file path relative to repo root
    cand_path = Path(file_path)
    if cand_path.is_absolute():
        try:
            rel_file = str(cand_path.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel_file = str(cand_path).replace("\\", "/")
    else:
        rel_file = str(cand_path).replace("\\", "/")

    if rel_file.startswith("./"):
        rel_file = rel_file[2:]

    # Ensure full file path exists on disk
    full_file = repo_root / rel_file
    if not full_file.is_file():
        log.warning("Blame target file does not exist: %s in %s", rel_file, repo_root)
        return []

    cmd = [
        "git",
        "-C",
        str(repo_root),
        "blame",
        "--line-porcelain",
        "-w",
        "--",
        rel_file,
    ]

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "echo"

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,  # 10 s per file timeout
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.warning("git blame timed out for file %s in %s", rel_file, repo_root)
        return []
    except Exception as exc:
        log.warning("git blame failed for file %s in %s: %s", rel_file, repo_root, exc)
        return []

    if proc.returncode != 0:
        log.debug(
            "git blame returned non-zero code %d for %s: %s",
            proc.returncode,
            rel_file,
            proc.stderr.strip(),
        )
        return []

    lines: list[dict] = []
    current_commit = ""
    current_line = 0
    current_author = "Unknown"
    current_email = ""

    for raw_line in proc.stdout.splitlines():
        header_match = _BLAME_HEADER_RE.match(raw_line)
        if header_match:
            current_commit = header_match.group(1).lstrip("^")
            current_line = int(header_match.group(3))
            current_author = "Unknown"
            current_email = ""
        elif raw_line.startswith("author "):
            current_author = raw_line[7:].strip()
        elif raw_line.startswith("author-mail "):
            raw_mail = raw_line[12:].strip()
            if raw_mail.startswith("<") and raw_mail.endswith(">"):
                raw_mail = raw_mail[1:-1].strip()
            current_email = raw_mail
        elif raw_line.startswith("\t"):
            # End of porcelain header block for current line
            is_uncommitted = (
                current_author == "Not Committed Yet"
                or current_commit.startswith("0000000")
                or current_email.lower() == "not.committed.yet"
            )
            if not is_uncommitted and current_line > 0:
                lines.append(
                    {
                        "line": current_line,
                        "author": current_author,
                        "email": current_email,
                        "commit": current_commit,
                    }
                )
            current_line = 0
            current_author = "Unknown"
            current_email = ""
            current_commit = ""

    return lines


def normalize_identity(
    name: str, email: str, alias_map: Optional[dict[str, str]] = None
) -> str:
    """Normalize git committer/author identity by email and alias mapping.

    Rules:
    - lower-cased email is the key.
    - GitHub noreply emails (e.g. '123+user@users.noreply.github.com') -> 'user'.
    - alias_map applied to both name and email (maps aliases to canonical display name).
    - If alias_map provides a match for email or name, the mapped name is returned.
    """
    clean_name = name.strip() if name else ""
    clean_email = email.strip().strip("<>").strip() if email else ""
    email_lower = clean_email.lower()

    # Extract GitHub noreply username if present
    noreply_user: Optional[str] = None
    if email_lower:
        m = _NOREPLY_RE.match(email_lower)
        if m:
            noreply_user = m.group(1)

    # Check alias_map
    if alias_map:
        candidates = [clean_email, email_lower, clean_name, clean_name.lower()]
        if noreply_user:
            candidates.extend([noreply_user, noreply_user.lower()])

        for c in candidates:
            if c and c in alias_map:
                target = alias_map[c]
                if target in alias_map:
                    target = alias_map[target]
                return target

    # If GitHub noreply email and no alias
    if noreply_user:
        return noreply_user

    # Default to name if present
    if clean_name:
        return clean_name

    # Fall back to email prefix or email
    if clean_email:
        return clean_email.split("@")[0] if "@" in clean_email else clean_email

    return "Unknown"


def _get_author_key(
    name: str, email: str, alias_map: Optional[dict[str, str]] = None
) -> str:
    """Determine the grouping key for an author line."""
    clean_name = name.strip() if name else ""
    clean_email = email.strip().strip("<>").strip() if email else ""
    email_lower = clean_email.lower()

    noreply_user: Optional[str] = None
    if email_lower:
        m = _NOREPLY_RE.match(email_lower)
        if m:
            noreply_user = m.group(1)

    if alias_map:
        candidates = [clean_email, email_lower, clean_name, clean_name.lower()]
        if noreply_user:
            candidates.extend([noreply_user, noreply_user.lower()])

        for c in candidates:
            if c and c in alias_map:
                target = alias_map[c]
                if target in alias_map:
                    target = alias_map[target]
                return target.lower() if "@" in target else target

    if noreply_user:
        return noreply_user

    if email_lower:
        return email_lower

    return clean_name.lower() or "unknown"


def _build_author_identities(
    lines: list[dict], alias_map: Optional[dict[str, str]] = None
) -> tuple[dict[str, str], Callable[[dict], str], dict[str, str]]:
    """Build key-to-display-name and key-to-email maps across all blamed lines.

    The display name for each key is the most frequent spelling for that key.
    Returns:
        tuple[key_to_display, line_to_display_fn, key_to_email]
    """
    key_name_counts: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: collections.defaultdict(int)
    )
    key_email_counts: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: collections.defaultdict(int)
    )

    for l in lines:
        name = l.get("author", "").strip()
        email = l.get("email", "").strip().strip("<>").strip()
        key = _get_author_key(name, email, alias_map)

        if name and name != "Not Committed Yet":
            key_name_counts[key][name] += 1
        if email and email.lower() != "not.committed.yet":
            key_email_counts[key][email] += 1

    key_to_display: dict[str, str] = {}
    key_to_email: dict[str, str] = {}

    for key, name_counts in key_name_counts.items():
        # If key was mapped directly to a display name in alias_map
        if alias_map and any(
            target == key for target in alias_map.values()
        ) and "@" not in key:
            key_to_display[key] = key
        else:
            if name_counts:
                # Most frequent spelling; tie-break by longer name (e.g. "Aman Verma" > "Aman V")
                best_name = max(
                    name_counts.keys(),
                    key=lambda n: (name_counts[n], len(n)),
                )
                key_to_display[key] = best_name
            else:
                m = _NOREPLY_RE.match(key)
                if m:
                    key_to_display[key] = m.group(1)
                elif "@" in key:
                    key_to_display[key] = key.split("@")[0]
                else:
                    key_to_display[key] = key

        # Canonical email
        email_counts = key_email_counts.get(key, {})
        if email_counts:
            best_email = max(email_counts.keys(), key=lambda e: email_counts[e])
            key_to_email[key] = best_email
        else:
            key_to_email[key] = key if "@" in key else ""

    # Also handle keys that had no names recorded (e.g. only email)
    for key, email_counts in key_email_counts.items():
        if key not in key_to_display:
            if email_counts:
                best_email = max(email_counts.keys(), key=lambda e: email_counts[e])
                key_to_email[key] = best_email
                key_to_display[key] = best_email.split("@")[0] if "@" in best_email else best_email
            else:
                key_to_display[key] = key
                key_to_email[key] = key if "@" in key else ""

    def line_to_display(l: dict) -> str:
        k = _get_author_key(l.get("author", ""), l.get("email", ""), alias_map)
        return key_to_display.get(k, normalize_identity(l.get("author", ""), l.get("email", ""), alias_map))

    return key_to_display, line_to_display, key_to_email


def extract_author_map(
    repo_path: str,
    files: list[str],
    index: Optional[RepoIndex] = None,
    alias_map: Optional[dict[str, str]] = None,
) -> dict[str, list[OwnedSymbol]]:
    """Map each author to the AST symbols (functions) they own and loose lines.

    A function's owner is the author with the most lines in its range (tie -> earliest line).
    Share = owner lines / function lines.
    Loose lines outside functions are grouped per file with symbol=None.
    If index is None, index the files using A2's index_repo_path to get function ranges.
    """
    repo_root = Path(repo_path).resolve()
    if not repo_root.is_dir():
        raise IngestionError(
            f"Repository directory not found: {repo_path}",
            detail="Directory does not exist",
        )

    if not files:
        return {}

    # If index is None, index the files with A2's code
    if index is None:
        index = index_repo_path(str(repo_root))

    # 1. Blame each file
    file_blames: dict[str, list[dict]] = {}
    all_lines: list[dict] = []
    for f_path in files:
        blamed = blame_file(str(repo_root), f_path)
        file_blames[f_path] = blamed
        all_lines.extend(blamed)

    if not all_lines:
        return {}

    # 2. Build canonical identities for all authors
    key_to_display, line_to_display, _ = _build_author_identities(all_lines, alias_map)

    author_map: dict[str, list[OwnedSymbol]] = collections.defaultdict(list)

    # 3. Process each file
    for f_path in files:
        blamed_lines = file_blames.get(f_path, [])
        if not blamed_lines:
            continue

        # Posix relative path for index lookup
        rel_posix = str(Path(f_path)).replace("\\", "/")
        if rel_posix.startswith("./"):
            rel_posix = rel_posix[2:]

        file_idx = index.get_file(rel_posix)
        if file_idx is None:
            full_p = repo_root / rel_posix
            if full_p.is_file() and rel_posix.endswith(".py"):
                file_idx = _parse_python_file(rel_posix, str(full_p), 0)

        functions = file_idx.functions if file_idx else []

        # Track line numbers claimed by any function
        function_line_numbers: set[int] = set()
        for fn in functions:
            for l_num in range(fn.line_start, fn.line_end + 1):
                function_line_numbers.add(l_num)

        # Map lines in file by line number for fast lookup
        line_by_num: dict[int, dict] = {l["line"]: l for l in blamed_lines}

        # Process each function
        for fn in functions:
            fn_total_lines = max(1, fn.line_end - fn.line_start + 1)
            # Find blamed lines in fn range
            fn_blamed = [
                line_by_num[l_num]
                for l_num in range(fn.line_start, fn.line_end + 1)
                if l_num in line_by_num
            ]

            if not fn_blamed:
                continue

            author_counts: dict[str, int] = collections.defaultdict(int)
            earliest_line: dict[str, int] = {}

            for l in fn_blamed:
                auth = line_to_display(l)
                author_counts[auth] += 1
                if auth not in earliest_line or l["line"] < earliest_line[auth]:
                    earliest_line[auth] = l["line"]

            # Owner: most lines, tie -> earliest line
            owner = max(
                author_counts.keys(),
                key=lambda a: (author_counts[a], -earliest_line[a]),
            )
            lines_owned = author_counts[owner]
            share = round(lines_owned / fn_total_lines, 4)

            author_map[owner].append(
                OwnedSymbol(
                    file_path=rel_posix,
                    symbol=fn.qualname,
                    line_start=fn.line_start,
                    line_end=fn.line_end,
                    lines_owned=lines_owned,
                    share=share,
                )
            )

        # Process loose lines outside functions grouped per file
        loose_blamed = [
            l for l in blamed_lines if l["line"] not in function_line_numbers
        ]
        if loose_blamed:
            total_loose = len(loose_blamed)
            author_loose_lines: dict[str, list[int]] = collections.defaultdict(list)
            for l in loose_blamed:
                auth = line_to_display(l)
                author_loose_lines[auth].append(l["line"])

            for auth, l_nums in author_loose_lines.items():
                lines_owned = len(l_nums)
                share = round(lines_owned / total_loose, 4)
                author_map[auth].append(
                    OwnedSymbol(
                        file_path=rel_posix,
                        symbol=None,
                        line_start=min(l_nums),
                        line_end=max(l_nums),
                        lines_owned=lines_owned,
                        share=share,
                    )
                )

    # Sort each author's symbols by file_path and line_start
    for auth in author_map:
        author_map[auth].sort(key=lambda s: (s.file_path, s.line_start))

    return dict(author_map)


def compute_authorship_stats(
    repo_path: str,
    files: list[str],
    alias_map: Optional[dict[str, str]] = None,
) -> list[AuthorStat]:
    """Compute overall authorship breakdown and shares across all indexed files.

    Note on shallow clones (P2-2.9 limitation):
    When a repository is cloned with shallow depth (e.g. --depth 50), Git blame
    cannot traverse beyond the shallow boundary commit. The boundary commit
    absorbs all older history and attributes earlier lines to whoever authored
    the boundary commit. For accurate full-history authorship in repositories
    with deep history, a full clone (FULL_CLONE_MAX_KB) or unshallowing is required.

    Returns:
        list[AuthorStat]: Sorted descending by share_of_lines, shares summing to 1.0 (±0.001).
    """
    repo_root = Path(repo_path).resolve()
    if not repo_root.is_dir():
        raise IngestionError(
            f"Repository directory not found: {repo_path}",
            detail="Directory does not exist",
        )

    if not files:
        return []

    all_lines: list[dict] = []
    for f_path in files:
        blamed = blame_file(str(repo_root), f_path)
        all_lines.extend(blamed)

    if not all_lines:
        return []

    key_to_display, line_to_display, key_to_email = _build_author_identities(
        all_lines, alias_map
    )

    # Count lines per author
    author_line_counts: dict[str, int] = collections.defaultdict(int)
    author_display_to_email: dict[str, str] = {}

    for l in all_lines:
        auth = line_to_display(l)
        author_line_counts[auth] += 1
        key = _get_author_key(l["author"], l["email"], alias_map)
        if auth not in author_display_to_email:
            author_display_to_email[auth] = key_to_email.get(key, l.get("email", ""))

    total_lines = sum(author_line_counts.values())
    if total_lines == 0:
        return []

    stats: list[AuthorStat] = []
    for auth, count in author_line_counts.items():
        share = round(count / total_lines, 4)
        email = author_display_to_email.get(auth, "")
        stats.append(
            AuthorStat(
                author=auth,
                email=email,
                lines=count,
                share_of_lines=share,
            )
        )

    # Sort descending by share_of_lines, tie-break by lines descending, then author name
    stats.sort(key=lambda s: (-s.share_of_lines, -s.lines, s.author))

    # Ensure shares sum to 1.0 (±0.001)
    shares_sum = sum(s.share_of_lines for s in stats)
    diff = round(1.0 - shares_sum, 4)
    if diff != 0 and stats:
        # Adjust top author so sum is exactly 1.0
        stats[0].share_of_lines = round(stats[0].share_of_lines + diff, 4)

    return stats


def list_authors(author_map: dict[str, list[OwnedSymbol]]) -> list[str]:
    """List authors ordered by their ownership / contribution (descending lines owned)."""
    if not author_map:
        return []

    def _author_sort_key(auth: str) -> tuple[int, int, str]:
        syms = author_map[auth]
        total_lines = sum(s.lines_owned for s in syms)
        total_syms = len(syms)
        return (-total_lines, -total_syms, auth)

    return sorted(author_map.keys(), key=_author_sort_key)
