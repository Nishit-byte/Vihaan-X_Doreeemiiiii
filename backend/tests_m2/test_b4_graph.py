"""Tests for TASK B4: Concept graph generation and Mermaid diagram building."""

import concurrent.futures
from pathlib import Path
import re
import time
from unittest.mock import MagicMock, patch
import pytest

from ingestion.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_S
from ingestion.models import ConceptEdge, ConceptNode, PaperSection
from ingestion.pdf_parser import (
    _LLMConceptEdge,
    _LLMConceptGraphResponse,
    _LLMConceptNode,
    _call_gemini_structured_with_timeout,
    _extract_first_two_sentences,
    _heuristic_concept_graph,
    _prepare_paper_context,
    _sanitize_mermaid_label,
    build_concept_graph,
    build_mermaid,
    extract_sections,
)


# ============================================================================
# 1. Mermaid Generation & Label Sanitization Tests
# ============================================================================


def test_sanitize_mermaid_label_nasty_cases():
    """Verify that nasty labels are completely stripped of syntax-breaking characters."""
    cases = [
        ('Stage "1" [Draft] (v2.0) {alpha} | branch', "Stage '1' Draft v2.0 alpha - branch"),
        ("Line 1\nLine 2\r\nLine 3\tTabbed", "Line 1 Line 2 Line 3 Tabbed"),
        ('Quotes: "double" and \'single\' and "smart"', "Quotes: 'double' and 'single' and 'smart'"),
        ("Brackets: [brackets] (parens) {braces} <angles>", "Brackets: brackets parens braces angles"),
        ("Pipes and semicolons: A | B; C | D;", "Pipes and semicolons: A - B, C - D,"),
        ("A" * 100, ("A" * 40)),
        ("", "Stage"),
        ("   ", "Stage"),
    ]
    for raw, expected_contains in cases:
        sanitized = _sanitize_mermaid_label(raw, max_len=40)
        assert len(sanitized) <= 40
        assert '"' not in sanitized
        assert "[" not in sanitized and "]" not in sanitized
        assert "(" not in sanitized and ")" not in sanitized
        assert "{" not in sanitized and "}" not in sanitized
        assert "<" not in sanitized and ">" not in sanitized
        assert "|" not in sanitized
        assert "\n" not in sanitized and "\r" not in sanitized
        assert "\t" not in sanitized


def test_build_mermaid_nasty_labels_matches_pattern():
    """Verify build_mermaid produces 100% valid syntax matching expected line patterns."""
    nasty_nodes = [
        ConceptNode(
            id="N1",
            label='Init: "Start" [v1] (Draft) {mode}',
            excerpt="First sentence.",
            section="Section 1",
            page=1,
        ),
        ConceptNode(
            id="N2",
            label="Multi\nLine\r\nLabel\tWith\tTabs",
            excerpt="Second sentence.",
            section="Section 2",
            page=1,
        ),
        ConceptNode(
            id="N3",
            label="Pipes | Semicolons; And <Tags>",
            excerpt="Third sentence.",
            section="Section 3",
            page=2,
        ),
        ConceptNode(
            id="N4",
            label="A very long descriptive stage label exceeding forty characters by far",
            excerpt="Fourth sentence.",
            section="Section 4",
            page=2,
        ),
        ConceptNode(
            id="N5",
            label="",
            excerpt="Fifth sentence.",
            section="Section 5",
            page=3,
        ),
    ]
    nasty_edges = [
        ConceptEdge(source="N1", target="N2", label='Edge "1" [pass]'),
        ConceptEdge(source="N2", target="N3", label=None),
        ConceptEdge(source="N3", target="N4", label="A | B"),
        ConceptEdge(source="N4", target="N5", label="Step\nJump"),
    ]

    diagram = build_mermaid(nasty_nodes, nasty_edges)
    lines = [ln.strip() for ln in diagram.splitlines() if ln.strip()]

    # 1. First line must be flowchart TD
    assert lines[0] == "flowchart TD"

    # 2. Last line must be classDef active
    assert lines[-1] == "classDef active stroke-width:4px;"

    # 3. Check every intermediate line
    node_pattern = re.compile(r'^([A-Za-z0-9_]+)\["([^"\]\[\(\)\{\}<>\r\n|]*)"\]$')
    edge_pattern_unlabeled = re.compile(r"^([A-Za-z0-9_]+)\s*-->\s*([A-Za-z0-9_]+)$")
    edge_pattern_labeled = re.compile(
        r'^([A-Za-z0-9_]+)\s*-->\|([^"\]\[\(\)\{\}<>\r\n|]+)\|\s*([A-Za-z0-9_]+)$'
    )

    node_count = 0
    edge_count = 0

    for line in lines[1:-1]:
        if "-->" in line:
            assert edge_pattern_unlabeled.match(line) or edge_pattern_labeled.match(line), (
                f"Invalid edge line: {line}"
            )
            edge_count += 1
        else:
            m = node_pattern.match(line)
            assert m is not None, f"Invalid node line: {line}"
            label_inside = m.group(2)
            assert len(label_inside) <= 40
            node_count += 1

    assert node_count == len(nasty_nodes)
    assert edge_count == len(nasty_edges)


