"""Tests for Task B3: PDF text and section extraction, sample paper generation."""

from pathlib import Path
import pytest
from fpdf import FPDF

from demo_cache.build_sample_paper import (
    DEFAULT_OUTPUT_PDF,
    PAPER_TITLE,
    build_sample_paper,
)
from ingestion.models import IngestionError, PaperSection
from ingestion.pdf_parser import extract_sections


def test_sample_paper_file_exists():
    """Verify that backend/demo_cache/sample_paper.pdf exists and is non-empty."""
    assert DEFAULT_OUTPUT_PDF.exists(), f"Missing sample paper at {DEFAULT_OUTPUT_PDF}"
    assert DEFAULT_OUTPUT_PDF.stat().st_size > 1000, "sample_paper.pdf is unexpectedly small"


def test_sample_paper_deterministic():
    """Verify build_sample_paper produces byte-for-byte deterministic output."""
    b1 = build_sample_paper()
    b2 = build_sample_paper()
    assert b1 == b2, "build_sample_paper output is not deterministic"
    assert len(b1) > 2000


def test_extract_sections_sample_paper():
    """Verify extract_sections extracts title, >= 8 sections, and 6 method stages in order."""
    pdf_bytes = DEFAULT_OUTPUT_PDF.read_bytes()
    title, page_count, sections, full_text = extract_sections(pdf_bytes)

    # 1. Title verification
    assert title == PAPER_TITLE, f"Expected title {PAPER_TITLE!r}, got {title!r}"

    # 2. Page count (3-4 pages)
    assert 3 <= page_count <= 4, f"Expected 3-4 pages, got {page_count}"

    # 3. Section count >= 8
    assert len(sections) >= 8, f"Expected >= 8 sections, got {len(sections)}"

    titles = [s.title for s in sections]

    # Verify Abstract, 1 Introduction, 2 Method, 3 Evaluation, 4 Limitations, References
    assert any("Abstract" in t for t in titles), f"Abstract missing from {titles}"
    assert any("1 Introduction" in t for t in titles), f"1 Introduction missing from {titles}"
    assert any("2 Method" in t for t in titles), f"2 Method missing from {titles}"
    assert any("3 Evaluation" in t for t in titles), f"3 Evaluation missing from {titles}"
    assert any("4 Limitations" in t for t in titles), f"4 Limitations missing from {titles}"
    assert any("References" in t for t in titles), f"References missing from {titles}"

    # 4. Six method stages in sequential order (2.1 to 2.6)
    expected_stages = [
        "2.1 Concept Knowledge Graph Construction",
        "2.2 Dynamic Memory Decay Modeling",
        "2.3 Peer Complementarity Scoring",
        "2.4 Synchronous Pairing and Session Scheduling",
        "2.5 Collaborative Question Generation",
        "2.6 Dual-Feedback Performance Update",
    ]

    stage_indices: list[int] = []
    for stage in expected_stages:
        matching = [idx for idx, t in enumerate(titles) if stage in t]
        assert matching, f"Method stage {stage!r} not found in extracted titles: {titles}"
        stage_indices.append(matching[0])

    assert stage_indices == sorted(stage_indices), (
        f"Method stages are not in sequential order: {stage_indices}"
    )

    # 5. Page ranges and content validity
    for sec in sections:
        assert isinstance(sec, PaperSection)
        assert 1 <= sec.page_start <= page_count
        assert sec.page_start <= sec.page_end <= page_count
        assert len(sec.text.strip()) > 0, f"Section {sec.title} has empty text"

    # 6. full_text checks
    assert title in full_text
    assert "Spaced repetition" in full_text
    assert "Topological ordering" in full_text
    assert "Edmonds blossom algorithm" in full_text
    assert "Taxonomy of Educational Objectives" in full_text


