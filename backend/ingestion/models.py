"""Internal Pydantic models and exceptions for VivaVoce M2 ingestion & sandbox.

These models define the internal contracts used across Lane A (repo intelligence)
and Lane B (execution, papers & replay). M1 maps these to schemas.py.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class IngestionError(Exception):
    """Exception raised for user-facing ingestion or parsing failures."""

    def __init__(self, user_message: str, detail: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail

    def __str__(self) -> str:
        if self.detail:
            return f"{self.user_message} ({self.detail})"
        return self.user_message


class FunctionInfo(BaseModel):
    name: str
    qualname: str
    kind: Literal["function", "async_function", "method"]
    args: list[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    line_start: int
    line_end: int
    calls: list[str] = Field(default_factory=list)


class ConstantInfo(BaseModel):
    name: str
    value_repr: str  # <= 80 chars
    line: int


class FileIndex(BaseModel):
    path: str  # posix, relative to repo root
    line_count: int
    import_count: int = 0  # how many indexed files import it
    imports: list[str] = Field(default_factory=list)
    functions: list[FunctionInfo] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    constants: list[ConstantInfo] = Field(default_factory=list)
    content: str


class RepoIndex(BaseModel):
    repo_id: str
    source_url: str
    local_path: str = ""
    commit_sha: str = ""
    files: list[FileIndex] = Field(default_factory=list)
    file_tree: list[str] = Field(default_factory=list)  # ALL .py paths in repo
    total_py_files: int = 0
    truncated: bool = False
    from_cache: bool = False
    created_at: str = ""  # ISO 8601 string

    def get_file(self, path: str) -> Optional[FileIndex]:
        """Retrieve FileIndex by relative posix path."""
        if not path:
            return None
        norm = path.replace("\\", "/").strip()
        if norm.startswith("./"):
            norm = norm[2:]
        for f in self.files:
            if f.path == norm or f.path == path:
                return f
        return None

    def identifiers(self, limit: int = 60) -> list[str]:
        """Return prioritized identifiers (functions, classes, constants, module names) for M3 STT prompt."""
        result: list[str] = []
        seen: set[str] = set()

        def _add(ident: str) -> bool:
            if ident and ident not in seen:
                seen.add(ident)
                result.append(ident)
            return len(result) >= limit

        # Process files in ranked order (most important files first)
        for f in self.files:
            # 1. Functions from this file
            for fn in f.functions:
                if _add(fn.name):
                    return result

            # 2. Classes from this file
            for cls_name in f.classes:
                simple_name = cls_name.split(".")[-1]
                if _add(simple_name):
                    return result
                if cls_name != simple_name:
                    if _add(cls_name):
                        return result

            # 3. Constants from this file
            for c in f.constants:
                if _add(c.name):
                    return result

            # 4. Module name for this file
            stem = f.path.split("/")[-1]
            if stem.endswith(".py"):
                stem = stem[:-3]
            if stem and stem != "__init__":
                if _add(stem):
                    return result

        return result

    def numbered_source(
        self, path: str, start: Optional[int] = None, end: Optional[int] = None
    ) -> str:
        """Return lines formatted as '  12 | code' for M1 prompts."""
        f = self.get_file(path)
        if f is None or not f.content:
            return ""

        lines = f.content.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return ""

        s = 1 if start is None or start < 1 else min(start, total_lines)
        e = total_lines if end is None or end > total_lines else max(1, end)
        if s > e:
            s, e = e, s

        width = max(4, len(str(e)))
        output_lines = [
            f"{i:>{width}} | {lines[i - 1]}" for i in range(s, e + 1)
        ]
        return "\n".join(output_lines)

    def find_function(self, path: str, line: int) -> Optional[FunctionInfo]:
        """Find the enclosing or closest function for a line in a file."""
        f = self.get_file(path)
        if f is None or not f.functions:
            return None

        enclosing = [
            fn for fn in f.functions if fn.line_start <= line <= fn.line_end
        ]
        if enclosing:
            return min(enclosing, key=lambda fn: fn.line_end - fn.line_start)

        return None

    def snap_range(self, path: str, start: int, end: int) -> tuple[str, int, int]:
        """Snap a code citation range to valid function boundaries (M1 citation guard)."""
        f = self.get_file(path)
        if f is None:
            # Unknown path -> highest-ranked file's first function
            if self.files:
                for candidate in self.files:
                    if candidate.functions:
                        first_fn = candidate.functions[0]
                        return (candidate.path, first_fn.line_start, first_fn.line_end)
                first_file = self.files[0]
                return (first_file.path, 1, max(1, first_file.line_count))
            s = max(1, start)
            e = max(s, end)
            return (path, s, e)

        target_path = f.path
        total_lines = max(1, f.line_count)

        if not f.functions:
            return (target_path, 1, total_lines)

        req_start, req_end = (start, end) if start <= end else (end, start)
        req_start = max(1, min(req_start, total_lines))
        req_end = max(1, min(req_end, total_lines))
        if req_start > req_end:
            req_start, req_end = req_end, req_start

        # Rule 1: exact containment in a function -> unchanged
        for fn in f.functions:
            if fn.line_start <= req_start and req_end <= fn.line_end:
                return (target_path, req_start, req_end)

        # Rule 2: partly outside a function -> clamp to that function
        overlapping: list[tuple[int, FunctionInfo]] = []
        for fn in f.functions:
            overlap = min(req_end, fn.line_end) - max(req_start, fn.line_start) + 1
            if overlap > 0:
                overlapping.append((overlap, fn))

        if overlapping:
            overlapping.sort(key=lambda item: item[0], reverse=True)
            best_fn = overlapping[0][1]
            clamped_start = max(req_start, best_fn.line_start)
            clamped_end = min(req_end, best_fn.line_end)
            return (target_path, clamped_start, clamped_end)

        # Rule 3: outside any function -> nearest function by distance
        def _dist(fn: FunctionInfo) -> int:
            if req_end < fn.line_start:
                return fn.line_start - req_end
            if req_start > fn.line_end:
                return req_start - fn.line_end
            return 0

        nearest_fn = min(f.functions, key=_dist)
        return (target_path, nearest_fn.line_start, nearest_fn.line_end)


class OwnedSymbol(BaseModel):
    file_path: str
    symbol: Optional[str] = None
    line_start: int
    line_end: int
    lines_owned: int
    share: float  # 0..1


class AuthorStat(BaseModel):
    author: str
    email: str
    lines: int
    share_of_lines: float  # 0..1


class PaperSection(BaseModel):
    title: str
    page_start: int
    page_end: int
    text: str


class ConceptNode(BaseModel):
    id: str  # 'N1'..'N8'
    label: str
    excerpt: str
    section: str
    page: int
    excerpt_verified: bool = False


class ConceptEdge(BaseModel):
    source: str
    target: str
    label: Optional[str] = None


class PaperIndex(BaseModel):
    paper_id: str  # sha256 of bytes, first 16 hex characters
    title: str
    page_count: int
    sections: list[PaperSection] = Field(default_factory=list)
    full_text: str = ""
    nodes: list[ConceptNode] = Field(default_factory=list)
    edges: list[ConceptEdge] = Field(default_factory=list)
    mermaid: str = ""
    excerpts: dict[str, str] = Field(default_factory=dict)
    source: Literal["gemini", "heuristic", "cache"] = "heuristic"


class SandboxResult(BaseModel):
    passed: bool
    stdout: str = ""
    stderr: str = ""
    runtime_ms: int = 0
    timed_out: bool = False
    tests_passed: int = 0
    tests_failed: int = 0
    error: Optional[str] = None