def test_build_mermaid_determinism():
    """Verify that build_mermaid is 100% deterministic."""
    nodes = [
        ConceptNode(id="N1", label="Step 1", excerpt="Ex 1", section="S1", page=1),
        ConceptNode(id="N2", label="Step 2", excerpt="Ex 2", section="S2", page=1),
    ]
    edges = [ConceptEdge(source="N1", target="N2", label="next")]

    d1 = build_mermaid(nodes, edges)
    d2 = build_mermaid(nodes, edges)
    assert d1 == d2


# ============================================================================
# 2. Heuristic Concept Graph Tests
# ============================================================================


def test_heuristic_concept_graph_sample_paper():
    """Verify that heuristic fallback on sample_paper.pdf produces exactly 6 chained nodes."""
    pdf_path = Path(__file__).resolve().parent.parent / "demo_cache" / "sample_paper.pdf"
    assert pdf_path.exists(), "sample_paper.pdf must exist in demo_cache"

    pdf_bytes = pdf_path.read_bytes()
    title, page_count, sections, full_text = extract_sections(pdf_bytes)

    nodes, edges, source = _heuristic_concept_graph(sections, full_text)

    assert source == "heuristic"
    assert len(nodes) == 6, f"Expected 6 method stages, got {len(nodes)}"
    assert [n.id for n in nodes] == ["N1", "N2", "N3", "N4", "N5", "N6"]

    # Verify labels correspond to the 6 method subsections in order
    expected_labels = [
        "Concept Knowledge Graph Construction",
        "Dynamic Memory Decay Modeling",
        "Peer Complementarity Scoring",
        "Synchronous Pairing and Session",
        "Collaborative Question Generation",
        "Dual-Feedback Performance Update",
    ]
    for idx, expected in enumerate(expected_labels):
        assert nodes[idx].label == expected, (
            f"Node {nodes[idx].id} label mismatch: {nodes[idx].label} != {expected}"
        )
        assert len(nodes[idx].label.split()) <= 6
        assert len(nodes[idx].label) <= 40
        assert nodes[idx].excerpt, "Excerpt must not be empty"
        assert nodes[idx].page in (1, 2)
        assert not nodes[idx].excerpt_verified

    # Verify chained edges: N1->N2, N2->N3, N3->N4, N4->N5, N5->N6
    assert len(edges) == 5
    for i in range(5):
        assert edges[i].source == f"N{i + 1}"
        assert edges[i].target == f"N{i + 2}"

    # Verify Mermaid rendering
    mermaid_out = build_mermaid(nodes, edges)
    assert "flowchart TD" in mermaid_out
    assert "N1 --> N2" in mermaid_out
    assert "N5 --> N6" in mermaid_out
    assert "classDef active stroke-width:4px;" in mermaid_out


