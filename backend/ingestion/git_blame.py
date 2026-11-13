"""Map repository lines to the contributors who last changed them."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from backend.models.schemas import OwnedSymbol


_HEADER_RE = re.compile(r"^([0-9a-f^]{7,40})\s+\d+\s+(\d+)(?:\s+\d+)?$")


def _safe_repo_file(repo_root: Path, relative_file: str) -> Path:
    candidate = Path(relative_file)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Expected a repository-relative file path, got {relative_file!r}.")
    resolved_root = repo_root.resolve()
    resolved_file = (resolved_root / candidate).resolve()
    try:
        resolved_file.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"File path escapes the repository: {relative_file!r}.") from exc
    if not resolved_file.is_file():
        raise FileNotFoundError(f"Repository file not found: {relative_file}")
    return resolved_file


def _blame_file(repo_root: Path, relative_file: str) -> list[tuple[int, str, str]]:
    _safe_repo_file(repo_root, relative_file)
    result = subprocess.run(
        ["git", "-C", str(repo_root), "blame", "--line-porcelain", "--", relative_file],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or "git blame could not read this file"
        raise RuntimeError(f"git blame failed for {relative_file}: {detail}")

    line_authors: list[tuple[int, str, str]] = []
    line_number: int | None = None
    author = "Unknown author"
    commit = ""
    for line in result.stdout.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            commit = header.group(1).lstrip("^")
            line_number = int(header.group(2))
            author = "Unknown author"
        elif line.startswith("author "):
            author = line[len("author "):].strip() or "Unknown author"
        elif line.startswith("\t") and line_number is not None:
            line_authors.append((line_number, author, commit))
            line_number = None
    return line_authors


def extract_author_map(repo_path: str, files: list[str]) -> dict[str, list[OwnedSymbol]]:
    """Run line-porcelain blame and group consecutive lines by contributor."""
    repo_root = Path(repo_path).resolve()
    if not (repo_root / ".git").exists():
        raise ValueError(f"No Git metadata found at {repo_root}.")

    ownership: dict[str, list[OwnedSymbol]] = {}
    for relative_file in files:
        line_authors = _blame_file(repo_root, relative_file)
        if not line_authors:
            continue
        start, previous_line = line_authors[0][0], line_authors[0][0]
        current_author = line_authors[0][1]
        commits = {line_authors[0][2]}
        for line_number, author, commit in line_authors[1:]:
            if author == current_author and line_number == previous_line + 1:
                previous_line = line_number
                commits.add(commit)
                continue
            ownership.setdefault(current_author, []).append(
                OwnedSymbol(
                    file_path=relative_file,
                    line_start=start,
                    line_end=previous_line,
                    symbol_name=None,
                    commit_count=max(1, len(commits)),
                )
            )
            current_author = author
            start = previous_line = line_number
            commits = {commit}
        ownership.setdefault(current_author, []).append(
            OwnedSymbol(
                file_path=relative_file,
                line_start=start,
                line_end=previous_line,
                symbol_name=None,
                commit_count=max(1, len(commits)),
            )
        )

    return ownership


def author_map_as_dict(author_map: dict[str, list[OwnedSymbol]]) -> dict[str, list[dict[str, object]]]:
    """Serialize the blame result for JSON APIs and the frontend."""
    return {author: [symbol.model_dump() for symbol in symbols] for author, symbols in author_map.items()}
