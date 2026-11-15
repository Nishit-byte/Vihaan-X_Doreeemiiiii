"""Team adapter for VivaVoce M2 ingestion, PDF parsing, and sandbox verification.

Translates M2 internal domain models into team-facing Pydantic schemas (backend.models.schemas).
Does not contain new business logic or network calls of its own.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

try:
    from backend.models import schemas
except ImportError:
    from models import schemas

try:
    from .demo_loader import is_demo_source, load_demo_repo, materialize_demo_repo
    from .git_blame import compute_authorship_stats, extract_author_map
    from .models import IngestionError
    from .paper_explorer import (
        MAX_PDF_BYTES,
        _clean_ws,
        _extract_pdf_with_layout,
        _extract_sections,
        build_paper_breakdown,
        build_scanned_pdf_breakdown,
    )
    from .pdf_parser import load_demo_paper_bytes, parse_research_paper
    from .repo_parser import clone_and_index_repo
except ImportError:
    from ingestion.demo_loader import is_demo_source, load_demo_repo, materialize_demo_repo
    from ingestion.git_blame import compute_authorship_stats, extract_author_map
    from ingestion.models import IngestionError
    from ingestion.paper_explorer import (
        MAX_PDF_BYTES,
        _clean_ws,
        _extract_pdf_with_layout,
        _extract_sections,
        build_paper_breakdown,
        build_scanned_pdf_breakdown,
    )
    from ingestion.pdf_parser import load_demo_paper_bytes, parse_research_paper
    from ingestion.repo_parser import clone_and_index_repo

try:
    from ..sandbox.sandbox_runner import execute_verification
except ImportError:
    from sandbox.sandbox_runner import execute_verification


# Cache of internal M2 RepoIndex objects keyed by github_url / source_url.
# main.py sessions can retrieve these for citation snapping (snap_range)
# and speech-to-text domain term biasing (identifiers).
M2_REPO_INDEXES: Dict[str, Any] = {}


def _m2_repo_to_schema(idx: Any, author_map: Dict[str, Any], stats: list[Any]) -> schemas.RepoIndex:
    """Converts an internal M2 RepoIndex into the team's schemas.RepoIndex."""
    symbols = [
        schemas.ASTFunctionSymbol(
            name=fn.qualname,
            file_path=f.path,
            line_start=fn.line_start,
            line_end=fn.line_end,
            args=fn.args,
            docstring=fn.docstring,
            calls=fn.calls,
            constants=[c.name for c in f.constants],
            # Raw source, as origin/main's repo_parser did: the brain uses it as runnable starter code.
            code_snippet="\n".join(f.content.splitlines()[fn.line_start - 1:fn.line_end]),
        )
        for f in idx.files
        for fn in f.functions
    ]

    raw_name = idx.source_url.rstrip("/").split("/")[-1]
    repo_name = (raw_name[:-4] if raw_name.endswith(".git") else raw_name) or idx.repo_id

    files = [
        schemas.RepoFile(path=f.path, content=f.content, line_count=f.line_count)
        for f in idx.files
    ]

    mapped_author_map = {
        author: [
            schemas.OwnedSymbol(
                file_path=sym.file_path,
                line_start=sym.line_start,
                line_end=sym.line_end,
                symbol_name=sym.symbol,
                commit_count=1,
            )
            for sym in syms
        ]
        for author, syms in author_map.items()
    }

    return schemas.RepoIndex(
        repo_name=repo_name,
        github_url=idx.source_url,
        local_path=idx.local_path or None,
        files=files,
        symbols=symbols,
        authors=[s.author for s in stats],
        author_map=mapped_author_map,
        summary=f"{idx.total_py_files} Python files ({len(idx.files)} indexed), commit {idx.commit_sha[:7]}",
    )


def ingest_repo(github_url: str, use_demo_cache: bool = False) -> schemas.RepoIndex:
    """Synchronously ingest a repository and map to schemas.RepoIndex."""
    if use_demo_cache or is_demo_source(github_url):
        idx, author_map, stats = load_demo_repo()
        idx.local_path = materialize_demo_repo()
    else:
        idx = clone_and_index_repo(github_url, use_cache=False)
        paths = [f.path for f in idx.files]
        author_map = extract_author_map(idx.local_path, paths, index=idx)
        stats = compute_authorship_stats(idx.local_path, paths)

    M2_REPO_INDEXES[idx.source_url] = idx
    if idx.local_path:
        M2_REPO_INDEXES[idx.local_path] = idx
    return _m2_repo_to_schema(idx, author_map, stats)


async def ingest_repo_async(github_url: str, use_demo_cache: bool = False) -> schemas.RepoIndex:
    """Asynchronous wrapper for ingest_repo via asyncio.to_thread."""
    return await asyncio.to_thread(ingest_repo, github_url, use_demo_cache)


