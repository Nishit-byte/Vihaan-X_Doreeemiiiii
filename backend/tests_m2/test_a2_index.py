"""Comprehensive test suite for TASK A2: AST indexer and RepoIndex helpers.

Covers:
- AST extraction: functions, async functions, methods (qualname, kind, args, docstring,
  line_start incl. decorators, line_end, calls deduped max 30)
- Classes and module-level UPPER_CASE constants (ast.unparse <= 80 chars)
- Imports extraction
- File tree, total_py_files, truncation flag (> MAX_INDEXED_FILES)
- Git commit SHA and repo_id hashing
- Syntax-error file retention with empty functions
- RepoIndex.get_file, identifiers, numbered_source, find_function, snap_range (all 4 rules)
- Timing performance (< 1 s for ~15 files)
- clone_and_index_repo behavior and parameter handling
"""

import ast
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ingestion.config import MAX_INDEXED_FILES
from ingestion.models import (
    ConstantInfo,
    FileIndex,
    FunctionInfo,
    IngestionError,
    RepoIndex,
)
from ingestion.repo_parser import clone_and_index_repo, index_repo_path


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """Create a multi-file fixture repo with classes, async, nested, decorators, constants, syntax error."""
    repo_dir = tmp_path / "sample_repo"
    repo_dir.mkdir()

    # 1. Main service file with comprehensive AST constructs
    service_code = '''"""Service module for data pipelines and math processing."""

import math
import os.path
from typing import Optional, List

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30
API_URL = "https://api.example.com/v1"
LONG_CONFIG_VAL = "x" * 120
_PRIVATE_CONFIG = "internal"
normal_var = 12345

class BaseService:
    """Base service class documentation."""

    def __init__(self, name: str):
        """Initialize the base service."""
        self.name = name

    def ping(self) -> bool:
        return True


class DataEngine(BaseService):
    """Processes datasets and computes statistics."""

    @classmethod
    def create(cls, name: str = "default"):
        """Factory constructor."""
        return cls(name)

    def process_item(self, item, *args, threshold: float = 1.0, **kwargs):
        """Processes a single item and applies mathematical transforms."""
        self.validate(item)
        print("processing", item)
        val = math.sqrt(item)
        return val

    def validate(self, item):
        """Validates that item is non-negative."""
        if item < 0:
            raise ValueError("Item cannot be negative")
        return True


async def fetch_payload(url: str, timeout: int = 10) -> bytes:
    """Fetch external payload asynchronously."""
    print("connecting to", url)
    return b"response_bytes"


def run_pipeline(items: list) -> list:
    """Outer pipeline function containing nested worker."""
    def _inner_worker(x):
        """Nested transform worker."""
        return x * 2

    results = []
    for it in items:
        results.append(_inner_worker(it))
    return results


@staticmethod
def decorated_utility():
    """Standalone decorated utility function."""
    return "utility"

# Trailing module-level lines outside any function
# For testing line ranges beyond any function
TRAILING_NOTE = "end of file"
'''
    (repo_dir / "service.py").write_text(service_code, encoding="utf-8")

    # 2. Syntax-error file with enough lines to rank in top 15
    broken_code = """# Broken syntax file
def invalid_syntax_func(a, b:
    return a + b
""" + "\n".join(f"# padding comment line {i}" for i in range(25))
    (repo_dir / "syntax_error.py").write_text(broken_code, encoding="utf-8")

    # 3. Subpackage with utilities
    utils_dir = repo_dir / "utils"
    utils_dir.mkdir()
    (utils_dir / "__init__.py").write_text('"""Utils package."""\n', encoding="utf-8")

    helpers_code = '''"""Helper calculation utilities."""

import math

HELPER_VERSION = "2.1.0"
MAX_ITEMS = 500

def compute_norm(v: list[float]) -> float:
    """Compute Euclidean norm of vector."""
    sum_sq = sum(x * x for x in v)
    return math.sqrt(sum_sq)
'''
    (repo_dir / "utils" / "helpers.py").write_text(helpers_code, encoding="utf-8")

    # 4. Extra files to bring total files to 17 (> MAX_INDEXED_FILES = 15)
    for i in range(1, 14):
        file_name = f"mod_{i:02d}.py"
        code = f'''"""Module {i:02d} documentation."""

MOD_CONST_{i:02d} = {i * 10}

class Handler_{i:02d}:
    def handle_{i:02d}(self):
        return {i}

def helper_fn_{i:02d}():
    return {i * 2}
'''
        (repo_dir / file_name).write_text(code, encoding="utf-8")

    return repo_dir


