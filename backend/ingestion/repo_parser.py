"""GitHub repository cloning, filtering, and AST indexing for Python repositories."""

import ast
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from .config import (
    CLONE_DEPTH,
    CLONE_TIMEOUT_S,
    FULL_CLONE_MAX_KB,
    MAX_FILE_LINES,
    MAX_INDEXED_FILES,
    MAX_REPO_PY_FILES,
    WORK_DIR,
    log,
)
from .models import (
    ConstantInfo,
    FileIndex,
    FunctionInfo,
    IngestionError,
    RepoIndex,
)

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


def validate_github_url(url: str) -> tuple[str, str]:
    """Validate a GitHub URL and return (owner, repo).

    Only URLs of the form https://github.com/<owner>/<repo> (with optional .git
    or trailing slash) are accepted.

    Returns:
        tuple[str, str]: (owner, repo)

    Raises:
        IngestionError: If the URL is invalid, empty, or does not point to a GitHub repo.
    """
    if not url or not isinstance(url, str) or not url.strip():
        raise IngestionError(
            "Please provide a GitHub repository URL.",
            detail="URL is empty or not a string",
        )

    stripped_url = url.strip()
    try:
        parsed = urllib.parse.urlparse(stripped_url)
    except Exception as e:
        raise IngestionError(
            "Invalid repository URL format.",
            detail=str(e),
        ) from e

    if parsed.scheme != "https":
        raise IngestionError(
            "Invalid GitHub URL. Only secure HTTPS URLs are supported (https://github.com/<owner>/<repo>).",
            detail=f"Scheme '{parsed.scheme}' is not allowed",
        )

    if parsed.netloc.lower() != "github.com":
        raise IngestionError(
            "Invalid repository host. Only repositories hosted on github.com are supported.",
            detail=f"Host '{parsed.netloc}' is not github.com",
        )

    if parsed.query or parsed.fragment:
        raise IngestionError(
            "Invalid GitHub URL. Query parameters and fragments are not allowed.",
            detail=f"Query: {parsed.query}, Fragment: {parsed.fragment}",
        )

    raw_path = parsed.path
    if "//" in raw_path:
        raise IngestionError(
            "Invalid GitHub URL. Path contains empty segments.",
            detail=f"Path: {raw_path}",
        )

    clean_path = raw_path.strip("/")
    parts = clean_path.split("/")
    if len(parts) != 2:
        raise IngestionError(
            "Invalid GitHub URL. Please provide a repository URL in the format https://github.com/<owner>/<repo>.",
            detail=f"Expected exactly 2 path segments, got {len(parts)} ({parts})",
        )

    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo or owner in (".", "..") or repo in (".", ".."):
        raise IngestionError(
            "Invalid GitHub URL. Owner and repository name cannot be empty.",
            detail=f"owner='{owner}', repo='{repo}'",
        )

    valid_name_pattern = re.compile(r"^[A-Za-z0-9_.-]+$")
    if not valid_name_pattern.match(owner) or not valid_name_pattern.match(repo):
        raise IngestionError(
            "Invalid GitHub URL. Owner or repository name contains invalid characters.",
            detail=f"owner='{owner}', repo='{repo}'",
        )

    return owner, repo