def ingest_pdf(pdf_bytes: Optional[bytes] = None) -> schemas.PaperIndex:
    """Synchronously parse a PDF and map to schemas.PaperIndex (None means demo)."""
    effective_bytes = pdf_bytes if (pdf_bytes and len(pdf_bytes) > 0) else load_demo_paper_bytes()
    if not effective_bytes:
        raise IngestionError("The uploaded PDF is empty.")
    if len(effective_bytes) > MAX_PDF_BYTES:
        raise IngestionError(f"PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB ingestion limit.")

    # Scanned / Layout check using paper_explorer before calling M2's parse_research_paper
    try:
        page_texts, layout_meta = _extract_pdf_with_layout(effective_bytes)
    except ValueError as exc:
        # Keep paper_explorer's own message (unreadable PDF, 250-page limit, ...)
        raise IngestionError(str(exc)) from exc
    except Exception as exc:
        raise IngestionError("Could not read this file as a valid PDF.", detail=str(exc))

    if not page_texts:
        raise IngestionError("No pages could be read from this PDF.")

    whole_text = _clean_ws(" ".join(page_texts))
    if not whole_text or len(whole_text) < 40:
        # Scanned / image-only PDF: return the old scanned-PDF breakdown result (HTTP 200, same as origin/main)
        scanned_bd = build_scanned_pdf_breakdown("Scanned Research PDF", page_count=len(page_texts))
        scanned_node = schemas.PaperNode(
            node_id="N1",
            label="Scanned PDF (OCR Required)",
            summary=scanned_bd.what_this_paper_does,
            section="Extraction Notice",
            page=1,
            excerpt=scanned_bd.what_this_paper_does,
        )
        return schemas.PaperIndex(
            title=scanned_bd.title,
            mermaid_graph="",
            nodes=[scanned_node],
            node_excerpts={"N1": scanned_node.excerpt},
            full_text_summary=scanned_bd.what_this_paper_does,
            breakdown=scanned_bd,
        )

    p = parse_research_paper(effective_bytes)
    nodes = [
        schemas.PaperNode(
            node_id=n.id,
            label=n.label,
            section=n.section or None,
            page=max(1, n.page),
            excerpt=n.excerpt,
        )
        for n in p.nodes
    ]
    # Nishit's Research Paper Explorer breakdown, built from the same nodes as the M2 diagram
    # (same call as origin/main's pdf_parser.parse_research_paper).
    sections = _extract_sections(page_texts, layout_meta=layout_meta)
    breakdown = build_paper_breakdown(
        page_texts=page_texts,
        sections=sections,
        paper_nodes=nodes,
        reconstructed_from_headings=True,
        layout_meta=layout_meta,
        diagram_status="ok",
        diagram_provenance="Reconstructed from the paper",
    )
    return schemas.PaperIndex(
        title=breakdown.title or p.title,
        mermaid_graph=p.mermaid,
        nodes=nodes,
        node_excerpts=dict(p.excerpts),
        full_text_summary=p.full_text[:2000],
        breakdown=breakdown,
    )


async def ingest_pdf_async(pdf_bytes: Optional[bytes] = None) -> schemas.PaperIndex:
    """Asynchronous wrapper for ingest_pdf via asyncio.to_thread."""
    return await asyncio.to_thread(ingest_pdf, pdf_bytes)


def run_challenge(
    file_path: str,
    student_code: str,
    test_code: str,
    repo_root: Optional[str] = None,
) -> schemas.RunCodeResponse:
    """Synchronously verify candidate code fix in sandbox with timeout."""
    # Team challenges (brain/state_machine.py) import the student's code as `student_solution`;
    # M2 writes it to file_path, so alias that module under the team's name.
    module = file_path[:-3].replace("\\", "/").replace("/", ".") if file_path.endswith(".py") else ""
    if module and module != "student_solution" and "student_solution" in test_code:
        test_code = (
            "import importlib as _il, sys as _sys\n"
            f"_sys.modules.setdefault('student_solution', _il.import_module({module!r}))\n"
        ) + test_code

    res = execute_verification(
        file_path=file_path,
        student_code=student_code,
        test_code=test_code,
        repo_root=repo_root,
    )

    if res.timed_out:
        verdict = "Time Limit Exceeded"
    elif res.passed:
        verdict = "Accepted"
    else:
        verdict = "Wrong Answer"

    stderr = res.stderr if not res.error else f"{res.stderr}\n{res.error}".strip()
    total_cases = res.tests_passed + res.tests_failed

    return schemas.RunCodeResponse(
        passed=res.passed,
        verdict=verdict,
        stdout=res.stdout,
        stderr=stderr,
        runtime_ms=res.runtime_ms,
        test_results=[],
        total_cases=total_cases,
        passed_cases=res.tests_passed,
    )


async def run_challenge_async(
    file_path: str,
    student_code: str,
    test_code: str,
    repo_root: Optional[str] = None,
) -> schemas.RunCodeResponse:
    """Asynchronous wrapper for run_challenge via asyncio.to_thread."""
    return await asyncio.to_thread(
        run_challenge, file_path, student_code, test_code, repo_root
    )