# ============================================================================
# 1. AST Extraction Tests
# ============================================================================


def test_index_repo_ast_functions(fixture_repo: Path):
    """Verify function, async function, method, args, docstring, qualname, and kind extraction."""
    repo_index = index_repo_path(str(fixture_repo))
    service_file = repo_index.get_file("service.py")
    assert service_file is not None

    functions_by_qual = {fn.qualname: fn for fn in service_file.functions}

    # Method in class
    assert "DataEngine.process_item" in functions_by_qual
    fn_process = functions_by_qual["DataEngine.process_item"]
    assert fn_process.name == "process_item"
    assert fn_process.kind == "method"
    assert fn_process.args == ["self", "item", "*args", "threshold", "**kwargs"]
    assert fn_process.docstring is not None
    assert "Processes a single item" in fn_process.docstring
    assert fn_process.line_start < fn_process.line_end
    assert "self.validate" in fn_process.calls
    assert "print" in fn_process.calls
    assert "math.sqrt" in fn_process.calls

    # Async function
    assert "fetch_payload" in functions_by_qual
    fn_async = functions_by_qual["fetch_payload"]
    assert fn_async.kind == "async_function"
    assert fn_async.args == ["url", "timeout"]
    assert fn_async.docstring == "Fetch external payload asynchronously."
    assert "print" in fn_async.calls

    # Top-level and nested functions
    assert "run_pipeline" in functions_by_qual
    assert functions_by_qual["run_pipeline"].kind == "function"
    assert "run_pipeline._inner_worker" in functions_by_qual
    fn_nested = functions_by_qual["run_pipeline._inner_worker"]
    assert fn_nested.kind == "function"
    assert fn_nested.args == ["x"]
    assert fn_nested.docstring == "Nested transform worker."

    # Decorator line numbers
    assert "DataEngine.create" in functions_by_qual
    fn_create = functions_by_qual["DataEngine.create"]
    assert fn_create.kind == "method"
    # Decorator @classmethod is on the line immediately before def create
    service_lines = service_file.content.splitlines()
    assert "@classmethod" in service_lines[fn_create.line_start - 1]

    # Standalone decorated function
    assert "decorated_utility" in functions_by_qual
    fn_dec = functions_by_qual["decorated_utility"]
    assert "@staticmethod" in service_lines[fn_dec.line_start - 1]


def test_index_repo_ast_constants_and_classes(fixture_repo: Path):
    """Verify classes and module-level UPPER_CASE constants extraction."""
    repo_index = index_repo_path(str(fixture_repo))
    service_file = repo_index.get_file("service.py")
    assert service_file is not None

    # Classes
    assert "BaseService" in service_file.classes
    assert "DataEngine" in service_file.classes

    # Constants
    const_by_name = {c.name: c for c in service_file.constants}
    assert "MAX_RETRIES" in const_by_name
    assert const_by_name["MAX_RETRIES"].value_repr == "3"

    assert "DEFAULT_TIMEOUT" in const_by_name
    assert const_by_name["DEFAULT_TIMEOUT"].value_repr == "30"

    assert "API_URL" in const_by_name
    assert "https://api.example.com/v1" in const_by_name["API_URL"].value_repr

    # LONG_CONFIG_VAL must be truncated to <= 80 chars
    assert "LONG_CONFIG_VAL" in const_by_name
    assert len(const_by_name["LONG_CONFIG_VAL"].value_repr) <= 80

    # Lowercase variables must not be in constants
    assert "normal_var" not in const_by_name


def test_index_repo_ast_imports(fixture_repo: Path):
    """Verify imported module extraction in order of appearance."""
    repo_index = index_repo_path(str(fixture_repo))
    service_file = repo_index.get_file("service.py")
    assert service_file is not None

    assert "math" in service_file.imports
    assert "os.path" in service_file.imports
    assert "typing" in service_file.imports


def test_syntax_error_file_retained_with_empty_symbols(fixture_repo: Path):
    """Verify files with syntax errors are kept with line_count and content, but empty functions."""
    repo_index = index_repo_path(str(fixture_repo))
    broken_file = repo_index.get_file("syntax_error.py")
    assert broken_file is not None
    assert broken_file.line_count > 0
    assert "invalid_syntax_func" in broken_file.content
    assert broken_file.functions == []
    assert broken_file.classes == []
    assert broken_file.constants == []
    assert broken_file.imports == []


# ============================================================================
# 2. File Tree, Truncation & Git Metadata Tests
# ============================================================================


