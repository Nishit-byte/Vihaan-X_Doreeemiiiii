"""Extract research-paper sections and build an excerpt-grounded Mermaid graph."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from backend.models.schemas import PaperIndex, PaperNode

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 250
MAX_MODEL_CHARS = 32_000
NODE_LABELS = [
    "Research question", "Background", "Approach", "Data", "Evaluation",
    "Results", "Limitations", "Conclusion",
]
NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z0-9 &():,/'-]{1,90}$")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _extract_pdf_pages(pdf_bytes: bytes) -> list[str]:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None

    if fitz is not None:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            if document.page_count > MAX_PDF_PAGES:
                raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page ingestion limit.")
            return [page.get_text("text", sort=True) for page in document]
        finally:
            document.close()

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("PDF ingestion requires PyMuPDF (fitz).") from exc
    import io

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as document:
        if len(document.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page ingestion limit.")
        return [page.extract_text() or "" for page in document.pages]


def _extract_sections(page_texts: list[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_title = ""
    current_pages: list[int] = []
    current_lines: list[str] = []

    def flush() -> None:
        body = " ".join(line.strip() for line in current_lines if line.strip())
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            sections.append({
                "title": current_title or f"Section {len(sections) + 1}",
                "page_start": min(current_pages) if current_pages else 1,
                "page_end": max(current_pages) if current_pages else 1,
                "text": body,
            })

    for page_number, page_text in enumerate(page_texts, start=1):
        for raw_line in page_text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            words = line.split()
            is_known_heading = line.casefold() in {
                "abstract", "introduction", "background", "related work", "method",
                "methodology", "data", "experiments", "evaluation", "results",
                "discussion", "limitations", "conclusion", "references",
                "acknowledgements", "acknowledgments",
            }
            is_title_case_heading = (
                1 <= len(words) <= 8
                and not line.endswith((".", "!", "?", ";"))
                and all(word[:1].isupper() for word in words if word[:1].isalpha())
            )
            is_heading = bool(NUMBERED_HEADING_RE.match(line)) or is_known_heading or is_title_case_heading
            if is_heading and current_lines:
                flush()
                current_title = line
                current_pages = [page_number]
                current_lines = []
            else:
                if not current_title:
                    current_title = f"Page {page_number}"
                if page_number not in current_pages:
                    current_pages.append(page_number)
                current_lines.append(line)
    flush()

    if not sections:
        for page_number, page_text in enumerate(page_texts, start=1):
            text = re.sub(r"\s+", " ", page_text).strip()
            if text:
                sections.append({
                    "title": f"Page {page_number}",
                    "page_start": page_number,
                    "page_end": page_number,
                    "text": text,
                })
    return sections


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    return [part.strip() for part in SENTENCE_RE.split(normalized) if part.strip()]


def _fallback_nodes(sections: list[dict[str, Any]], whole_text: str) -> list[dict[str, str]]:
    # Prefer section-local pairs, then use adjacent source sentences as a fallback.
    nodes: list[dict[str, str]] = []
    for section in sections:
        sentences = _sentences(section["text"])
        for offset in range(0, len(sentences) - 1, 2):
            nodes.append({
                "label": section["title"],
                "excerpt": f"{sentences[offset]} {sentences[offset + 1]}",
                "section": section["title"],
            })
            if len(nodes) == 8:
                break
        if len(nodes) == 8:
            break

    if len(nodes) < 5:
        sentences = _sentences(whole_text)
        pairs = [sentences[index:index + 2] for index in range(0, len(sentences) - 1, 2)]
        nodes = [
            {
                "label": NODE_LABELS[index % len(NODE_LABELS)],
                "excerpt": " ".join(pair),
                "section": "Paper overview",
            }
            for index, pair in enumerate(pairs[:8])
        ]
    return nodes[:8]


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _valid_generated_nodes(
    value: Any,
    source_text: str,
    sections: list[dict[str, Any]],
) -> list[dict[str, str]] | None:
    if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
        return None
    nodes: list[dict[str, str]] = []
    source = _normalized(source_text)
    for item in value["nodes"]:
        if not isinstance(item, dict):
            return None
        label = item.get("label")
        excerpt = item.get("excerpt")
        if not isinstance(label, str) or not isinstance(excerpt, str):
            return None
        excerpt = _normalized(excerpt)
        if excerpt not in source or len(_sentences(excerpt)) < 2:
            return None
        section_title = next(
            (section["title"] for section in sections if excerpt in _normalized(section["text"])),
            "Paper overview",
        )
        nodes.append({"label": label.strip(), "excerpt": excerpt, "section": section_title})
    if not 5 <= len(nodes) <= 8:
        return None
    return nodes


def _ask_gemini_once(paper_text: str) -> dict[str, Any] | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    prompt = (
        "Create a 5-to-8 node directed research-paper architecture graph. Return only JSON "
        'with shape {"nodes":[{"label":"...","excerpt":"..."}],"edges":[["N1","N2"]]}. '
        "Each excerpt must be exactly two adjacent verbatim sentences from the supplied paper text. "
        "Use concise stage labels and edges in reading order. Do not invent claims or excerpts.\n\n"
        "PAPER TEXT:\n" + paper_text[:MAX_MODEL_CHARS]
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + model
        + ":generateContent?key="
        + api_key
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError):
        return None


def _mermaid_label(label: str) -> str:
    safe = re.sub(r"[\r\n\[\]{}|]", " ", label)
    safe = safe.replace('"', "'")
    return re.sub(r"\s+", " ", safe).strip()[:90] or "Paper stage"


def _build_mermaid(nodes: list[dict[str, str]], generated: dict[str, Any] | None) -> str:
    lines = ["flowchart TD"]
    for index, node in enumerate(nodes, start=1):
        lines.append(f'    N{index}["{_mermaid_label(node["label"])}"]')

    allowed = {f"N{index}" for index in range(1, len(nodes) + 1)}
    edges: list[tuple[str, str]] = []
    if generated and isinstance(generated.get("edges"), list):
        for edge in generated["edges"]:
            if (
                isinstance(edge, list)
                and len(edge) == 2
                and edge[0] in allowed
                and edge[1] in allowed
                and edge[0] != edge[1]
            ):
                edges.append((edge[0], edge[1]))
    if not edges:
        edges = [(f"N{index}", f"N{index + 1}") for index in range(1, len(nodes))]
    lines.extend(f"    {start} --> {end}" for start, end in edges)
    return "\n".join(lines)


def parse_research_paper(pdf_bytes: bytes) -> PaperIndex:
    """Extract PDF text and build an excerpt-grounded 5-to-8-node concept map."""
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB ingestion limit.")
    page_texts = _extract_pdf_pages(pdf_bytes)
    if not page_texts:
        raise ValueError("No pages could be read from this PDF.")
    whole_text = re.sub(r"\s+", " ", " ".join(page_texts)).strip()
    if not whole_text:
        raise ValueError("No selectable text was found; scanned PDFs need OCR before ingestion.")

    sections = _extract_sections(page_texts)
    first_lines = [line.strip() for line in page_texts[0].splitlines() if line.strip()]
    title = first_lines[0][:200] if first_lines else "Untitled research paper"
    generated = _ask_gemini_once(whole_text)
    nodes = _valid_generated_nodes(generated, whole_text, sections) if generated else None
    warnings: list[str] = []
    if nodes is None:
        nodes = _fallback_nodes(sections, whole_text)
        if generated is None and os.environ.get("GEMINI_API_KEY"):
            warnings.append("Gemini was unavailable or returned invalid excerpts; a local graph was used.")
        elif not os.environ.get("GEMINI_API_KEY"):
            warnings.append("GEMINI_API_KEY is not set; a local section-based graph was used.")
    if not nodes:
        raise ValueError("The paper did not contain enough text to build an architecture graph.")

    paper_nodes = [
        PaperNode(
            node_id=f"N{index}",
            label=node["label"],
            section=node.get("section", "Paper overview"),
            excerpt=node["excerpt"],
        )
        for index, node in enumerate(nodes, start=1)
    ]
    graph_method = "Gemini-validated excerpts" if generated and _valid_generated_nodes(generated, whole_text, sections) else "local section fallback"
    return PaperIndex(
        title=title,
        mermaid_graph=_build_mermaid(nodes, generated),
        nodes=paper_nodes,
        node_excerpts={node.node_id: node.excerpt for node in paper_nodes},
        full_text_summary=(
            f"Extracted {len(sections)} sections across {len(page_texts)} pages; "
            f"graph built with {graph_method}. "
            + (" ".join(warnings) if warnings else "")
        ).strip(),
    )


def load_demo_paper_bytes() -> bytes:
    """Read the bundled paper used by offline demos."""
    path = Path(__file__).resolve().parent.parent / "demo_cache" / "sample_paper.pdf"
    return path.read_bytes()
