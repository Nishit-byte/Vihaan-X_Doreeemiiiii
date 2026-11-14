"""
Extract research-paper sections, layout metadata, and a grounded method pipeline graph.
"""

from __future__ import annotations

from collections import Counter
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.ingestion.paper_breakdown import (
    YEAR_VENUE_RE,
    build_paper_breakdown,
    build_scanned_pdf_breakdown,
    find_exact_page_for_excerpt,
    is_pdf_furniture,
)
from backend.models.schemas import PaperIndex, PaperNode

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDF_PAGES = 250
MAX_MODEL_CHARS = 32_000

KNOWN_HEADINGS = {
    "abstract",
    "introduction",
    "background",
    "related work",
    "prior work",
    "preliminaries",
    "problem statement",
    "problem formulation",
    "method",
    "methodology",
    "methods",
    "proposed method",
    "proposed approach",
    "approach",
    "architecture",
    "framework",
    "system overview",
    "experiments",
    "experimental setup",
    "data",
    "datasets",
    "data and evaluation",
    "evaluation",
    "results",
    "experiments and results",
    "ablation study",
    "ablations",
    "discussion",
    "limitations",
    "ethical considerations",
    "broader impact",
    "conclusion",
    "conclusions",
    "conclusion and future work",
    "future work",
    "references",
    "acknowledgements",
    "acknowledgments",
    "appendix",
}

GENERIC_BANNED_NODE_LABELS = KNOWN_HEADINGS | {
    "paper overview",
    "page 1",
    "page 2",
    "page 3",
    "table 1",
    "figure 1",
}

NUMBERED_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?|[IVX]{1,4}\.)\s+[A-Z][A-Za-z0-9 &():,/'-]{1,85}$"
)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _column_aware_line_order(
    raw_lines: List[Dict[str, Any]],
    page_width: float,
) -> List[Dict[str, Any]]:
    """
    Orders extracted lines in two-column or single-column reading order without interleaving
    left-column and right-column lines that happen to share the same y-coordinate.
    """
    if not raw_lines or page_width <= 0:
        return raw_lines

    mid_x = page_width * 0.50
    narrow_left: List[Dict[str, Any]] = []
    narrow_right: List[Dict[str, Any]] = []
    wide_spans: List[Dict[str, Any]] = []

    for ln in raw_lines:
        width = ln["x1"] - ln["x0"]
        center = (ln["x0"] + ln["x1"]) * 0.5
        spans_center = ln["x0"] < page_width * 0.43 and ln["x1"] > page_width * 0.57
        if spans_center or width > page_width * 0.56:
            wide_spans.append(ln)
        elif center < mid_x:
            narrow_left.append(ln)
        else:
            narrow_right.append(ln)

    # Heuristic: genuine 2-column page has substantial narrow lines on both halves
    if len(narrow_left) >= 6 and len(narrow_right) >= 6:
        wide_top = sorted(
            [w for w in wide_spans if w["y0"] <= min(narrow_right[0]["y0"], narrow_left[0]["y0"]) + 24],
            key=lambda x: (x["y0"], x["x0"]),
        )
        wide_rest = [w for w in wide_spans if w not in wide_top]
        # Fold remaining wide captions/headings into whichever column or bottom makes sense chronologically
        narrow_left.sort(key=lambda x: (x["y0"], x["x0"]))
        narrow_right.sort(key=lambda x: (x["y0"], x["x0"]))
        wide_rest.sort(key=lambda x: (x["y0"], x["x0"]))
        return wide_top + narrow_left + narrow_right + wide_rest

    return sorted(raw_lines, key=lambda x: (x["y0"], x["x0"]))