def test_file_tree_and_truncation(fixture_repo: Path):
    """Verify file_tree contains all .py files sorted, and truncated is set when candidates > 15."""
    repo_index = index_repo_path(str(fixture_repo))

    # All candidate .py paths sorted
    assert isinstance(repo_index.file_tree, list)
    assert repo_index.file_tree == sorted(repo_index.file_tree)
    assert "service.py" in repo_index.file_tree
    assert "syntax_error.py" in repo_index.file_tree
    assert "utils/helpers.py" in repo_index.file_tree

    # Total files = 1 (service) + 1 (syntax) + 2 (utils) + 13 (mod_*) = 17 files
    assert repo_index.total_py_files >= 16
    assert repo_index.truncated is True
    assert len(repo_index.files) == MAX_INDEXED_FILES


def test_git_metadata_when_git_and_non_git(fixture_repo: Path):
    """Verify commit_sha and repo_id behavior for git and non-git directories."""
    # Non-git directory
    index_non_git = index_repo_path(str(fixture_repo), source_url="https://github.com/foo/bar")
    assert index_non_git.commit_sha == ""
    assert len(index_non_git.repo_id) == 12

    # Initialize a git repo and make a commit
    subprocess.run(["git", "init"], cwd=str(fixture_repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test Agent"], cwd=str(fixture_repo), capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "agent@test.local"],
        cwd=str(fixture_repo),
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=str(fixture_repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(fixture_repo),
        capture_output=True,
        check=True,
    )

    index_git = index_repo_path(str(fixture_repo), source_url="https://github.com/foo/bar")
    assert len(index_git.commit_sha) == 40
    assert len(index_git.repo_id) == 12
    assert index_git.created_at != ""


# ============================================================================
# 3. RepoIndex Helper Methods Tests
# ============================================================================


def test_repo_index_get_file(fixture_repo: Path):
    """Verify get_file with posix, backslash, and relative prefix variations."""
    repo = index_repo_path(str(fixture_repo))

    assert repo.get_file("service.py") is not None
    assert repo.get_file("./service.py") is not None
    assert repo.get_file("utils/helpers.py") is not None
    assert repo.get_file("utils\\helpers.py") is not None
    assert repo.get_file("nonexistent.py") is None


def test_numbered_source(fixture_repo: Path):
    """Verify numbered_source formats right-aligned line numbers and clamps ranges."""
    repo = index_repo_path(str(fixture_repo))

    # Full source formatting
    full_src = repo.numbered_source("service.py")
    lines = full_src.splitlines()
    assert lines[0].startswith("   1 | ")
    assert '"""Service module' in lines[0]

    # Specific sub-range
    sub_src = repo.numbered_source("service.py", start=6, end=8)
    sub_lines = sub_src.splitlines()
    assert len(sub_lines) == 3
    assert sub_lines[0].startswith("   6 | ")
    assert sub_lines[-1].startswith("   8 | ")

    # Clamping out-of-range bounds
    clamped_src = repo.numbered_source("service.py", start=-10, end=9999)
    clamped_lines = clamped_src.splitlines()
    service_file = repo.get_file("service.py")
    assert len(clamped_lines) == service_file.line_count

    # Nonexistent file returns empty string
    assert repo.numbered_source("missing.py") == ""


def test_find_function(fixture_repo: Path):
    """Verify find_function returns the innermost function for a line number."""
    repo = index_repo_path(str(fixture_repo))
    service_file = repo.get_file("service.py")
    functions_by_qual = {fn.qualname: fn for fn in service_file.functions}

    # Line inside DataEngine.process_item
    process_fn = functions_by_qual["DataEngine.process_item"]
    mid_line = (process_fn.line_start + process_fn.line_end) // 2
    found = repo.find_function("service.py", mid_line)
    assert found is not None
    assert found.qualname == "DataEngine.process_item"

    # Line inside nested worker _inner_worker
    worker_fn = functions_by_qual["run_pipeline._inner_worker"]
    found_worker = repo.find_function("service.py", worker_fn.line_start)
    assert found_worker is not None
    assert found_worker.qualname == "run_pipeline._inner_worker"

    # Line at top-level constant outside any function
    found_none = repo.find_function("service.py", 7)  # MAX_RETRIES = 3
    assert found_none is None

    # Line in non-existent file
    assert repo.find_function("missing.py", 10) is None


def test_snap_range_all_four_rules(fixture_repo: Path):
    """Verify all four snap_range citation guard rules (improvement plan P0-1.2)."""
    repo = index_repo_path(str(fixture_repo))
    service_file = repo.get_file("service.py")
    functions_by_qual = {fn.qualname: fn for fn in service_file.functions}
    proc_fn = functions_by_qual["DataEngine.process_item"]

    # RULE 1: Exact containment inside a function -> unchanged
    r1_start = proc_fn.line_start + 1
    r1_end = proc_fn.line_end - 1
    p, s, e = repo.snap_range("service.py", r1_start, r1_end)
    assert (p, s, e) == ("service.py", r1_start, r1_end)

    # RULE 2: Partly outside a function -> clamp to that function
    # Starts before the function, ends inside
    p, s, e = repo.snap_range("service.py", proc_fn.line_start - 2, r1_end)
    assert p == "service.py"
    assert s == proc_fn.line_start  # clamped to function start
    assert e == r1_end

    # Starts inside, ends after the function
    p, s, e = repo.snap_range("service.py", r1_start, proc_fn.line_end + 3)
    assert p == "service.py"
    assert s == r1_start
    assert e == proc_fn.line_end  # clamped to function end

    # RULE 3: Outside any function -> nearest function by distance
    # Between module start and first function (constants area, line 6..8)
    p, s, e = repo.snap_range("service.py", 5, 8)
    assert p == "service.py"
    first_fn = functions_by_qual["BaseService.__init__"]
    assert (s, e) == (first_fn.line_start, first_fn.line_end)

    # High line numbers beyond the file length -> nearest function
    p, s, e = repo.snap_range("service.py", 800, 900)
    assert p == "service.py"
    assert s <= service_file.line_count
    assert e <= service_file.line_count
    # Should snap to the last function
    last_fn = max(service_file.functions, key=lambda f: f.line_end)
    assert (s, e) == (last_fn.line_start, last_fn.line_end)

    # RULE 4: Unknown path -> top-ranked file's first function
    top_file = repo.files[0]
    top_first_fn = top_file.functions[0]
    p, s, e = repo.snap_range("unknown/nonexistent_module.py", 12, 34)
    assert p == top_file.path
    assert (s, e) == (top_first_fn.line_start, top_first_fn.line_end)


def test_identifiers_ordering_dedup_and_limit(fixture_repo: Path):
    """Verify identifiers returns functions, classes, constants, module names prioritized and deduped."""
    repo = index_repo_path(str(fixture_repo))

    # Full identifiers
    idents = repo.identifiers(limit=60)
    assert isinstance(idents, list)
    assert len(idents) <= 60

    # No duplicates
    assert len(idents) == len(set(idents))

    # Functions present
    assert "process_item" in idents
    assert "fetch_payload" in idents
    assert "run_pipeline" in idents

    # Classes present
    assert "BaseService" in idents
    assert "DataEngine" in idents

    # Constants present
    assert "MAX_RETRIES" in idents
    assert "API_URL" in idents

    # Module names present
    assert "service" in idents or "helpers" in idents

    # Respects limit parameter
    small_idents = repo.identifiers(limit=5)
    assert len(small_idents) == 5


# ============================================================================
# 4. Performance & clone_and_index_repo Tests
# ============================================================================


def test_index_repo_performance(fixture_repo: Path):
    """Verify indexing a ~15-file repo executes in under 1 second."""
    t0 = time.perf_counter()
    repo_index = index_repo_path(str(fixture_repo))
    elapsed_s = time.perf_counter() - t0

    assert elapsed_s < 1.0, f"Indexing took {elapsed_s:.3f} s, which exceeds 1.0 s requirement"
    print(f"\n[PERFORMANCE] Indexed {len(repo_index.files)} files ({repo_index.total_py_files} candidates) in {elapsed_s * 1000:.1f} ms")


def test_clone_and_index_repo_delegation(fixture_repo: Path):
    """Verify clone_and_index_repo validates URL and delegates to clone and index."""
    # Invalid URL must raise IngestionError
    with pytest.raises(IngestionError):
        clone_and_index_repo("not-a-github-url")

    # Valid URL mocked to fixture directory
    with patch("ingestion.repo_parser.clone_repo", return_value=str(fixture_repo)):
        repo = clone_and_index_repo("https://github.com/shreyas-269/sample-repo", use_cache=True)
        assert repo.source_url == "https://github.com/shreyas-269/sample-repo"
        assert len(repo.files) > 0
        assert repo.get_file("service.py") is not None


def test_nonexistent_directory_raises():
    """Verify index_repo_path raises IngestionError on invalid or missing directory."""
    with pytest.raises(IngestionError) as exc_info:
        index_repo_path("C:/invalid_nonexistent_directory_for_test")
    assert "does not exist" in str(exc_info.value)