def test_heuristic_concept_graph_sparse_paper():
    """Verify heuristic handles papers with few or no method headings without crashing."""
    sparse_sections = [
        PaperSection(title="Introduction", page_start=1, page_end=1, text="Introduction text. Second sentence."),
        PaperSection(title="Core Approach", page_start=2, page_end=2, text="We propose a new model. It works well."),
        PaperSection(title="Evaluation", page_start=3, page_end=3, text="Results are good. Accuracy is 95%."),
    ]
    nodes, edges, source = _heuristic_concept_graph(sparse_sections, "full text")
    assert source == "heuristic"
    assert len(nodes) >= 3
    assert [n.id for n in nodes] == [f"N{i+1}" for i in range(len(nodes))]
    assert len(edges) == len(nodes) - 1


# ============================================================================
# 3. Gemini Structured Graph & Fallback Tests (Mocked)
# ============================================================================


def test_build_concept_graph_fallback_when_api_key_missing():
    """When GEMINI_API_KEY is empty, build_concept_graph falls back to heuristic immediately."""
    with patch("ingestion.pdf_parser.GEMINI_API_KEY", ""):
        secs = [
            PaperSection(title="2.1 Step A", page_start=1, page_end=1, text="Sentence one. Sentence two."),
            PaperSection(title="2.2 Step B", page_start=1, page_end=1, text="Sentence three. Sentence four."),
            PaperSection(title="2.3 Step C", page_start=2, page_end=2, text="Sentence five. Sentence six."),
            PaperSection(title="2.4 Step D", page_start=2, page_end=2, text="Sentence seven. Sentence eight."),
            PaperSection(title="2.5 Step E", page_start=2, page_end=2, text="Sentence nine. Sentence ten."),
        ]
        nodes, edges, source = build_concept_graph("full text", secs)
        assert source == "heuristic"
        assert len(nodes) == 5
        assert [n.id for n in nodes] == ["N1", "N2", "N3", "N4", "N5"]


def test_build_concept_graph_fallback_on_api_error():
    """When Gemini API call raises an error, it retries and falls back to heuristic."""
    secs = [
        PaperSection(title="2.1 Step One", page_start=1, page_end=1, text="Alpha text. Beta text."),
        PaperSection(title="2.2 Step Two", page_start=1, page_end=1, text="Gamma text. Delta text."),
        PaperSection(title="2.3 Step Three", page_start=2, page_end=2, text="Epsilon text. Zeta text."),
        PaperSection(title="2.4 Step Four", page_start=2, page_end=2, text="Eta text. Theta text."),
        PaperSection(title="2.5 Step Five", page_start=2, page_end=2, text="Iota text. Kappa text."),
    ]

    with patch("ingestion.pdf_parser.GEMINI_API_KEY", "fake_key"):
        with patch(
            "ingestion.pdf_parser._call_gemini_structured_with_timeout",
            side_effect=RuntimeError("504 DEADLINE_EXCEEDED"),
        ):
            nodes, edges, source = build_concept_graph("full text", secs)
            assert source == "heuristic"
            assert len(nodes) == 5


def test_gemini_timeout_enforcement():
    """Verify ThreadPoolExecutor enforces strict timeout and terminates on delay."""
    def slow_call(*args, **kwargs):
        time.sleep(0.5)
        return MagicMock()

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = slow_call

    with pytest.raises(concurrent.futures.TimeoutError):
        _call_gemini_structured_with_timeout(
            client=mock_client,
            model="gemini-3.8-flash",
            contents="test prompt",
            timeout_s=0.05,
        )


