"""Unit and integration tests for Task B5: Excerpt verification, parse_research_paper, and paper cache."""

from __future__ import annotations

import hashlib
from pathlib import Path
import time
from unittest.mock import patch

import pytest

from ingestion.config import DEMO_CACHE_DIR
from ingestion.models import (
    ConceptEdge,
    ConceptNode,
    IngestionError,
    PaperIndex,
    PaperSection,
)
from ingestion.pdf_parser import (
    _normalize_text,
    _split_into_sentences,
    extract_sections,
    load_cached_paper,
    parse_research_paper,
    save_cached_paper,
    verify_excerpt,
)


@pytest.fixture
def sample_paper_bytes() -> bytes:
    """Read bytes of deterministic sample_paper.pdf from demo_cache."""
    pdf_path = Path(DEMO_CACHE_DIR) / "sample_paper.pdf"
    assert pdf_path.is_file(), f"sample_paper.pdf not found at {pdf_path}"
    return pdf_path.read_bytes()


@pytest.fixture
def sample_full_text(sample_paper_bytes: bytes) -> str:
    """Extract full text from sample_paper.pdf for verification tests."""
    _, _, _, full_text = extract_sections(sample_paper_bytes)
    return full_text


# ============================================================================
# 1. verify_excerpt Tests: Exact Match
# ============================================================================

def test_verify_excerpt_exact_sentence(sample_full_text: str):
    """An exact verbatim sentence from the paper returns (excerpt, True)."""
    # Sample paper Method 2.1 text contains:
    verbatim = (
        "We construct a directed concept knowledge graph from the curriculum ontology "
        "where vertices represent granular technical concepts and directed edges denote prerequisite dependencies."
    )
    result_text, is_exact = verify_excerpt(verbatim, sample_full_text)
    assert is_exact is True
    assert result_text == verbatim


def test_verify_excerpt_exact_with_quotes_dashes_whitespace():
    """Exact match succeeds after normalizing curly quotes, unicode dashes, and extra whitespace."""
    paper_text = (
        'The architecture utilizes “Dynamic Memory Decay” — modeling exponential forgetting curves.\n'
        'Stage 2.2 calculates the optimal interval.'
    )
    # Query uses standard ascii quotes, standard hyphen, and extra whitespace
    query = 'The architecture utilizes   "Dynamic Memory Decay"   -   modeling exponential forgetting curves.'
    result_text, is_exact = verify_excerpt(query, paper_text)
    assert is_exact is True
    assert result_text == query.strip()


def test_verify_excerpt_exact_substring(sample_full_text: str):
    """A verbatim clause/substring within a longer sentence returns (excerpt, True)."""
    sub_clause = "vertices represent granular technical concepts and directed edges denote prerequisite dependencies"
    result_text, is_exact = verify_excerpt(sub_clause, sample_full_text)
    assert is_exact is True
    assert result_text == sub_clause


# ============================================================================
# 2. verify_excerpt Tests: Paraphrase -> Closest Real Sentence + False
# ============================================================================

def test_verify_excerpt_paraphrase_returns_real_sentence(sample_full_text: str):
    """A paraphrased excerpt returns the closest real sentence from the text and False."""
    paraphrase = (
        "We build a directed concept knowledge graph from curriculum ontology "
        "where nodes represent technical concepts."
    )
    result_text, is_exact = verify_excerpt(paraphrase, sample_full_text)

    assert is_exact is False
    # The returned result_text must be a real sentence found in the paper's text
    assert result_text in sample_full_text
    assert "concept knowledge graph" in result_text
    assert "prerequisite dependencies" in result_text


def test_verify_excerpt_minor_typo_fuzzy_match():
    """A sentence with typos returns the real verbatim sentence and False."""
    text = (
        "Peer Complementarity Scoring matches students based on mastery levels. "
        "Synchronous Pairing and Session Scheduling groups learners into breakout channels."
    )
    typo_excerpt = "Peer Complementarity Scorin matches studnts based on mastery levels."
    result_text, is_exact = verify_excerpt(typo_excerpt, text)
    assert is_exact is False
    assert result_text == "Peer Complementarity Scoring matches students based on mastery levels."


# ============================================================================
# 3. Sentence Splitting Tests: Survives 'e.g.', 'et al.', Decimals & 2-Sentence Windows
# ============================================================================