def cleanup_repo(path: str) -> None:
    """Remove cloned repo files cleanly, handling Windows read-only .git files."""
    if not path:
        return

    target = Path(path)
    if not target.exists() and not os.path.islink(path):
        return

    def _remove_readonly(func, file_path, exc_info_or_exc=None):
        try:
            os.chmod(file_path, stat.S_IWRITE | stat.S_IWUSR)
            func(file_path)
        except Exception as e:
            log.debug("cleanup_repo retry failed for %s: %s", file_path, e)

    try:
        if target.is_file() or target.is_symlink() or os.path.islink(path):
            try:
                os.chmod(path, stat.S_IWRITE | stat.S_IWUSR)
                os.unlink(path)
            except Exception:
                pass
            return

        if sys.version_info >= (3, 12):
            shutil.rmtree(
                path,
                onexc=lambda func, p, exc: _remove_readonly(func, p, exc),
            )
        else:
            shutil.rmtree(
                path,
                onerror=lambda func, p, exc_info: _remove_readonly(func, p, exc_info),
            )
    except Exception as e:
        log.warning("cleanup_repo encountered error while removing %s: %s", path, e)

    # Extra pass if Windows filesystem briefly kept directory handle open
    if os.path.exists(path):
        try:
            for root, dirs, files in os.walk(path, topdown=False):
                for name in files:
                    fp = os.path.join(root, name)
                    try:
                        os.chmod(fp, stat.S_IWRITE | stat.S_IWUSR)
                        os.unlink(fp)
                    except Exception:
                        pass
                for name in dirs:
                    dp = os.path.join(root, name)
                    try:
                        os.chmod(dp, stat.S_IWRITE | stat.S_IWUSR)
                        os.rmdir(dp)
                    except Exception:
                        pass
            if os.path.exists(path):
                os.chmod(path, stat.S_IWRITE | stat.S_IWUSR)
                os.rmdir(path)
        except Exception:
            pass