def test_build_concept_graph_post_processing_renumbering():
    """Verify raw LLM nodes with non-standard IDs are renumbered N1..Nk and unknown edges dropped."""
    raw_response = _LLMConceptGraphResponse(
        nodes=[
            _LLMConceptNode(id="step_a", label="Initial Data Loading", excerpt="We load data.", section="2.1 Method"),
            _LLMConceptNode(id="step_b", label="Graph Construction Pipeline", excerpt="We build graph.", section="2.2 Method"),
            _LLMConceptNode(id="step_c", label="Decay Modeling Optimization", excerpt="We model decay.", section="2.3 Method"),
            _LLMConceptNode(id="step_d", label="Student Peer Pairing", excerpt="We pair peers.", section="2.4 Method"),
            _LLMConceptNode(id="step_e", label="Dynamic Performance Updating", excerpt="We update stats.", section="2.5 Method"),
        ],
        edges=[
            _LLMConceptEdge(source="step_a", target="step_b", label="feeds"),
            _LLMConceptEdge(source="step_b", target="step_c", label=None),
            _LLMConceptEdge(source="step_c", target="step_d", label=None),
            _LLMConceptEdge(source="step_d", target="step_e", label=None),
            _LLMConceptEdge(source="step_e", target="step_e", label="self_loop"),  # Self loop -> must be dropped
            _LLMConceptEdge(source="step_a", target="UNKNOWN_ID", label="invalid"),  # Unknown target -> dropped
        ],
    )

    secs = [
        PaperSection(title="2.1 Method", page_start=1, page_end=1, text="We load data."),
        PaperSection(title="2.2 Method", page_start=1, page_end=1, text="We build graph."),
        PaperSection(title="2.3 Method", page_start=2, page_end=2, text="We model decay."),
        PaperSection(title="2.4 Method", page_start=2, page_end=2, text="We pair peers."),
        PaperSection(title="2.5 Method", page_start=2, page_end=2, text="We update stats."),
    ]

    with patch("ingestion.pdf_parser.GEMINI_API_KEY", "fake_key"):
        with patch("ingestion.pdf_parser._call_gemini_structured_with_timeout", return_value=raw_response):
            nodes, edges, source = build_concept_graph("full text", secs)

            assert source == "gemini"
            assert len(nodes) == 5
            assert [n.id for n in nodes] == ["N1", "N2", "N3", "N4", "N5"]

            # Edge checks
            edge_pairs = [(e.source, e.target) for e in edges]
            assert ("N1", "N2") in edge_pairs
            assert ("N2", "N3") in edge_pairs
            assert ("N3", "N4") in edge_pairs
            assert ("N4", "N5") in edge_pairs
            # Ensure invalid edge was dropped
            assert not any("UNKNOWN_ID" in (e.source, e.target) for e in edges)
            # Ensure self loop was dropped
            assert not any(e.source == e.target for e in edges)


# ============================================================================
# 4. Live Gemini API Test (@pytest.mark.gemini)
# ============================================================================


@pytest.mark.gemini
def test_gemini_live_call_sample_paper():
    """Live call to Gemini API on sample_paper.pdf verifying structured extraction or graceful fallback."""
    pdf_path = Path(__file__).resolve().parent.parent / "demo_cache" / "sample_paper.pdf"
    assert pdf_path.exists()

    pdf_bytes = pdf_path.read_bytes()
    title, page_count, sections, full_text = extract_sections(pdf_bytes)

    t0 = time.time()
    nodes, edges, source = build_concept_graph(full_text, sections)
    elapsed = time.time() - t0

    print(f"\nLive Gemini call finished in {elapsed:.2f}s with source='{source}'")
    print(f"Nodes ({len(nodes)}):")
    for n in nodes:
        print(f"  {n.id}: [{n.label}] page={n.page} sec='{n.section}'")

    print(f"Edges ({len(edges)}):")
    for e in edges:
        lbl = f" |{e.label}|" if e.label else ""
        print(f"  {e.source} -->{lbl} {e.target}")

    mermaid = build_mermaid(nodes, edges)
    print("\nMermaid Output:\n" + mermaid)

    # Acceptance criteria
    assert 5 <= len(nodes) <= 8
    assert [n.id for n in nodes] == [f"N{i+1}" for i in range(len(nodes))]
    assert len(edges) >= len(nodes) - 1
    assert source in ("gemini", "heuristic")

    for n in nodes:
        assert len(n.label.split()) <= 6
        assert len(n.label) <= 40
        assert n.excerpt.strip()

    assert mermaid.startswith("flowchart TD")
    assert "classDef active stroke-width:4px;" in mermaid
