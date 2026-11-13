"""Clone GitHub repositories and build a compact, AST-grounded code index."""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from backend.models.schemas import ASTFunctionSymbol, OwnedSymbol, RepoFile, RepoIndex

SUPPORTED_SUFFIXES = {".py", ".ts", ".js"}
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "dist", "build",
    "__pycache__", ".next", "coverage",
}
MAX_SOURCE_BYTES = 1_000_000
IMPORT_RE = re.compile(
    r"(?:\bfrom\s+|\bimport\s+|\brequire\s*\(\s*|\bimport\s*\(\s*)"
    r"['\"]([^'\"]+)['\"]"
)


def _validate_github_url(github_url: str) -> str:
    parsed = urlsplit(github_url.strip())
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in {"github.com", "www.github.com"}
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Provide a public GitHub HTTPS URL, such as https://github.com/owner/repo.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or any(part in {".", ".."} for part in parts):
        raise ValueError("The GitHub URL must point directly to an owner/repository.")
    repository = parts[1]
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not repository:
        raise ValueError("The GitHub repository name is missing.")
    return f"https://github.com/{parts[0]}/{repository}.git"


def _clone_repository(github_url: str, destination: Path) -> None:
    """Prefer GitPython; use the git executable when GitPython is unavailable."""
    try:
        from git import Repo  # type: ignore[import-not-found]
    except ImportError:
        result = subprocess.run(
            ["git", "clone", "--depth", "50", "--no-tags", "--", github_url, str(destination)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"git clone failed: {detail or 'unknown git error'}")
        return

    Repo.clone_from(github_url, str(destination), depth=50, multi_options=["--no-tags"])


def _candidate_files(repo_root: Path) -> list[Path]:
    root = repo_root.resolve()
    result: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        relative = path.relative_to(repo_root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
            if resolved.stat().st_size <= MAX_SOURCE_BYTES:
                result.append(path)
        except (OSError, ValueError):
            # Ignore unreadable files and symlinks that escape the cloned repo.
            continue
    return result


def _module_references(relative_path: str, text: str) -> list[str]:
    references = [match.group(1) for match in IMPORT_RE.finditer(text)]
    if relative_path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return references
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                references.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                references.append(node.module)
    return references


def _rank_files(repo_root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    root = repo_root.resolve()
    records: list[dict[str, Any]] = []
    path_by_key: dict[str, str] = {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        key = PurePosixPath(relative).with_suffix("").as_posix().lower()
        path_by_key[key] = relative
        path_by_key.setdefault(PurePosixPath(relative).stem.lower(), relative)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        records.append({
            "path": relative,
            "text": text,
            "line_count": len(text.splitlines()),
            "references": _module_references(relative, text),
        })

    import_counts: Counter[str] = Counter()
    for record in records:
        importer = PurePosixPath(record["path"])
        for raw_reference in record["references"]:
            reference = raw_reference.replace("\\", "/").strip()
            keys: list[str] = []
            if reference.startswith("."):
                base = (importer.parent / reference).as_posix()
                keys.append(PurePosixPath(base).with_suffix("").as_posix().lower())
                keys.append(PurePosixPath(base).name.lower())
            else:
                module_key = reference.replace(".", "/").lower()
                keys.append(module_key)
                keys.append(PurePosixPath(module_key).name.lower())
            for key in keys:
                target = path_by_key.get(key)
                if target and target != record["path"]:
                    import_counts[target] += 1
                    break

    ranked = []
    for record in records:
        frequency = import_counts[record["path"]]
        # Import frequency breaks ties while keeping substantial files prominent.
        score = record["line_count"] + 20 * frequency
        ranked.append({
            "file_path": record["path"],
            "line_count": record["line_count"],
            "import_frequency": frequency,
            "rank_score": score,
            "_text": record["text"],
        })
    ranked.sort(key=lambda item: (-item["rank_score"], -item["line_count"], item["file_path"]))
    return ranked


def _python_symbols(file_path: str, source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return [], []

    constants: list[dict[str, Any]] = []
    for node in tree.body:
        targets: list[ast.expr] = []
        value_node: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value_node = node.value
        for target in targets:
            for name_node in ast.walk(target):
                if not isinstance(name_node, ast.Name) or not name_node.id.isupper():
                    continue
                try:
                    value: Any = ast.literal_eval(value_node) if value_node is not None else None
                except (ValueError, TypeError, SyntaxError):
                    value = ast.get_source_segment(source, value_node) if value_node else None
                constants.append({
                    "file_path": file_path,
                    "name": name_node.id,
                    "value": value,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                })

    def call_name(expr: ast.expr) -> str:
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            parent = call_name(expr.value)
            return f"{parent}.{expr.attr}" if parent else expr.attr
        return ""

    constant_names = sorted({item["name"] for item in constants})
    functions: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            argument_nodes = (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            )
            args = [arg.arg for arg in argument_nodes]
            if node.args.vararg:
                args.append("*" + node.args.vararg.arg)
            if node.args.kwarg:
                args.append("**" + node.args.kwarg.arg)
            start_line = min(
                [node.lineno] + [decorator.lineno for decorator in node.decorator_list]
            )
            snippet = ast.get_source_segment(source, node) or ""
            functions.append({
                "file_path": file_path,
                "name": node.name,
                "args": args,
                "docstring": ast.get_docstring(node),
                "line_start": start_line,
                "line_end": getattr(node, "end_lineno", node.lineno),
                "calls": sorted({
                    name for call in ast.walk(node) if isinstance(call, ast.Call)
                    if (name := call_name(call.func))
                }),
                "constants": constant_names,
                "code_snippet": snippet,
            })

    return functions, constants


def _javascript_functions(file_path: str, source: str) -> list[dict[str, Any]]:
    """Extract common named and arrow functions when the file is JS/TS."""
    patterns = (
        re.compile(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)"),
        re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>"),
    )
    functions: list[dict[str, Any]] = []
    lines = source.splitlines()
    for pattern in patterns:
        for match in pattern.finditer(source):
            start = source.count("\n", 0, match.start()) + 1
            args = [item.strip().split(":", 1)[0].strip() for item in match.group(2).split(",") if item.strip()]
            functions.append({
                "file_path": file_path,
                "name": match.group(1),
                "args": args,
                "docstring": "",
                "line_start": start,
                # JS/TS boundaries are approximate; Python functions use exact AST spans.
                "line_end": min(len(lines), start + 1),
                "calls": [],
                "constants": [],
                "code_snippet": lines[start - 1] if start <= len(lines) else "",
            })
    functions.sort(key=lambda item: (item["line_start"], item["name"]))
    return functions


def _build_index(github_url: str, repo_root: Path) -> RepoIndex:
    ranked = _rank_files(repo_root, _candidate_files(repo_root))
    selected = ranked[:15]
    symbols: list[ASTFunctionSymbol] = []
    repo_files: list[RepoFile] = []
    constant_descriptions: list[str] = []
    for record in selected:
        file_path = record["file_path"]
        if file_path.lower().endswith(".py"):
            found_functions, found_constants = _python_symbols(file_path, record["_text"])
            constant_names = sorted({item["name"] for item in found_constants})
            for function in found_functions:
                function["constants"] = constant_names
                symbols.append(ASTFunctionSymbol(**function))
            constant_descriptions.extend(
                f"{file_path}:{item['name']}={item['value']}" for item in found_constants
            )
        else:
            found_functions = _javascript_functions(file_path, record["_text"])
            for line_number, line in enumerate(record["_text"].splitlines(), start=1):
                match = re.match(r"\s*(?:export\s+)?(?:const|let|var)\s+([A-Z][A-Z0-9_]*)\s*=\s*(.+?);?\s*$", line)
                if match:
                    constant_descriptions.append(f"{file_path}:{match.group(1)}={match.group(2)}")
                    for function in found_functions:
                        function["constants"].append(match.group(1))
            symbols.extend(ASTFunctionSymbol(**function) for function in found_functions)

        suffix = Path(file_path).suffix.lower()
        language = "python" if suffix == ".py" else "typescript" if suffix == ".ts" else "javascript"
        repo_files.append(RepoFile(
            path=file_path,
            content=record["_text"],
            language=language,
            line_count=record["line_count"],
        ))

    name_parts = [part for part in urlsplit(github_url).path.rstrip("/").split("/") if part]
    repo_name = name_parts[-1].removesuffix(".git") if name_parts else "repository"
    rankings = ", ".join(
        f"{record['file_path']} ({record['line_count']} lines, {record['import_frequency']} imports)"
        for record in selected
    )
    constants_text = "; ".join(constant_descriptions[:80]) or "none detected"
    return RepoIndex(
        repo_name=repo_name,
        github_url=github_url,
        local_path=str(repo_root),
        files=repo_files,
        symbols=symbols,
        authors=[],
        author_map={},
        summary=(
            f"Indexed {len(repo_files)} source files ranked by line count and import frequency: {rankings}. "
            f"Top-level constants: {constants_text}."
        ),
    )


def clone_and_index_repo(github_url: str) -> RepoIndex:
    """Shallow-clone a GitHub repository and return its top-15 source index."""
    normalized_url = _validate_github_url(github_url)
    clone_parent = Path(tempfile.mkdtemp(prefix="vivavoce-repo-"))
    destination = clone_parent / "repository"
    try:
        _clone_repository(normalized_url, destination)
        return _build_index(normalized_url, destination)
    except Exception:
        shutil.rmtree(clone_parent, ignore_errors=True)
        raise


def load_demo_repo_index() -> RepoIndex:
    """Load the checked-in pre-indexed demo without network access."""
    cache_root = Path(__file__).resolve().parent.parent / "demo_cache"
    index_path = cache_root / "sample_repo_index.json"
    data = json.loads(index_path.read_text(encoding="utf-8"))
    sample_root = cache_root / "sample_repo"
    files: list[RepoFile] = []
    for relative_path in data["files"]:
        source_path = sample_root / relative_path
        content = source_path.read_text(encoding="utf-8")
        files.append(RepoFile(
            path=relative_path,
            content=content,
            language="python",
            line_count=len(content.splitlines()),
        ))

    constants_by_file: dict[str, list[str]] = {}
    for item in data.get("constants", []):
        constants_by_file.setdefault(item["file_path"], []).append(item["name"])
    symbols: list[ASTFunctionSymbol] = []
    for item in data.get("functions", []):
        source_path = sample_root / item["file_path"]
        content = source_path.read_text(encoding="utf-8")
        snippet = "\n".join(content.splitlines()[item["line_start"] - 1:item["line_end"]])
        symbols.append(ASTFunctionSymbol(
            name=item["name"],
            file_path=item["file_path"],
            line_start=item["line_start"],
            line_end=item["line_end"],
            args=item.get("args", []),
            docstring=item.get("docstring"),
            calls=item.get("calls", []),
            constants=constants_by_file.get(item["file_path"], []),
            code_snippet=snippet,
        ))

    author_map = {
        author: [OwnedSymbol(**symbol) for symbol in ranges]
        for author, ranges in data.get("authors", {}).items()
    }
    return RepoIndex(
        repo_name="sample_repo",
        github_url="demo://vivavoce/sample_repo",
        local_path=str(sample_root),
        files=files,
        symbols=symbols,
        authors=list(author_map),
        author_map=author_map,
        summary=(
            "Offline pre-indexed multi-author demo repository with a planted loader edge-case bug. "
            "Files are ordered by line count and import frequency."
        ),
    )