def _extract_pdf_with_layout(pdf_bytes: bytes) -> Tuple[List[str], Dict[str, Any]]:
    """
    Extracts clean page texts and layout metadata (Page 1 font sizes, bounding boxes, venue hints).
    Strips watermarks, copyright footers, vertical margin text, and repeating headers/footers.
    """
    try:
        import pymupdf as fitz  # preferred PyMuPDF import
    except ImportError:
        try:
            import fitz  # type: ignore
        except ImportError:
            fitz = None  # type: ignore

    if fitz is not None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            raise ValueError("Could not read this file as a valid PDF. Please upload a valid PDF document.") from exc
        try:
            if doc.page_count > MAX_PDF_PAGES:
                raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page ingestion limit.")

            raw_pages_lines: List[List[Dict[str, Any]]] = []
            font_counter: Counter[float] = Counter()
            venue_hints: List[str] = []
            page1_height = 792.0

            for page_idx, page in enumerate(doc):
                rect = page.rect
                pw = float(rect.width or 612.0)
                ph = float(rect.height or 792.0)
                if page_idx == 0:
                    page1_height = ph

                pdict = page.get_text("dict")
                page_lines: List[Dict[str, Any]] = []
                for block in pdict.get("blocks", []):
                    if block.get("type", 0) != 0:
                        continue
                    for line in block.get("lines", []):
                        direction = line.get("dir", (1, 0))
                        is_vertical = abs(float(direction[1])) > 0.5
                        spans = line.get("spans", [])
                        text = _clean_ws("".join(s.get("text", "") for s in spans))
                        if not text:
                            continue

                        # Harvest venue hint from top/side margin stamps before dropping furniture
                        if page_idx <= 1 and YEAR_VENUE_RE.search(text):
                            hint = text[:160]
                            if hint not in venue_hints and not is_pdf_furniture(text):
                                venue_hints.append(hint)
                            elif "cvpr" in text.lower() and "open access" in text.lower():
                                if "CVPR (Open Access)" not in venue_hints:
                                    venue_hints.append("CVPR (Computer Vision Foundation Open Access)")

                        if is_vertical:
                            # Vertical margin stamps (arXiv identifiers, CVPR watermarks)
                            continue

                        sizes = [float(s.get("size", 10.0)) for s in spans if _clean_ws(s.get("text", ""))]
                        flags = [int(s.get("flags", 0)) for s in spans if _clean_ws(s.get("text", ""))]
                        max_size = max(sizes) if sizes else 10.0
                        is_bold = any(bool(fl & 16) for fl in flags)
                        bbox = line.get("bbox", (0.0, 0.0, pw, ph))

                        if not is_pdf_furniture(text) and len(text) > 12:
                            font_counter[round(max_size, 1)] += len(text)

                        page_lines.append(
                            {
                                "text": text,
                                "x0": float(bbox[0]),
                                "y0": float(bbox[1]),
                                "x1": float(bbox[2]),
                                "y1": float(bbox[3]),
                                "size": max_size,
                                "is_bold": is_bold,
                                "is_vertical": is_vertical,
                                "in_margin": float(bbox[1]) < ph * 0.06 or float(bbox[3]) > ph * 0.94,
                            }
                        )

                ordered = _column_aware_line_order(page_lines, pw)
                raw_pages_lines.append(ordered)

            # Detect lines repeated across >=2 pages in top/bottom margins (running headers/footers)
            repeated_margin_lines: set[str] = set()
            if len(raw_pages_lines) >= 2:
                margin_counts: Counter[str] = Counter()
                for plines in raw_pages_lines:
                    seen_on_page: set[str] = set()
                    for ln in plines:
                        if ln["in_margin"] and len(ln["text"]) <= 110:
                            norm_key = re.sub(r"\d+", "#", ln["text"].lower())
                            seen_on_page.add(norm_key)
                    for k in seen_on_page:
                        margin_counts[k] += 1
                repeated_margin_lines = {k for k, cnt in margin_counts.items() if cnt >= 2}

            body_font_size = font_counter.most_common(1)[0][0] if font_counter else 10.0

            cleaned_pages: List[str] = []
            cleaned_pages_lines: List[List[Dict[str, Any]]] = []
            abstract_y0: Optional[float] = None

            for p_idx, plines in enumerate(raw_pages_lines):
                kept_lines: List[Dict[str, Any]] = []
                for ln in plines:
                    txt = ln["text"]
                    if is_pdf_furniture(txt):
                        continue
                    norm_key = re.sub(r"\d+", "#", txt.lower())
                    if ln["in_margin"] and norm_key in repeated_margin_lines:
                        continue
                    kept_lines.append(ln)
                    if p_idx == 0 and abstract_y0 is None:
                        low = txt.lower()
                        if low in ("abstract", "1 introduction", "1. introduction", "i. introduction") or low.startswith(
                            ("abstract ", "abstract—", "abstract:")
                        ):
                            abstract_y0 = ln["y0"]

                cleaned_pages_lines.append(kept_lines)
                cleaned_pages.append("\n".join(ln["text"] for ln in kept_lines))

            layout_meta: Dict[str, Any] = {
                "page1_lines": cleaned_pages_lines[0] if cleaned_pages_lines else [],
                "pages_lines": cleaned_pages_lines,
                "body_font_size": body_font_size,
                "abstract_y0": abstract_y0,
                "page1_height": page1_height,
                "venue_hints": venue_hints,
            }
            return cleaned_pages, layout_meta
        finally:
            doc.close()

    # Fallback: pdfplumber if PyMuPDF is missing
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("PDF ingestion requires PyMuPDF (pymupdf).") from exc

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as document:
        if len(document.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF exceeds the {MAX_PDF_PAGES}-page ingestion limit.")
        pages = []
        for page in document.pages:
            raw = page.extract_text() or ""
            kept = [ln for ln in raw.splitlines() if _clean_ws(ln) and not is_pdf_furniture(ln)]
            pages.append("\n".join(kept))
        return pages, {"venue_hints": []}


def _extract_pdf_pages(pdf_bytes: bytes) -> List[str]:
    """Compatibility helper returning clean page text strings."""
    pages, _ = _extract_pdf_with_layout(pdf_bytes)
    return pages


def _is_valid_heading(line: str, line_meta: Optional[Dict[str, Any]], body_font: float) -> bool:
    clean = _clean_ws(line)
    if not clean or is_pdf_furniture(clean):
        return False
    if len(clean) > 95:
        return False
    low = clean.casefold()
    # Explicit known academic section heading
    if low in KNOWN_HEADINGS:
        return True
    # Strict numbered heading (e.g. "3. Method", "4.2 Training Setup", "II. RELATED WORK")
    if NUMBERED_HEADING_RE.match(clean):
        # Reject metric rows / figure & table references
        if re.search(r"\b(?:table|figure|fig\.|eq\.|bleu|rouge|accuracy|f1)\b", low) and re.search(r"\d+\.\d+", clean):
            return False
        return True
    # Styled heading check (significantly larger or bold short line) when font metadata exists
    if line_meta:
        size = float(line_meta.get("size", body_font))
        is_bold = bool(line_meta.get("is_bold", False))
        words = clean.split()
        if (
            1 <= len(words) <= 7
            and not clean.endswith((".", "!", "?", ";", ","))
            and (size >= body_font * 1.10 or is_bold)
            and any(ch.isalpha() for ch in clean)
            and sum(1 for w in words if w.isupper() and len(w) >= 3) < 2  # skip table headers
        ):
            return True
    return False


def _extract_sections(
    page_texts: List[str],
    layout_meta: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current_title = ""
    current_pages: List[int] = []
    current_lines: List[str] = []

    body_font = float((layout_meta or {}).get("body_font_size") or 10.0)
    pages_lines: List[List[Dict[str, Any]]] = (layout_meta or {}).get("pages_lines") or []
    abstract_y0 = (layout_meta or {}).get("abstract_y0")

    def flush() -> None:
        body = " ".join(line.strip() for line in current_lines if line.strip())
        body = _clean_ws(body)
        if body:
            sections.append(
                {
                    "title": current_title or f"Section {len(sections) + 1}",
                    "page_start": min(current_pages) if current_pages else 1,
                    "page_end": max(current_pages) if current_pages else 1,
                    "text": body,
                }
            )

    for page_number, page_text in enumerate(page_texts, start=1):
        meta_list = pages_lines[page_number - 1] if page_number - 1 < len(pages_lines) else []
        raw_lines = [ln for ln in page_text.splitlines() if _clean_ws(ln)]
        for idx, raw_line in enumerate(raw_lines):
            line = _clean_ws(raw_line)
            if not line or is_pdf_furniture(line):
                continue
            line_meta = meta_list[idx] if idx < len(meta_list) and _clean_ws(meta_list[idx].get("text", "")) == line else None

            # Skip title & author block lines above Abstract on Page 1 so wrapped title words aren't treated as sections
            if page_number == 1 and abstract_y0 is not None and line_meta is not None:
                if float(line_meta.get("y0", 0.0)) < float(abstract_y0) - 2:
                    continue

            # Handle inline heading prefixes like "Abstract—We propose..." or "Abstract: This study..."
            m_inline = re.match(r"^(Abstract|Introduction|Method|Conclusion)\s*[—:\-]\s*(.+)$", line, re.IGNORECASE)
            if m_inline and len(m_inline.group(2)) > 20:
                if current_lines:
                    flush()
                current_title = m_inline.group(1).title()
                current_pages = [page_number]
                current_lines = [m_inline.group(2).strip()]
                continue

            if _is_valid_heading(line, line_meta, body_font) and (current_lines or line.casefold() in KNOWN_HEADINGS or NUMBERED_HEADING_RE.match(line)):
                if current_lines:
                    flush()
                current_title = line
                current_pages = [page_number]
                current_lines = []
            else:
                if not current_title:
                    current_title = "Paper Preamble"
                if page_number not in current_pages:
                    current_pages.append(page_number)
                current_lines.append(line)
    flush()

    if not sections:
        for page_number, page_text in enumerate(page_texts, start=1):
            text = _clean_ws(page_text)
            if text:
                sections.append(
                    {
                        "title": f"Page {page_number}",
                        "page_start": page_number,
                        "page_end": page_number,
                        "text": text,
                    }
                )
    return sections


def _sentences(text: str) -> List[str]:
    normalized = _clean_ws(re.sub(r"([a-zA-Z])-\s+([a-zA-Z])", r"\1\2", text))
    return [part.strip() for part in SENTENCE_RE.split(normalized) if len(part.strip()) > 15]


# Action-verb patterns that indicate genuine methodological / processing steps in research text
METHOD_ACTION_VERBS = (
    ("Input & Extraction", re.compile(r"\b(?:extract|ingest|parse|read|collect|tokeniz|sampl|receiv)(?:e|es|ed|ing|s)?\b", re.I)),
    ("Segmentation & Encoding", re.compile(r"\b(?:divid|split|segment|chunk|encod|embed|project|transform|map|represent)(?:e|es|ed|ing|s)?\b", re.I)),
    ("Graph / Model Construction", re.compile(r"\b(?:construct|build|form|align|attend|fus|aggregat|pair|comput|learn|train|us)(?:e|es|ed|ing|s)?\b", re.I)),
    ("Optimization & Loss", re.compile(r"\b(?:optimiz|minimiz|regulariz|fine-?tun|updat|weight|loss|objectiv)(?:e|es|ed|ing|s)?\b", re.I)),
    ("Retrieval / Inference", re.compile(r"\b(?:retriev|rank|predict|generat|decod|classif|infer|synthesiz)(?:e|es|ed|ing|s|y|ies|ied)?\b", re.I)),
    ("Verification & Evaluation", re.compile(r"\b(?:evaluat|check|verify|verified|compar|measur|benchmark|prevent|ablat|produc)(?:e|es|ed|ing|s)?\b", re.I)),
)


def _derive_distinct_stage_label(sentence: str, used_labels: set[str]) -> Optional[str]:
    """
    Produces a concise, descriptive label explaining *what this step does* (not a section heading).
    Never emits duplicate labels.
    """
    s_low = sentence.lower()
    # Try domain-specific readable action phrasing first
    specific_rules = (
        (r"\bextracts?\s+section\s+text", "Extract Section Text"),
        (r"\bdivides?\s+(?:the\s+)?explanation\s+into\s+stages", "Segment Into Method Stages"),
        (r"\bis\s+paired\s+with\s+(?:two\s+)?adjacent\s+source|\bpaired\s+with", "Pair Stages With Source Excerpts"),
        (r"\bsynthetic\s+papers\s+was\s+used\s+to\s+exercise", "Exercise Graph Extraction"),
        (r"\bchecked\s+whether\s+every\s+displayed\s+excerpt", "Verify Excerpt Grounding & IDs"),
        (r"\bsection-based\s+fallback\s+produced", "Build Fallback Stage Sequence"),
        (r"\bprevented\s+unsupported\s+paraphrases", "Enforce Excerpt Guardrail"),
        (r"\bself-?attention|multi-?head\s+attention", "Compute Multi-Head Attention"),
        (r"\bcontrastive\s+(?:loss|learning|alignment)", "Contrastive Alignment"),
        (r"\btokeniz|wordpiece|subword|byte-?pair", "Tokenize Input Sequence"),
        (r"\bembed|positional\s+encoding", "Encode Dense Embeddings"),
        (r"\bconvolution|resnet|backbone|feature\s+pyramid|voxel\s+features", "Extract Spatial Features"),
        (r"\bdirected\s+scene\s+graph|constructs\s+a\s+directed", "Construct Relational Graph"),
        (r"\bcross-?modal\s+transformer", "Cross-Modal Graph Alignment"),
        (r"\bdiffusion|denoising|latent", "Iterative Latent Denoising"),
        (r"\bloss\s+function|cross-?entropy|objective", "Optimize Training Objective"),
        (r"\bablation|baseline|benchmark|evaluation\s+metric", "Benchmark Against Baselines"),
    )
    for pat, nice_label in specific_rules:
        if re.search(pat, s_low) and nice_label.lower() not in used_labels:
            used_labels.add(nice_label.lower())
            return nice_label

    # General action-clause distillation: extract "<Verb Phrase> <Object Phrase>"
    m = re.search(
        r"\b(extract|parse|encode|embed|construct|build|segment|divide|align|compute|aggregate|train|optimize|fine-tune|predict|generate|retrieve|rank|evaluate|verify|check)\w*\s+"
        r"([a-zA-Z0-9 -]{4,38}?)(?:,|;|\.| which| that| so | using | via | to | and )",
        sentence,
        re.IGNORECASE,
    )
    if m:
        verb = m.group(1).capitalize()
        obj = re.sub(r"^(the|a|an)\s+", "", m.group(2).strip(), flags=re.I)
        words = obj.split()[:4]
        if words:
            candidate = f"{verb} {' '.join(w.capitalize() if not w.isupper() else w for w in words)}"
            candidate = candidate[:46].strip()
            if candidate.lower() not in GENERIC_BANNED_NODE_LABELS and candidate.lower() not in used_labels:
                used_labels.add(candidate.lower())
                return candidate

    # Last fallback: functional category bucket (only if not already used)
    for cat_label, pat in METHOD_ACTION_VERBS:
        if pat.search(sentence) and cat_label.lower() not in used_labels:
            used_labels.add(cat_label.lower())
            return cat_label

    return None


def _local_method_pipeline(
    sections: List[Dict[str, Any]],
    page_texts: List[str],
) -> Tuple[List[Dict[str, str]], str, Optional[str]]:
    """
    Extracts 3-to-7 distinct, grounded method-pipeline nodes directly from method/approach/evaluation
    passages. Never falls back to repeating section headings.
    Returns (nodes, status, note) where status is 'ok' or 'fallback'.
    """
    method_keywords = ("method", "methodology", "approach", "architecture", "framework", "system", "model", "algorithm", "proposed")
    eval_keywords = ("data", "dataset", "experiment", "evaluation", "result")

    prioritized_secs: List[Dict[str, Any]] = []
    for sec in sections:
        t = str(sec.get("title", "")).lower()
        if t in ("references", "acknowledgments", "acknowledgements", "paper preamble"):
            continue
        if any(k in t for k in method_keywords):
            prioritized_secs.append(sec)
    for sec in sections:
        t = str(sec.get("title", "")).lower()
        if any(k in t for k in eval_keywords) and sec not in prioritized_secs:
            prioritized_secs.append(sec)
    for sec in sections:
        t = str(sec.get("title", "")).lower()
        if t in ("abstract", "introduction", "overview") and sec not in prioritized_secs:
            prioritized_secs.append(sec)

    nodes: List[Dict[str, str]] = []
    used_labels: set[str] = set()
    used_excerpts: set[str] = set()

    for sec in prioritized_secs:
        sents = _sentences(sec.get("text", ""))
        sec_title = str(sec.get("title", "Methodology"))
        for idx, sent in enumerate(sents):
            # Require sentence to sound like a technical/method action or evaluation step
            if not any(pat.search(sent) for _, pat in METHOD_ACTION_VERBS):
                continue
            excerpt = sent
            if idx + 1 < len(sents) and len(sent) < 110:
                excerpt = f"{sent} {sents[idx + 1]}"
            excerpt_norm = _clean_ws(excerpt)
            if excerpt_norm in used_excerpts:
                continue

            stage_label = _derive_distinct_stage_label(sent, used_labels)
            if not stage_label:
                continue

            used_excerpts.add(excerpt_norm)
            exact_page = find_exact_page_for_excerpt(
                excerpt_norm, page_texts, default_page=int(sec.get("page_start", 1))
            )
            nodes.append(
                {
                    "label": stage_label,
                    "summary": sent,
                    "excerpt": excerpt_norm,
                    "section": sec_title,
                    "page": str(exact_page),
                }
            )
            if len(nodes) >= 6:
                return nodes, "ok", None

    if len(nodes) >= 3:
        return nodes, "ok", None

    return (
        [],
        "fallback",
        "A multi-stage technical method flow could not be inferred reliably from the extracted text. Use the Story Map and Full Breakdown instead.",
    )


def _ask_gemini_method_graph(paper_text: str) -> Optional[Dict[str, Any]]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    prompt = (
        "Analyze the research paper text below and reconstruct the paper's ACTUAL proposed method/pipeline as a directed graph of 4 to 6 functional stages.\n"
        "Return strictly valid JSON: "
        '{"nodes":[{"label":"...","summary":"1 plain sentence of what this stage does","excerpt":"exact verbatim sentence(s) from the text"}],"edges":[["N1","N2"]]}.\n'
        "Rules:\n"
        "1. NEVER use generic PDF section headings (like Abstract, Introduction, Results, Conclusion, Page 1, BLEU, ROUGE) as node labels.\n"
        "2. Each node label MUST be unique and describe an actual data transformation, component, training objective, or evaluation step.\n"
        "3. Every excerpt MUST be copied verbatim from the supplied text.\n"
        "4. Only add edges supported by the paper's workflow. If no clear method pipeline exists, return {\"nodes\":[],\"edges\":[]}.\n\n"
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


def _valid_generated_nodes(
    value: Any,
    source_text: str,
    sections: List[Dict[str, Any]],
    page_texts: List[str],
) -> Optional[List[Dict[str, str]]]:
    if not isinstance(value, dict) or not isinstance(value.get("nodes"), list):
        return None

    nodes: List[Dict[str, str]] = []
    seen_labels: set[str] = set()
    seen_excerpts: set[str] = set()
    norm_source = _clean_ws(re.sub(r"([a-zA-Z])-\s+([a-zA-Z])", r"\1\2", source_text)).lower()

    for item in value["nodes"]:
        if not isinstance(item, dict):
            continue
        label = _clean_ws(str(item.get("label") or ""))
        summary = _clean_ws(str(item.get("summary") or ""))
        excerpt = _clean_ws(str(item.get("excerpt") or ""))
        if not label or not excerpt or len(excerpt) < 25:
            continue
        if label.lower() in GENERIC_BANNED_NODE_LABELS or label.lower() in seen_labels:
            continue
        if is_pdf_furniture(label) or is_pdf_furniture(excerpt):
            continue
        excerpt_probe = excerpt[:50].lower()
        if excerpt_probe not in norm_source:
            continue
        if excerpt in seen_excerpts:
            continue

        seen_labels.add(label.lower())
        seen_excerpts.add(excerpt)
        exact_page = find_exact_page_for_excerpt(excerpt, page_texts, default_page=1)
        sec_title = next(
            (s["title"] for s in sections if excerpt_probe in _clean_ws(s.get("text", "")).lower()),
            "Methodology",
        )
        nodes.append(
            {
                "label": label[:60],
                "summary": summary or excerpt,
                "excerpt": excerpt,
                "section": str(sec_title),
                "page": str(exact_page),
            }
        )

    if len(nodes) < 3:
        return None
    return nodes[:7]


def _mermaid_label(label: str) -> str:
    safe = re.sub(r"[\r\n\[\]{}|]", " ", label)
    safe = safe.replace('"', "'")
    return re.sub(r"\s+", " ", safe).strip()[:75] or "Method stage"


def _build_mermaid(nodes: List[Dict[str, str]], generated: Optional[Dict[str, Any]]) -> str:
    if not nodes:
        return ""
    lines = ["flowchart TD"]
    for index, node in enumerate(nodes, start=1):
        lines.append(f'    N{index}["{_mermaid_label(node["label"])}"]')

    allowed = {f"N{index}" for index in range(1, len(nodes) + 1)}
    edges: List[Tuple[str, str]] = []
    if generated and isinstance(generated.get("edges"), list):
        for edge in generated["edges"]:
            if (
                isinstance(edge, list)
                and len(edge) == 2
                and edge[0] in allowed
                and edge[1] in allowed
                and edge[0] != edge[1]
            ):
                pair = (edge[0], edge[1])
                if pair not in edges:
                    edges.append(pair)
    if not edges:
        edges = [(f"N{index}", f"N{index + 1}") for index in range(1, len(nodes))]
    lines.extend(f"    {start} --> {end}" for start, end in edges)
    return "\n".join(lines)


def parse_research_paper(pdf_bytes: bytes) -> PaperIndex:
    """Extract clean PDF text + layout metadata and build a verified PaperIndex & PaperBreakdown."""
    if not pdf_bytes:
        raise ValueError("The uploaded PDF is empty.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB ingestion limit.")

    page_texts, layout_meta = _extract_pdf_with_layout(pdf_bytes)
    if not page_texts:
        raise ValueError("No pages could be read from this PDF.")

    whole_text = _clean_ws(" ".join(page_texts))
    if not whole_text or len(whole_text) < 40:
        scanned_bd = build_scanned_pdf_breakdown("Scanned Research PDF", page_count=len(page_texts))
        scanned_node = PaperNode(
            node_id="N1",
            label="Scanned PDF (OCR Required)",
            summary=scanned_bd.what_this_paper_does,
            section="Extraction Notice",
            page=1,
            excerpt=scanned_bd.what_this_paper_does,
        )
        return PaperIndex(
            title=scanned_bd.title,
            mermaid_graph="",
            nodes=[scanned_node],
            node_excerpts={"N1": scanned_node.excerpt},
            full_text_summary=scanned_bd.what_this_paper_does,
            breakdown=scanned_bd,
        )

    sections = _extract_sections(page_texts, layout_meta=layout_meta)
    generated = _ask_gemini_method_graph(whole_text)
    nodes = _valid_generated_nodes(generated, whole_text, sections, page_texts) if generated else None

    diagram_status = "ok"
    diagram_note: Optional[str] = None
    diagram_provenance = "Reconstructed from the paper"

    if nodes is None:
        nodes, diagram_status, diagram_note = _local_method_pipeline(sections, page_texts)
        diagram_provenance = "Reconstructed from the paper" if diagram_status == "ok" else "Conceptual explanation"
    else:
        diagram_provenance = "Reconstructed from the paper"

    paper_nodes = [
        PaperNode(
            node_id=f"N{index}",
            label=node["label"],
            summary=node.get("summary") or None,
            section=node.get("section", "Methodology"),
            page=int(node.get("page", 1)),
            excerpt=node["excerpt"],
        )
        for index, node in enumerate(nodes, start=1)
    ]

    breakdown = build_paper_breakdown(
        page_texts=page_texts,
        sections=sections,
        paper_nodes=paper_nodes,
        reconstructed_from_headings=(diagram_status == "ok"),
        layout_meta=layout_meta,
        diagram_status=diagram_status,
        diagram_note=diagram_note,
        diagram_provenance=diagram_provenance,
    )

    return PaperIndex(
        title=breakdown.title,
        mermaid_graph=_build_mermaid(nodes, generated),
        nodes=paper_nodes,
        node_excerpts={node.node_id: node.excerpt for node in paper_nodes},
        full_text_summary=(
            f"Extracted {len(sections)} sections across {len(page_texts)} pages. "
            f"Methodology pipeline status: {diagram_status}."
        ),
        breakdown=breakdown,
    )


def load_demo_paper_bytes() -> bytes:
    """Read the bundled paper used by offline demos."""
    path = Path(__file__).resolve().parent.parent / "demo_cache" / "sample_paper.pdf"
    return path.read_bytes()