def test_sentence_splitting_survives_abbreviations_and_decimals():
    """Sentence splitting does not break on 'e.g.', 'et al.', decimals, or academic abbreviations."""
    sample_text = (
        "We evaluate the method, e.g. on 100 benchmark tasks. "
        "Smith et al. (2020) demonstrated convergence at p = 0.05. "
        "In Section 2.1, the accuracy reached 98.4% vs. 92.1% in Dr. Smith's model. "
        "Final results are summarized in Fig. 3."
    )
    sentences = _split_into_sentences(sample_text)
    assert len(sentences) == 4
    assert sentences[0] == "We evaluate the method, e.g. on 100 benchmark tasks."
    assert sentences[1] == "Smith et al. (2020) demonstrated convergence at p = 0.05."
    assert sentences[2] == "In Section 2.1, the accuracy reached 98.4% vs. 92.1% in Dr. Smith's model."
    assert sentences[3] == "Final results are summarized in Fig. 3."


def test_verify_excerpt_two_sentence_window_match():
    """Fuzzy matching selects a 2-sentence window when an excerpt paraphrases two consecutive sentences."""
    text = (
        "Concept Knowledge Graph Construction parses input material into prerequisite dependencies. "
        "Dynamic Memory Decay Modeling calculates retention intervals, e.g. using exponential forgetting curves. "
        "Peer Complementarity Scoring matches students based on mastery levels."
    )
    # Paraphrase that spans concepts across sentence 1 and sentence 2
    two_sentence_paraphrase = (
        "Concept Knowledge Graph Construction parses material. "
        "Dynamic Memory Decay Modeling calculates retention intervals using curves."
    )
    result_text, is_exact = verify_excerpt(two_sentence_paraphrase, text)
    assert is_exact is False
    # The closest real text should be the combination of sentence 1 and sentence 2
    assert "Concept Knowledge Graph Construction" in result_text
    assert "Dynamic Memory Decay Modeling" in result_text
    assert "Peer Complementarity Scoring" not in result_text


# ============================================================================
# 4. verify_excerpt Edge Cases
# ============================================================================

def test_verify_excerpt_empty_inputs():
    """Empty or whitespace-only excerpts return ('', False); empty full_text returns (clean_excerpt, False)."""
    assert verify_excerpt("", "Some full text.") == ("", False)
    assert verify_excerpt("   ", "Some full text.") == ("", False)
    assert verify_excerpt("Important excerpt.", "") == ("Important excerpt.", False)
    assert verify_excerpt("Important excerpt.", "   ") == ("Important excerpt.", False)


# ============================================================================
# 5. Cache Round-Trip: save_cached_paper and load_cached_paper
# ============================================================================

def test_cache_save_and_load_roundtrip(tmp_path: Path):
    """PaperIndex round-trip through save_cached_paper and load_cached_paper."""
    dummy_pdf_bytes = b"%PDF-1.4 dummy paper test bytes for roundtrip"
    paper_id = hashlib.sha256(dummy_pdf_bytes).hexdigest()[:16]

    dummy_index = PaperIndex(
        paper_id=paper_id,
        title="Test Spaced Repetition Paper",
        page_count=2,
        sections=[
            PaperSection(title="1 Introduction", page_start=1, page_end=1, text="Intro text."),
            PaperSection(title="2 Method", page_start=2, page_end=2, text="Method text."),
        ],
        full_text="Intro text.\n\nMethod text.",
        nodes=[
            ConceptNode(
                id="N1",
                label="Graph Construction",
                excerpt="Intro text.",
                section="1 Introduction",
                page=1,
                excerpt_verified=True,
            ),
            ConceptNode(
                id="N2",
                label="Decay Modeling",
                excerpt="Method text.",
                section="2 Method",
                page=2,
                excerpt_verified=True,
            ),
        ],
        edges=[ConceptEdge(source="N1", target="N2", label="feeds")],
        mermaid="flowchart TD\n    N1[\"Graph Construction\"] -->|feeds| N2[\"Decay Modeling\"]\n    classDef active stroke-width:4px;",
        excerpts={"N1": "Intro text.", "N2": "Method text."},
        source="heuristic",
    )

    # Save to cache
    save_cached_paper(dummy_index)

    # Load from cache using dummy_pdf_bytes
    loaded_index = load_cached_paper(dummy_pdf_bytes)
    assert loaded_index is not None
    assert loaded_index.paper_id == dummy_index.paper_id
    assert loaded_index.title == dummy_index.title
    assert loaded_index.page_count == dummy_index.page_count
    assert len(loaded_index.sections) == 2
    assert len(loaded_index.nodes) == 2
    assert loaded_index.nodes[0].id == "N1"
    assert loaded_index.nodes[0].excerpt_verified is True
    assert loaded_index.edges[0].source == "N1"
    assert loaded_index.edges[0].target == "N2"
    assert loaded_index.mermaid == dummy_index.mermaid
    assert loaded_index.excerpts == dummy_index.excerpts
    assert loaded_index.source == "heuristic"

    # Clean up test cache file
    cache_file = Path(DEMO_CACHE_DIR) / "papers" / f"{paper_id}.json"
    if cache_file.exists():
        cache_file.unlink()


