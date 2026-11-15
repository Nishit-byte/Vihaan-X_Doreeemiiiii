"""Tests for M2 team_adapter mapping internal M2 models to team Pydantic schemas.

Checks:
1. Demo repo ingest returns real studysync data (similarity.py, utils/vector_ops.py,
   authors Aman Verma, Priya Nair, Rohan Gupta).
2. Demo PDF ingest returns sample paper's real title, a mermaid_graph starting with 'flowchart TD',
   and Nishit's PaperBreakdown built from the same nodes.
3. Demo challenge: starter code FAILS, reference solution PASSES.
4. Async versions function cleanly.
5. Scanned PDFs get the scanned breakdown; junk bytes raise IngestionError.
6. (J3 fix round 2) non-demo repo path, raw code_snippet, brain-generated L4 challenge,
   and HTTP-level /api/ingest-pdf behaviour.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

# Ensure repo root is on sys.path for backend.* imports
REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pytest
from backend.ingestion import team_adapter as adapter
from backend.ingestion.demo_loader import load_demo_challenge, materialize_demo_repo
from backend.ingestion.repo_parser import index_repo_path
from backend.models import schemas

LINE_NUMBER_PREFIX = re.compile(r"^\s*\d+ \| ", re.MULTILINE)


def _scanned_pdf_bytes() -> bytes:
    """An image-only page (a drawn rectangle, no text layer)."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(pymupdf.Rect(50, 50, 200, 200), color=(1, 0, 0), fill=(0, 1, 0))
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_team_adapter_demo_repo():
    """Verify demo repo ingestion produces schemas.RepoIndex with real studysync data."""
    repo = adapter.ingest_repo("demo", use_demo_cache=True)
    assert isinstance(repo, schemas.RepoIndex)
    assert repo.repo_name == "vivavoce-demo-repo"

    file_paths = [f.path for f in repo.files]
    assert "similarity.py" in file_paths
    assert "utils/vector_ops.py" in file_paths

    # Authors check
    assert "Aman Verma" in repo.authors
    assert "Priya Nair" in repo.authors
    assert "Rohan Gupta" in repo.authors

    # Author map check
    assert "Aman Verma" in repo.author_map
    assert "Priya Nair" in repo.author_map
    assert "Rohan Gupta" in repo.author_map

    # Symbols check
    symbol_names = [s.name for s in repo.symbols]
    assert "cosine_similarity" in symbol_names
    assert "dot_product" in symbol_names
    assert repo.local_path is not None


def test_team_adapter_demo_pdf():
    """Verify demo PDF ingestion produces schemas.PaperIndex with valid Mermaid graph."""
    paper = adapter.ingest_pdf(None)
    assert isinstance(paper, schemas.PaperIndex)
    assert paper.title == "Adaptive Spaced Repetition with Peer Matching"
    assert paper.mermaid_graph.startswith("flowchart TD")
    assert len(paper.nodes) >= 5
    assert len(paper.node_excerpts) >= 5

    # Check node structure
    for node in paper.nodes:
        assert node.node_id.startswith("N")
        assert len(node.label) > 0
        assert len(node.excerpt) > 0


def test_team_adapter_demo_challenge():
    """Verify demo challenge run: starter code fails, reference solution passes."""
    challenge = load_demo_challenge()
    repo_root = materialize_demo_repo()

    # 1. Run starter code (must fail with Wrong Answer / ZeroDivisionError)
    res_starter = adapter.run_challenge(
        file_path=challenge["target_file"],
        student_code=challenge["starter_code"],
        test_code=challenge["test_code"],
        repo_root=repo_root,
    )
    assert isinstance(res_starter, schemas.RunCodeResponse)
    assert res_starter.passed is False
    assert res_starter.verdict in ("Wrong Answer", "Runtime Error")
    assert res_starter.passed_cases < res_starter.total_cases

    # 2. Run reference solution (must pass with Accepted)
    res_ref = adapter.run_challenge(
        file_path=challenge["target_file"],
        student_code=challenge["reference_solution"],
        test_code=challenge["test_code"],
        repo_root=repo_root,
    )
    assert isinstance(res_ref, schemas.RunCodeResponse)
    assert res_ref.passed is True
    assert res_ref.verdict == "Accepted"
    assert res_ref.passed_cases == res_ref.total_cases
    assert res_ref.passed_cases > 0


def test_team_adapter_async():
    """Verify asynchronous adapter wrappers."""
    async def _run_async_checks():
        repo = await adapter.ingest_repo_async("demo", use_demo_cache=True)
        assert repo.repo_name == "vivavoce-demo-repo"

        paper = await adapter.ingest_pdf_async(None)
        assert paper.mermaid_graph.startswith("flowchart TD")

        challenge = load_demo_challenge()
        res = await adapter.run_challenge_async(
            file_path=challenge["target_file"],
            student_code=challenge["reference_solution"],
            test_code=challenge["test_code"],
            repo_root=repo.local_path,
        )
        assert res.passed is True

    asyncio.run(_run_async_checks())