def test_no_heading_pdf_per_page_fallback():
    """Verify a PDF without headings falls back to exactly one section per page."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for p in range(3):
        pdf.add_page()
        pdf.set_font("Helvetica", "", 10)
        for i in range(4):
            pdf.multi_cell(
                pdf.epw,
                5.0,
                f"Page {p + 1} narrative paragraph {i + 1}. Unformatted uniform text without headings.",
                new_x="LMARGIN",
                new_y="NEXT",
            )
            pdf.ln(3)

    pdf_bytes = bytes(pdf.output())
    title, page_count, sections, full_text = extract_sections(pdf_bytes)

    assert page_count == 3
    assert len(sections) == 3, f"Expected 3 fallback sections, got {len(sections)}"
    assert [s.title for s in sections] == ["Page 1", "Page 2", "Page 3"]

    for idx, s in enumerate(sections):
        p_num = idx + 1
        assert s.page_start == p_num
        assert s.page_end == p_num
        assert f"Page {p_num} narrative paragraph" in s.text


def test_garbage_bytes_raises_ingestion_error():
    """Verify corrupted or invalid PDF bytes raise IngestionError."""
    with pytest.raises(IngestionError) as exc_info:
        extract_sections(b"not a valid pdf stream at all")
    assert "Unreadable PDF" in str(exc_info.value)


def test_empty_bytes_raises_ingestion_error():
    """Verify empty bytes raise IngestionError."""
    with pytest.raises(IngestionError) as exc_info:
        extract_sections(b"")
    assert "empty" in str(exc_info.value).lower()


def test_encrypted_pdf_raises_ingestion_error():
    """Verify password-encrypted PDF raises IngestionError."""
    pdf = FPDF()
    pdf.set_encryption(user_password="userpass", owner_password="ownerpass")
    pdf.add_page()
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(text="Encrypted document body")
    enc_bytes = bytes(pdf.output())

    with pytest.raises(IngestionError) as exc_info:
        extract_sections(enc_bytes)
    assert "encrypted" in str(exc_info.value).lower()


def test_image_only_or_empty_text_raises_ingestion_error():
    """Verify PDF with pages but no extractable text raises IngestionError."""
    pdf = FPDF()
    pdf.add_page()
    # No text added to page
    empty_doc_bytes = bytes(pdf.output())

    with pytest.raises(IngestionError) as exc_info:
        extract_sections(empty_doc_bytes)
    assert "scanned" in str(exc_info.value).lower() or "image-only" in str(exc_info.value).lower()


def test_dehyphenation_and_whitespace_normalization():
    """Verify hyphenated line breaks are reconnected and whitespace is cleaned."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(pdf.epw, 8, "Hyphenation Test Paper", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(pdf.epw, 6, "1 Introduction", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    # Paragraph with explicit line break hyphenation
    pdf.multi_cell(
        pdf.epw,
        5,
        "We evaluate the perfor-\nmance of the collaborative rec-\nommender across benchmarks.",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    pdf_bytes = bytes(pdf.output())
    title, page_count, sections, full_text = extract_sections(pdf_bytes)

    assert title == "Hyphenation Test Paper"
    assert len(sections) == 1
    # Check that performance and recommender were de-hyphenated
    assert "performance" in sections[0].text
    assert "recommender" in sections[0].text
    assert "perfor-\nmance" not in sections[0].text
    assert "performance" in full_text
    assert "recommender" in full_text


def test_roman_numeral_and_unnumbered_known_headings():
    """Verify Roman numeral headings and known unnumbered headings are detected."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(pdf.epw, 8, "Roman Numeral Architecture", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    headings_and_body = [
        ("Abstract", "Overview of system components."),
        ("I. Introduction", "Introduction to distributed state machines."),
        ("II. Proposed Approach", "Design of consensus engine."),
        ("III. Experimental Results", "Empirical latency benchmarks."),
        ("IV. Limitations", "Throughput bottlenecks under high churn."),
        ("References", "[1] Lamport. Time, Clocks, and the Ordering of Events. 1978."),
    ]

    for h, b in headings_and_body:
        pdf.set_font("Helvetica", "B", 12)
        pdf.multi_cell(pdf.epw, 6, h, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(pdf.epw, 5, b, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    pdf_bytes = bytes(pdf.output())
    title, page_count, sections, full_text = extract_sections(pdf_bytes)

    assert title == "Roman Numeral Architecture"
    assert len(sections) == 6
    extracted_titles = [s.title for s in sections]
    assert extracted_titles == [
        "Abstract",
        "I. Introduction",
        "II. Proposed Approach",
        "III. Experimental Results",
        "IV. Limitations",
        "References",
    ]