def test_load_cached_paper_missing_or_empty():
    """load_cached_paper returns None for empty bytes or non-existent cached papers."""
    assert load_cached_paper(b"") is None
    assert load_cached_paper(b"random-nonexistent-bytes-1234567890") is None


# ============================================================================
# 6. parse_research_paper: Cache Hit in < 50 ms
# ============================================================================

def test_second_parse_returns_cache_under_50ms(sample_paper_bytes: bytes):
    """Second call to parse_research_paper on the same PDF returns source 'cache' in < 50 ms."""
    # Ensure cache exists by running once (or checking existing cache)
    initial_index = parse_research_paper(sample_paper_bytes, use_gemini=False, use_cache=True)
    assert initial_index is not None

    # Second call must hit cache and complete in < 50 ms
    t0 = time.perf_counter()
    cached_index = parse_research_paper(sample_paper_bytes, use_gemini=False, use_cache=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert cached_index.source == "cache"
    assert elapsed_ms < 50.0, f"Cache hit took {elapsed_ms:.2f} ms (target: < 50 ms)"
    assert cached_index.paper_id == "73cbee6fbc268346"
    assert cached_index.title == "Adaptive Spaced Repetition with Peer Matching"
    assert len(cached_index.nodes) == 6
    assert all(node.excerpt_verified is True for node in cached_index.nodes)
    assert len(cached_index.excerpts) == 6
    assert cached_index.mermaid.startswith("flowchart TD")


# ============================================================================
# 7. parse_research_paper: Offline Mode with use_gemini=False
# ============================================================================

def test_parse_research_paper_offline_heuristic(sample_paper_bytes: bytes):
    """parse_research_paper with use_gemini=False works completely offline without network/API."""
    index = parse_research_paper(sample_paper_bytes, use_gemini=False, use_cache=False)

    assert index.source == "heuristic"
    assert index.paper_id == "73cbee6fbc268346"
    assert index.title == "Adaptive Spaced Repetition with Peer Matching"
    assert index.page_count == 3
    assert len(index.nodes) == 6
    # In heuristic mode on sample paper, opening sentences are pulled directly from text -> verified True
    assert all(node.excerpt_verified is True for node in index.nodes)
    assert len(index.edges) == 5
    assert index.mermaid.startswith("flowchart TD")
    assert "classDef active stroke-width:4px;" in index.mermaid
    assert index.excerpts["N1"] == index.nodes[0].excerpt


# ============================================================================
# 8. parse_research_paper: Gemini Failure Falls Back Without Raising
# ============================================================================

def test_parse_research_paper_gemini_failure_fallback(sample_paper_bytes: bytes):
    """Gemini failure never raises; parse_research_paper falls back gracefully to heuristic."""
    with patch("ingestion.pdf_parser.build_concept_graph", side_effect=RuntimeError("Simulated API failure")):
        index = parse_research_paper(sample_paper_bytes, use_gemini=True, use_cache=False)
        assert index.source == "heuristic"
        assert len(index.nodes) == 6
        assert index.title == "Adaptive Spaced Repetition with Peer Matching"


# ============================================================================
# 9. parse_research_paper: Unreadable PDFs Raise IngestionError
# ============================================================================

def test_parse_research_paper_unreadable_raises_ingestion_error():
    """Unreadable or empty PDF bytes raise IngestionError."""
    with pytest.raises(IngestionError, match="PDF document is empty"):
        parse_research_paper(b"")

    with pytest.raises(IngestionError, match="Unreadable PDF document"):
        parse_research_paper(b"Not a valid PDF byte string")


# ============================================================================
# 10. Live Gemini Integration Test (@pytest.mark.gemini)
# ============================================================================

@pytest.mark.gemini
def test_parse_research_paper_live_gemini(sample_paper_bytes: bytes):
    """Live call to parse_research_paper using Gemini API when GEMINI_API_KEY is available."""
    index = parse_research_paper(sample_paper_bytes, use_gemini=True, use_cache=False)
    assert index.source in ("gemini", "heuristic")
    assert 5 <= len(index.nodes) <= 8
    assert all(isinstance(n.excerpt_verified, bool) for n in index.nodes)
    assert index.mermaid.startswith("flowchart TD")