def clone_repo(github_url: str, dest_dir: Optional[str] = None) -> str:
    """Clone a GitHub repository via git subprocess and return local directory path.

    Repos <= FULL_CLONE_MAX_KB (via GitHub API size check) get a full clone,
    otherwise --depth CLONE_DEPTH. Timeout is CLONE_TIMEOUT_S.

    Raises:
        IngestionError: If the URL is invalid, cloning times out, or git clone fails (e.g. 404/private).
    """
    owner, repo = validate_github_url(github_url)

    if dest_dir is None:
        os.makedirs(WORK_DIR, exist_ok=True)
        unique_folder = f"{owner}_{repo}_{uuid.uuid4().hex[:10]}"
        dest_dir = os.path.join(WORK_DIR, unique_folder)
    else:
        parent_dir = os.path.dirname(dest_dir)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    # Optional GitHub API size check (best effort; failure falls back to shallow clone)
    is_shallow = True
    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        resp = httpx.get(
            api_url,
            headers={"User-Agent": "vivavoce-m2"},
            timeout=3.0,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            repo_size_kb = data.get("size", 0)
            if isinstance(repo_size_kb, (int, float)) and repo_size_kb <= FULL_CLONE_MAX_KB:
                is_shallow = False
                log.info(
                    "Repo size is %d KB (<= %d KB limit); performing full clone",
                    repo_size_kb,
                    FULL_CLONE_MAX_KB,
                )
            else:
                log.info(
                    "Repo size is %s KB (> %d KB limit); performing shallow clone with depth %d",
                    str(repo_size_kb),
                    FULL_CLONE_MAX_KB,
                    CLONE_DEPTH,
                )
    except Exception as e:
        log.debug("GitHub API size check failed or skipped: %s; using shallow clone", e)
        is_shallow = True

    cmd = ["git", "clone"]
    if is_shallow:
        cmd.extend(["--depth", str(CLONE_DEPTH)])
    cmd.extend([f"https://github.com/{owner}/{repo}.git", dest_dir])

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "echo"

    try:
        proc = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=CLONE_TIMEOUT_S,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        cleanup_repo(dest_dir)
        raise IngestionError(
            f"Cloning repository '{github_url}' timed out after {CLONE_TIMEOUT_S} seconds.",
            detail=f"TimeoutExpired: {CLONE_TIMEOUT_S}s",
        ) from e
    except FileNotFoundError as e:
        cleanup_repo(dest_dir)
        raise IngestionError(
            "Git command-line executable was not found on this system.",
            detail=str(e),
        ) from e
    except Exception as e:
        cleanup_repo(dest_dir)
        raise IngestionError(
            f"Failed to clone repository '{github_url}'.",
            detail=str(e),
        ) from e

    if proc.returncode != 0:
        cleanup_repo(dest_dir)
        stderr_msg = proc.stderr.strip()
        if (
            "could not read Username" in stderr_msg
            or "Authentication failed" in stderr_msg
            or "Repository not found" in stderr_msg
        ):
            user_msg = (
                f"Repository '{github_url}' was not found or is private. "
                "Please verify the URL and ensure the repository is public."
            )
        else:
            user_msg = f"Failed to clone repository '{github_url}'."
        raise IngestionError(user_msg, detail=stderr_msg)

    return os.path.abspath(dest_dir)


def _is_test_file(rel_path: str) -> bool:
    """Check if a relative POSIX file path represents a test file."""
    norm = rel_path.lower().replace("\\", "/")
    parts = norm.split("/")
    filename = parts[-1]
    for dir_part in parts[:-1]:
        if dir_part in ("tests", "test", "testing"):
            return True
    if (
        filename.startswith("test_")
        or filename.endswith("_test.py")
        or filename in ("test.py", "tests.py", "conftest.py")
    ):
        return True
    return False


def _extract_imported_modules(
    curr_rel_path: str,
    tree: ast.AST,
    module_to_file: dict[str, str],
) -> set[str]:
    """Find other candidate repo files imported by this file AST."""
    imported_targets: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name in module_to_file:
                    target = module_to_file[name]
                    if target != curr_rel_path:
                        imported_targets.add(target)

        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            mod = node.module or ""

            if level == 0:
                # Absolute import
                if mod in module_to_file:
                    target = module_to_file[mod]
                    if target != curr_rel_path:
                        imported_targets.add(target)
                for alias in node.names:
                    combined = f"{mod}.{alias.name}" if mod else alias.name
                    if combined in module_to_file:
                        target = module_to_file[combined]
                        if target != curr_rel_path:
                            imported_targets.add(target)

                # Sibling imports without package prefix if inside subpackage
                curr_dir = os.path.dirname(curr_rel_path).replace("\\", "/")
                dir_parts = [p for p in curr_dir.split("/") if p]
                if dir_parts:
                    same_dir_mod = ".".join(dir_parts + [mod]) if mod else ""
                    if same_dir_mod and same_dir_mod in module_to_file:
                        target = module_to_file[same_dir_mod]
                        if target != curr_rel_path:
                            imported_targets.add(target)
                    for alias in node.names:
                        sub_combined = (
                            f"{same_dir_mod}.{alias.name}"
                            if same_dir_mod
                            else ".".join(dir_parts + [alias.name])
                        )
                        if sub_combined in module_to_file:
                            target = module_to_file[sub_combined]
                            if target != curr_rel_path:
                                imported_targets.add(target)

            else:
                # Relative import (level >= 1)
                curr_dir = os.path.dirname(curr_rel_path).replace("\\", "/")
                dir_parts = [p for p in curr_dir.split("/") if p]
                pop_count = level - 1
                if pop_count <= len(dir_parts):
                    base_parts = (
                        dir_parts[: len(dir_parts) - pop_count]
                        if pop_count > 0
                        else list(dir_parts)
                    )
                    target_parts = base_parts + (mod.split(".") if mod else [])
                    target_dotted = ".".join(target_parts)

                    if target_dotted in module_to_file:
                        target = module_to_file[target_dotted]
                        if target != curr_rel_path:
                            imported_targets.add(target)

                    for alias in node.names:
                        combined = (
                            f"{target_dotted}.{alias.name}"
                            if target_dotted
                            else alias.name
                        )
                        if combined in module_to_file:
                            target = module_to_file[combined]
                            if target != curr_rel_path:
                                imported_targets.add(target)

    return imported_targets


def rank_python_files(repo_path: str) -> list[tuple[str, int, int]]:
    """Rank Python files in the repository by importance (path, line_count, import_count).

    Skips .git, venv/.venv/env, node_modules, site-packages, migrations, build/dist,
    __pycache__, files > MAX_FILE_LINES, symlinks; tests ranked last;
    score = line_count + 40 * import_count.

    Returns:
        list[tuple[str, int, int]]: Sorted list of (posix_rel_path, line_count, import_count)
    """
    if not repo_path or not os.path.exists(repo_path) or not os.path.isdir(repo_path):
        raise IngestionError(
            f"Repository directory '{repo_path}' does not exist or is not a directory.",
            detail=f"repo_path='{repo_path}'",
        )

    file_contents: dict[str, str] = {}
    file_lines: dict[str, int] = {}
    file_ast: dict[str, Optional[ast.AST]] = {}

    for root, dirs, files in os.walk(repo_path, followlinks=False):
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

            rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")
            parts = rel_path.split("/")
            if any(p in SKIP_DIR_NAMES for p in parts[:-1]):
                continue

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(full_path, "r", encoding="latin-1") as f:
                        content = f.read()
                except Exception:
                    continue
            except Exception:
                continue

            line_count = len(content.splitlines())
            if line_count > MAX_FILE_LINES:
                continue

            file_contents[rel_path] = content
            file_lines[rel_path] = line_count

            try:
                tree = ast.parse(content, filename=rel_path)
            except (SyntaxError, ValueError, RecursionError, MemoryError):
                tree = None
            file_ast[rel_path] = tree

            if len(file_contents) >= MAX_REPO_PY_FILES:
                break
        if len(file_contents) >= MAX_REPO_PY_FILES:
            break

    module_to_file: dict[str, str] = {}
    for rel_path in file_contents:
        if rel_path.endswith("/__init__.py"):
            pkg_path = rel_path[: -len("/__init__.py")]
            dotted = pkg_path.replace("/", ".")
            module_to_file[dotted] = rel_path
            if pkg_path.startswith("src/"):
                module_to_file[pkg_path[4:].replace("/", ".")] = rel_path
        elif rel_path == "__init__.py":
            pass
        else:
            stem = rel_path[:-3]
            dotted = stem.replace("/", ".")
            module_to_file[dotted] = rel_path
            if stem.startswith("src/"):
                module_to_file[stem[4:].replace("/", ".")] = rel_path

    import_counts: dict[str, int] = {p: 0 for p in file_contents}
    for rel_path, tree in file_ast.items():
        if tree is None:
            continue
        imported_by_this_file = _extract_imported_modules(
            rel_path, tree, module_to_file
        )
        for target in imported_by_this_file:
            if target in import_counts:
                import_counts[target] += 1

    entries: list[tuple[str, int, int]] = []
    for rel_path in file_contents:
        l_cnt = file_lines[rel_path]
        i_cnt = import_counts[rel_path]
        entries.append((rel_path, l_cnt, i_cnt))

    def _ranking_key(item: tuple[str, int, int]):
        r_path, l_cnt, i_cnt = item
        score = l_cnt + 40 * i_cnt
        is_test = _is_test_file(r_path)
        return (1 if is_test else 0, -score, r_path)

    entries.sort(key=_ranking_key)
    return entries


def _extract_call_name(node: ast.AST) -> Optional[str]:
    """Extract string identifier from a call function AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        val = _extract_call_name(node.value)
        if val:
            return f"{val}.{node.attr}"
        return node.attr
    return None


def _collect_calls(
    node: ast.AST, calls: list[str], seen: set[str], max_calls: int = 30
) -> None:
    if len(calls) >= max_calls:
        return
    # Skip descending into nested function or class definitions so their calls aren't attributed here
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return
    if isinstance(node, ast.Call):
        name = _extract_call_name(node.func)
        if name and name not in seen:
            seen.add(name)
            calls.append(name)
            if len(calls) >= max_calls:
                return
    for child in ast.iter_child_nodes(node):
        _collect_calls(child, calls, seen, max_calls)
        if len(calls) >= max_calls:
            return


def _get_function_calls(func_node: ast.AST) -> list[str]:
    calls: list[str] = []
    seen: set[str] = set()
    for child in ast.iter_child_nodes(func_node):
        _collect_calls(child, calls, seen, 30)
        if len(calls) >= 30:
            break
    return calls


def _extract_constants(tree: ast.AST) -> list[ConstantInfo]:
    """Extract module-level UPPER_CASE constants with <= 80 char value representations."""
    constants: list[ConstantInfo] = []
    seen_names: set[str] = set()

    if not isinstance(tree, ast.Module):
        return constants

    for node in tree.body:
        target_names: list[tuple[str, int]] = []
        val_node: Optional[ast.AST] = None

        if isinstance(node, ast.Assign):
            val_node = node.value
            for target in node.targets:
                if isinstance(target, ast.Name):
                    target_names.append((target.id, node.lineno))
                elif isinstance(target, (ast.Tuple, ast.List)):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            target_names.append((elt.id, node.lineno))
        elif isinstance(node, ast.AnnAssign):
            val_node = node.value
            if isinstance(node.target, ast.Name):
                target_names.append((node.target.id, node.lineno))

        for name, lineno in target_names:
            if name.isupper() and not (name.startswith("__") and name.endswith("__")):
                if name not in seen_names:
                    seen_names.add(name)
                    val_repr = ""
                    if val_node is not None:
                        try:
                            val_repr = ast.unparse(val_node)
                        except Exception:
                            val_repr = ""
                    if len(val_repr) > 80:
                        val_repr = val_repr[:80]
                    constants.append(
                        ConstantInfo(
                            name=name,
                            value_repr=val_repr,
                            line=lineno,
                        )
                    )
    return constants


def _extract_imports(tree: ast.AST) -> list[str]:
    """Extract imported module names in order of appearance."""
    imports: list[str] = []
    seen: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in seen:
                    seen.add(alias.name)
                    imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod_prefix = "." * (node.level or 0)
            full_mod = f"{mod_prefix}{node.module}" if node.module else mod_prefix
            if full_mod and full_mod not in seen:
                seen.add(full_mod)
                imports.append(full_mod)
    return imports


class _ASTFileParser(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes: list[str] = []
        self.functions: list[FunctionInfo] = []
        self._scope: list[tuple[str, str]] = []  # ("class" | "function", name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_qualname = ".".join(
            [s[1] for s in self._scope if s[0] == "class"] + [node.name]
        )
        if class_qualname not in self.classes:
            self.classes.append(class_qualname)

        self._scope.append(("class", node.name))
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node, is_async=True)

    def _handle_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
    ) -> None:
        qualname = ".".join([s[1] for s in self._scope] + [node.name])

        is_method = bool(self._scope and self._scope[-1][0] == "class")
        if is_method:
            kind = "method"
        elif is_async:
            kind = "async_function"
        else:
            kind = "function"

        args: list[str] = []
        if hasattr(node.args, "posonlyargs"):
            for a in node.args.posonlyargs:
                args.append(a.arg)
        for a in node.args.args:
            args.append(a.arg)
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        for a in node.args.kwonlyargs:
            args.append(a.arg)
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")

        raw_doc = ast.get_docstring(node)
        if raw_doc is not None:
            doc = raw_doc.strip()
            if len(doc) > 300:
                doc = doc[:300]
        else:
            doc = None

        start_line = node.lineno
        if node.decorator_list:
            dec_lines = [
                d.lineno for d in node.decorator_list if hasattr(d, "lineno")
            ]
            if dec_lines:
                start_line = min([start_line] + dec_lines)
        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno

        calls = _get_function_calls(node)

        self.functions.append(
            FunctionInfo(
                name=node.name,
                qualname=qualname,
                kind=kind,
                args=args,
                docstring=doc,
                line_start=start_line,
                line_end=end_line,
                calls=calls,
            )
        )

        self._scope.append(("function", node.name))
        self.generic_visit(node)
        self._scope.pop()


def _parse_python_file(
    rel_path: str, full_path: str, import_count: int
) -> FileIndex:
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(full_path, "r", encoding="latin-1") as f:
                content = f.read()
        except Exception:
            content = ""
    except Exception:
        content = ""

    lines = content.splitlines()
    line_count = len(lines)

    try:
        tree = ast.parse(content, filename=rel_path)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return FileIndex(
            path=rel_path,
            line_count=line_count,
            import_count=import_count,
            imports=[],
            functions=[],
            classes=[],
            constants=[],
            content=content,
        )

    constants = _extract_constants(tree)
    imports = _extract_imports(tree)

    parser = _ASTFileParser()
    try:
        parser.visit(tree)
    except RecursionError:
        parser = _ASTFileParser()

    return FileIndex(
        path=rel_path,
        line_count=line_count,
        import_count=import_count,
        imports=imports,
        functions=parser.functions,
        classes=parser.classes,
        constants=constants,
        content=content,
    )


def index_repo_path(repo_path: str, source_url: str = "local") -> RepoIndex:
    """Index an existing local directory of Python files into a RepoIndex.

    Keeps the top MAX_INDEXED_FILES from rank_python_files, extracts AST details
    (functions, classes, constants, imports), captures all .py files in file_tree,
    and calculates repo_id and commit_sha. Files with syntax errors are kept with
    empty functions.
    """
    if not repo_path or not os.path.exists(repo_path) or not os.path.isdir(repo_path):
        raise IngestionError(
            f"Repository directory '{repo_path}' does not exist or is not a directory.",
            detail=f"repo_path='{repo_path}'",
        )

    # 1. Collect all candidate .py files for file_tree (posix, sorted)
    all_py_files: list[str] = []
    for root, dirs, files in os.walk(repo_path, followlinks=False):
        dirs[:] = [
            d
            for d in dirs
            if d not in SKIP_DIR_NAMES
            and not d.endswith(".egg-info")
            and not d.endswith(".dist-info")
            and not os.path.islink(os.path.join(root, d))
        ]
        for file_name in files:
            if file_name.endswith(".py"):
                full_p = os.path.join(root, file_name)
                if not os.path.islink(full_p):
                    rel_p = os.path.relpath(full_p, repo_path).replace("\\", "/")
                    parts = rel_p.split("/")
                    if not any(p in SKIP_DIR_NAMES for p in parts[:-1]):
                        all_py_files.append(rel_p)

    all_py_files.sort()
    total_py_files = len(all_py_files)

    # 2. Rank python files
    ranked_entries = rank_python_files(repo_path)
    truncated = len(ranked_entries) > MAX_INDEXED_FILES
    selected_entries = ranked_entries[:MAX_INDEXED_FILES]

    # 3. Parse selected files
    files: list[FileIndex] = []
    for rel_path, line_count, import_count in selected_entries:
        full_path = os.path.join(repo_path, rel_path)
        file_index = _parse_python_file(rel_path, full_path, import_count)
        files.append(file_index)

    # 4. Commit SHA via git rev-parse HEAD ("" if not git)
    commit_sha = ""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            commit_sha = proc.stdout.strip()
    except Exception as e:
        log.debug("git rev-parse HEAD failed in %s: %s", repo_path, e)
        commit_sha = ""

    # 5. repo_id = short hash of url + sha
    hash_seed = f"{source_url}:{commit_sha}".encode("utf-8")
    repo_id = hashlib.sha256(hash_seed).hexdigest()[:12]

    # 6. created_at (ISO)
    created_at = datetime.now(timezone.utc).isoformat()

    return RepoIndex(
        repo_id=repo_id,
        source_url=source_url,
        local_path=os.path.abspath(repo_path),
        commit_sha=commit_sha,
        files=files,
        file_tree=all_py_files,
        total_py_files=total_py_files,
        truncated=truncated,
        from_cache=False,
        created_at=created_at,
    )


def clone_and_index_repo(github_url: str, *, use_cache: bool = True) -> RepoIndex:
    """Clone a GitHub repo and return RepoIndex.

    If use_cache is True and github_url matches the demo repository (or 'demo'),
    loads directly from demo cache in < 0.2 s without network calls and sets
    local_path = materialize_demo_repo(). Otherwise validates URL, clones repo,
    and indexes it.
    """
    if use_cache:
        from .demo_loader import (
            is_demo_source,
            load_demo_repo,
            materialize_demo_repo,
        )

        if is_demo_source(github_url):
            repo_index, _, _ = load_demo_repo()
            repo_index.local_path = materialize_demo_repo()
            return repo_index

    validate_github_url(github_url)
    dest_path = clone_repo(github_url)
    repo_index = index_repo_path(dest_path, source_url=github_url)
    if not repo_index.files:
        cleanup_repo(dest_path)
        raise IngestionError(
            "This repository has no Python files. VivaVoce supports Python repositories only.",
            detail=f"No indexable .py files in {github_url}",
        )
    return repo_index

def load_demo_repo_index() -> RepoIndex:
    """Returns the RepoIndex of the bundled demo repo (studysync)."""
    try:
        from .demo_loader import load_demo_repo
    except ImportError:
        from ingestion.demo_loader import load_demo_repo
    return load_demo_repo()[0]