def test_team_adapter_scanned_pdf():
    """Verify scanned/image-only PDF produces PaperIndex with breakdown, matching origin/main."""
    paper = adapter.ingest_pdf(_scanned_pdf_bytes())
    assert isinstance(paper, schemas.PaperIndex)
    assert paper.title == "Scanned Research PDF"
    assert paper.mermaid_graph == ""
    assert len(paper.nodes) == 1
    assert paper.nodes[0].label == "Scanned PDF (OCR Required)"
    assert paper.breakdown is not None
    assert paper.breakdown.title == "Scanned Research PDF"
    assert "scanned" in paper.breakdown.extraction_warning.lower()


def test_team_adapter_junk_pdf_error():
    """Verify non-PDF junk bytes raise IngestionError."""
    with pytest.raises(adapter.IngestionError):
        adapter.ingest_pdf(b"not a valid pdf document at all")


# --- J3 fix round 2 -------------------------------------------------------------------------


def test_fix6a_non_demo_repo_uses_clone(monkeypatch):
    """(a) A non-demo URL goes through clone_and_index_repo and is mapped to the schema."""
    calls = []

    def fake_clone(github_url, use_cache=True):
        calls.append((github_url, use_cache))
        return index_repo_path(materialize_demo_repo(), source_url="https://github.com/example/studysync")

    monkeypatch.setattr(adapter, "clone_and_index_repo", fake_clone)
    repo = adapter.ingest_repo("https://github.com/example/studysync")

    assert calls == [("https://github.com/example/studysync", False)]
    assert repo.repo_name == "studysync"
    assert repo.files and repo.symbols and repo.authors
    assert set(repo.authors) == {"Aman Verma", "Priya Nair", "Rohan Gupta"}


def test_fix6b_code_snippet_is_raw_source():
    """(b) code_snippet is runnable source (the brain uses it as IDE starter code)."""
    repo = adapter.ingest_repo("demo", use_demo_cache=True)
    for sym in repo.symbols:
        assert not LINE_NUMBER_PREFIX.search(sym.code_snippet or ""), sym.name

    cosine = next(s for s in repo.symbols if s.name == "cosine_similarity")
    compile(cosine.code_snippet, "similarity.py", "exec")


def _brain_challenge():
    from backend.brain.state_machine import VivaSession, _build_coding_challenge_for_symbol

    repo = adapter.ingest_repo("demo", use_demo_cache=True)
    sym = next(s for s in repo.symbols if s.name == "cosine_similarity")
    session = VivaSession(session_id="j3-test", mode="repo", title=repo.repo_name, repo_index=repo)
    return repo, sym, _build_coding_challenge_for_symbol(sym, session)


def test_fix6c_brain_challenge_student_solution():
    """(c) The brain's own L4 challenge imports `student_solution`: starter fails, a correct fix passes."""
    repo, sym, challenge = _brain_challenge()
    assert "from student_solution import" in challenge.test_code

    a, b = [x for x in sym.args if x not in ("self", "cls")][:2]
    fix = (
        "import math\n\n"
        f"def cosine_similarity({a}, {b}):\n"
        f"    if not {a} or not {b}:\n"
        "        return 0.0\n"
        f"    na = math.sqrt(sum(x * x for x in {a}))\n"
        f"    nb = math.sqrt(sum(x * x for x in {b}))\n"
        "    if na == 0 or nb == 0:\n"
        "        return 0.0\n"
        f"    return round(sum(x * y for x, y in zip({a}, {b})) / (na * nb), 4)\n"
    )

    starter = adapter.run_challenge(challenge.target_file, challenge.starter_code, challenge.test_code,
                                    repo_root=repo.local_path)
    assert starter.passed is False
    assert starter.total_cases > 0  # real test failures, not a collection error

    for file_path in (challenge.target_file, "main.py"):
        res = adapter.run_challenge(file_path, fix, challenge.test_code, repo_root=repo.local_path)
        assert res.passed is True, (file_path, res.stdout, res.stderr)
        assert res.verdict == "Accepted"


def test_fix6d_demo_pdf_breakdown_matches_diagram():
    """(d) The demo paper carries Nishit's breakdown, built from the same nodes as the diagram."""
    paper = adapter.ingest_pdf(None)
    assert paper.breakdown is not None
    assert paper.breakdown.title
    mermaid_ids = set(re.findall(r"\b(N\d+)\[", paper.mermaid_graph))
    assert {n.node_id for n in paper.nodes} == mermaid_ids


def test_fix6e_http_ingest_pdf():
    """(e) HTTP level: junk -> 400 (detail not repeated); no file / scanned -> 200 with a breakdown."""
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)  # no context manager: skip lifespan warmups

    r = client.post("/api/ingest-pdf", files={"file": ("junk.pdf", b"not a pdf at all", "application/pdf")})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail == "Could not read this file as a valid PDF. Please upload a valid PDF document."

    r = client.post("/api/ingest-pdf")
    assert r.status_code == 200
    assert r.json()["paper_breakdown"] is not None

    r = client.post("/api/ingest-pdf", files={"file": ("scan.pdf", _scanned_pdf_bytes(), "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["paper_breakdown"] is not None
    assert body["title"] == "Scanned Research PDF"
