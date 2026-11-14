"""
Evidence-Linked Research Paper Breakdown Builder (backend/ingestion/paper_breakdown.py).

Turns extracted PDF page texts, layout metadata, and sections into a structured,
page-provenance-verified `PaperBreakdown` report with:
- Furniture/watermark-aware metadata extraction (title, authors, venue, year)
- Strict separation between verbatim paper excerpts, author statements, and plain-language summaries
- Exact 1-based page resolution for every passage (even inside multi-page sections)
- Comparative-only quantitative results (no arbitrary stray numbers turned into charts)
- Real technical glossary terms (never fake section-title glossary rows)
- Paper-specific method pipeline validation and graceful fallback when a method flow cannot be inferred
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from backend.models.schemas import (
    BreakdownField,
    EvidenceRef,
    GlossaryItem,
    MethodologyStep,
    PaperBreakdown,
    PaperNode,
    ResultDataPoint,
)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
INLINE_CITATION_RE = re.compile(r"\s*\[(?:\d+(?:\s*[-,]\s*\d+)*)\]|\s*\((?:[A-Z][A-Za-z-]+(?:\s+et\s+al\.)?,?\s+\d{4}[a-z]?(?:;\s*)?)+\)")
YEAR_VENUE_RE = re.compile(
    r"\b(?:arxiv(?:\s+preprint)?|neurips|iclr|icml|acl|emnlp|naacl|cvpr|iccv|eccv|aaai|kdd|sigir|ieee(?:/cvf)?|acm|nature|science|pnas|transactions|journal|conference|proceedings|workshop)[^.\n]{0,70}?\b(19\d\d|20\d\d)\b"
    r"|\b(19\d\d|20\d\d)\b[^.\n]{0,70}?\b(?:arxiv|neurips|iclr|icml|acl|emnlp|cvpr|iccv|eccv|ieee|acm|conference|journal|workshop|proceedings)\b"
    r"|\barxiv:\s*\d{4}\.\d+(?:v\d+)?\b",
    re.IGNORECASE,
)

FURNITURE_PATTERNS = (
    re.compile(r"open\s+access\s+version", re.IGNORECASE),
    re.compile(r"computer\s+vision\s+foundation", re.IGNORECASE),
    re.compile(r"except\s+for\s+this\s+watermark", re.IGNORECASE),
    re.compile(r"identical\s+to\s+the\s+accepted\s+version", re.IGNORECASE),
    re.compile(r"available\s+on\s+ieee\s+xplore", re.IGNORECASE),
    re.compile(r"authorized\s+licensed\s+use\s+limited\s+to", re.IGNORECASE),
    re.compile(r"personal\s+use\s+is\s+permitted", re.IGNORECASE),
    re.compile(r"restrictions\s+apply", re.IGNORECASE),
    re.compile(r"©\s*\d{4}|copyright\s+\(c\)", re.IGNORECASE),
    re.compile(r"978-1-\d{4}|979-8-\d{4}|issn\s+\d", re.IGNORECASE),
    re.compile(r"preprint\.\s*under\s+review|work\s+in\s+progress|camera[- ]ready", re.IGNORECASE),
    re.compile(r"published\s+as\s+a\s+conference\s+paper\s+at", re.IGNORECASE),
    re.compile(r"^(?:page\s*)?\d{1,3}(?:\s*/\s*\d{1,3})?$", re.IGNORECASE),
)

GENERIC_HEADING_STOPWORDS = {
    "abstract",
    "introduction",
    "background",
    "related work",
    "preliminaries",
    "method",
    "methodology",
    "methods",
    "approach",
    "experiments",
    "experimental setup",
    "evaluation",
    "results",
    "discussion",
    "limitations",
    "conclusion",
    "conclusions",
    "future work",
    "references",
    "acknowledgments",
    "acknowledgements",
    "appendix",
    "table",
    "figure",
}

PROSE_STARTER_RE = re.compile(
    r"^(?:in\s+this\s+(?:paper|work|study)|we\s+(?:propose|present|introduce|study|investigate|evaluate|show|demonstrate)|this\s+(?:paper|study|work)|recently,|large\s+language|deep\s+learning|transformers?\s+have)",
    re.IGNORECASE,
)


def is_pdf_furniture(line: str) -> bool:
    """Return True if a line is a known watermark, copyright stamp, or page header/footer."""
    clean = re.sub(r"\s+", " ", line or "").strip()
    if not clean:
        return True
    if any(pat.search(clean) for pat in FURNITURE_PATTERNS):
        return True
    # Standalone metric header / table column strips like "Abstract BLEU ROUGE"
    tokens = clean.split()
    if 2 <= len(tokens) <= 6 and sum(1 for t in tokens if t.isupper() and len(t) >= 3) >= 2 and len(clean) < 55:
        if any(m in clean.upper() for m in ("BLEU", "ROUGE", "METEOR", "CIDER", "BERT", "FID", "PSNR", "SSIM", "MAP", "AUC")):
            return True
    return False


def _normalize_ws(text: str) -> str:
    # Fix soft hyphenation across line breaks ("retriev-\nal" -> "retrieval")
    dehyphen = re.sub(r"([a-zA-Z])-\s+([a-zA-Z])", r"\1\2", text or "")
    return re.sub(r"\s+", " ", dehyphen).strip()


def _sentences(text: str) -> List[str]:
    norm = _normalize_ws(text)
    if not norm:
        return []
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(norm) if len(s.strip()) > 12]


def _first_n_sentences(text: str, n: int = 2) -> str:
    sents = _sentences(text)
    if not sents:
        return _normalize_ws(text)[:360]
    return " ".join(sents[:n])


def _clean_prose_for_reading(text: str) -> str:
    """Lightly strips inline reference brackets so prose is easier to scan without altering factual meaning."""
    cleaned = INLINE_CITATION_RE.sub("", text or "")
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def find_exact_page_for_excerpt(excerpt: str, page_texts: List[str], default_page: int = 1) -> int:
    """
    Resolve the exact 1-based page number where `excerpt` appears.
    Handles line wraps, spacing differences, and multi-page sections via substring + sliding word anchors.
    """
    if not excerpt or not page_texts:
        return default_page

    norm_excerpt = _normalize_ws(excerpt).lower()
    if not norm_excerpt:
        return default_page

    norm_pages = [_normalize_ws(p).lower() for p in page_texts]

    # Try exact prefix / middle probe matches first
    probes = [norm_excerpt[:75], norm_excerpt[:40]]
    if len(norm_excerpt) > 80:
        probes.append(norm_excerpt[30:95])
    for probe in probes:
        probe = probe.strip()
        if len(probe) < 15:
            continue
        for idx, ptext in enumerate(norm_pages, start=1):
            if probe in ptext:
                return idx

    # Word n-gram window match (handles minor ligature / punctuation differences)
    words = [w for w in re.findall(r"[a-z0-9]+", norm_excerpt) if len(w) > 1]
    if len(words) >= 5:
        for idx, ptext in enumerate(norm_pages, start=1):
            hits = 0
            windows = [" ".join(words[i : i + 5]) for i in range(0, min(len(words) - 4, 15), 3)]
            page_words_str = " ".join(re.findall(r"[a-z0-9]+", ptext))
            for w in windows:
                if w in page_words_str:
                    hits += 1
            if hits >= 1:
                return idx

    return default_page


def _looks_like_author_line(line: str) -> bool:
    clean = re.sub(r"\s+", " ", line or "").strip()
    if not clean or is_pdf_furniture(clean):
        return False
    if YEAR_VENUE_RE.search(clean):
        return False
    low = clean.lower()
    if PROSE_STARTER_RE.search(clean) or len(clean.split()) > 28:
        return False
    if any(bad in low for bad in ("offline demo paper", "synthetic technical study", "vivavoce", "figure ", "table ")):
        return False
    if clean.endswith(".") and not any(tok in low for tok in ("university", "institute", "dept", "inc.", "corp.", "lab")):
        return False
    # Affiliation keywords or name/email list
    has_affil = any(
        tok in low
        for tok in (
            "university",
            "institute",
            "department",
            "laboratory",
            "research",
            "college",
            "school of",
            "google",
            "meta",
            "microsoft",
            "nvidia",
            "adobe",
            "deepmind",
            "@",
        )
    )
    if has_affil:
        return True
    # Person names: multiple capitalized words with optional superscript footnote markers (e.g. "Maya Patel1, Liam Chen2")
    cleaned_names = re.sub(r"(?<=[a-zA-Z])(?:\d+|[*†‡§])(?=\s|,|$)", "", clean)
    cap_words = re.findall(r"\b[A-Z][a-zA-Z'-]{1,20}(?:\s+[A-Z]\.?)?\s+[A-Z][a-zA-Z'-]{1,20}\b", cleaned_names)
    if cap_words and ("," in clean or " and " in low or len(clean.split()) <= 10):
        return True
    return False


def _extract_metadata(
    page_texts: List[str],
    layout_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Extracts title, authors & affiliations, venue/year, and clean top-of-page-1 inspection excerpt
    using font-size/bbox layout metadata when available and strict furniture filtering always.
    """
    venue = "Not found in the paper"
    if layout_meta and layout_meta.get("venue_hints"):
        venue = "; ".join(layout_meta["venue_hints"][:2])[:180]

    # Also scan clean first 2 pages for venue/year if not found in watermark/header hints
    if venue == "Not found in the paper" and page_texts:
        top_text = "\n".join(page_texts[:2])[:4000]
        for line in top_text.splitlines():
            clean_line = _normalize_ws(line)
            if not clean_line or len(clean_line) > 160:
                continue
            if YEAR_VENUE_RE.search(clean_line) and not clean_line.lower().startswith("references"):
                venue = clean_line[:160]
                break
        if venue == "Not found in the paper":
            m = YEAR_VENUE_RE.search(_normalize_ws(top_text))
            if m:
                venue = m.group(0).strip()[:160]

    # Path 1: Font-size & bounding-box metadata from PyMuPDF Page 1
    title = ""
    title_status = "verified"
    authors = "Could not identify reliably"
    authors_status = "uncertain"
    title_block_excerpt = ""

    if layout_meta and layout_meta.get("page1_lines"):
        p1_lines: List[Dict[str, Any]] = layout_meta["page1_lines"]
        body_font = float(layout_meta.get("body_font_size") or 10.0)
        abs_y0 = layout_meta.get("abstract_y0")

        # Keep clean horizontal lines above Abstract/Introduction (or top 55% of page 1)
        page1_height = float(layout_meta.get("page1_height") or 800.0)
        cutoff_y = float(abs_y0) if abs_y0 is not None else page1_height * 0.55

        top_lines = [
            ln
            for ln in p1_lines
            if ln["y0"] < cutoff_y - 2
            and not is_pdf_furniture(ln["text"])
            and not ln.get("is_vertical", False)
        ]

        # Build concise inspection block from top of Page 1
        title_block_excerpt = "\n".join(ln["text"] for ln in top_lines[:10]).strip()[:650]

        # Exclude venue/tag lines when detecting largest-font title lines
        title_candidates = [
            ln
            for ln in top_lines
            if not YEAR_VENUE_RE.search(ln["text"])
            and not ln["text"].lower().startswith(("abstract", "1 introduction", "1. introduction", "keywords"))
            and len(ln["text"]) >= 3
        ]

        if title_candidates:
            max_font = max(ln["size"] for ln in title_candidates)
            if max_font >= body_font * 1.15:
                title_lines = [ln for ln in title_candidates if ln["size"] >= max_font * 0.90]
                # Keep contiguous vertical lines (avoid picking an unrelated big drop-cap later)
                if title_lines:
                    grouped_title = [title_lines[0]]
                    for nxt in title_lines[1:]:
                        if nxt["y0"] - grouped_title[-1]["y1"] <= grouped_title[-1]["size"] * 1.8:
                            grouped_title.append(nxt)
                    title = " ".join(ln["text"] for ln in grouped_title).strip()
                    title_bottom_y = grouped_title[-1]["y1"]
                else:
                    title_bottom_y = 0.0
            else:
                # Uniform font fallback on top lines
                first_non_prose = [ln for ln in title_candidates if not PROSE_STARTER_RE.search(ln["text"])]
                if first_non_prose:
                    title = first_non_prose[0]["text"]
                    title_bottom_y = first_non_prose[0]["y1"]
                    title_status = "uncertain"
                else:
                    title_bottom_y = 0.0
        else:
            title_bottom_y = 0.0

        # Author block: strictly AFTER title_bottom_y and BEFORE abstract cutoff_y
        between_lines = [
            ln["text"]
            for ln in top_lines
            if ln["y0"] > title_bottom_y - 1 and ln["y0"] < cutoff_y - 2
        ]
        # Capture synthetic subtitle/tag as venue if not set
        for ln_txt in between_lines:
            if venue == "Not found in the paper" and any(
                k in ln_txt.lower() for k in ("preprint", "technical study", "technical report", "demo paper", "working paper", "draft")
            ):
                venue = ln_txt[:160]

        author_lines = [ln for ln in between_lines if _looks_like_author_line(ln)]
        if author_lines:
            authors = " · ".join(author_lines[:4])[:260]
            authors_status = "identified"
        elif not between_lines or abs_y0 is None:
            authors = "Could not identify reliably"
            authors_status = "uncertain"
        else:
            # Explicit lines exist above abstract but none looked like personal authors (e.g. anonymous submission / tagline)
            authors = "Not found in the paper"
            authors_status = "not_found"

    # Path 2: Clean text-only fallback if layout metadata wasn't provided
    if not title and page_texts:
        raw_lines = [
            _normalize_ws(line)
            for line in page_texts[0].splitlines()
            if _normalize_ws(line) and not is_pdf_furniture(line)
        ]
        title_block_excerpt = title_block_excerpt or "\n".join(raw_lines[:8])[:650]
        header_lines: List[str] = []
        for line in raw_lines[:12]:
            low = line.lower()
            if low.startswith(("abstract", "1 introduction", "1. introduction", "introduction")):
                break
            header_lines.append(line)

        clean_header = [
            ln for ln in header_lines if not YEAR_VENUE_RE.search(ln) and not PROSE_STARTER_RE.search(ln)
        ]
        if clean_header:
            title = clean_header[0][:200]
            title_status = "uncertain"
            rest = clean_header[1:]
            author_lines = [ln for ln in rest if _looks_like_author_line(ln)]
            if author_lines:
                authors = " · ".join(author_lines[:4])[:260]
                authors_status = "identified"
            else:
                authors = "Could not identify reliably"
                authors_status = "uncertain"

    if not title or is_pdf_furniture(title) or PROSE_STARTER_RE.search(title):
        title = "Could not identify paper title reliably"
        title_status = "uncertain"

    return {
        "title": title[:220],
        "title_status": title_status,
        "authors": authors,
        "authors_status": authors_status,
        "venue": venue,
        "title_block_excerpt": title_block_excerpt or None,
    }


def _match_section(
    sections: List[Dict[str, Any]],
    keywords: Tuple[str, ...],
) -> Optional[Dict[str, Any]]:
    for sec in sections:
        title_low = str(sec.get("title", "")).lower()
        if any(k in title_low for k in keywords):
            return sec
    return None


def _search_sentences_by_keywords(
    sections: List[Dict[str, Any]],
    page_texts: List[str],
    keywords: Tuple[str, ...],
) -> Optional[Tuple[str, int, str]]:
    """Finds 2 adjacent sentences matching keywords and resolves the EXACT 1-based page."""
    for sec in sections:
        sents = _sentences(sec.get("text", ""))
        for i, s in enumerate(sents):
            low = s.lower()
            if any(k in low for k in keywords):
                pair = " ".join(sents[i : min(len(sents), i + 2)])
                exact_page = find_exact_page_for_excerpt(
                    pair, page_texts, default_page=int(sec.get("page_start", 1))
                )
                return (pair, exact_page, str(sec.get("title", "Paper")))
    return None


def _build_field(
    sections: List[Dict[str, Any]],
    page_texts: List[str],
    section_keywords: Tuple[str, ...],
    sentence_keywords: Tuple[str, ...],
    plain_override: Optional[str] = None,
) -> BreakdownField:
    sec = _match_section(sections, section_keywords)
    if sec and sec.get("text"):
        excerpt = _first_n_sentences(sec["text"], 2)
        summary = _clean_prose_for_reading(_first_n_sentences(sec["text"], 3))
        exact_page = find_exact_page_for_excerpt(
            excerpt, page_texts, default_page=int(sec.get("page_start", 1))
        )
        sec_title = str(sec.get("title", "Section"))
        return BreakdownField(
            content=summary or excerpt,
            plain_language=plain_override,
            source_type="author_claim",
            page=exact_page,
            section=sec_title,
            excerpt=excerpt,
            found=True,
        )

    hit = _search_sentences_by_keywords(sections, page_texts, sentence_keywords)
    if hit:
        excerpt, exact_page, sec_title = hit
        return BreakdownField(
            content=_clean_prose_for_reading(excerpt),
            plain_language=plain_override,
            source_type="author_claim",
            page=exact_page,
            section=sec_title,
            excerpt=excerpt,
            found=True,
        )

    return BreakdownField(
        content="Not found in the paper",
        plain_language=None,
        source_type="author_claim",
        page=None,
        section=None,
        excerpt=None,
        found=False,
    )


# Explicit paired-comparison regexes: avoids charting isolated random digits near words like "accuracy"
COMPARISON_PATTERNS = (
    # "accuracy of 88.4% compared to 79.2%" / "accuracy: 88.4% vs 79.2%"
    re.compile(
        r"\b(?P<metric>accuracy|top-1|top-5|f1(?:-score)?|precision|recall(?:@\d+)?|auc|bleu|rouge(?:-[12l])?|map|pass@1|pass@k|iou|miou|psnr|wer|latency)\b"
        r"[^.]{0,55}?"
        r"(?P<val1>\d{1,3}(?:\.\d+)?)\s*(?P<unit1>%|ms|s|db)?\s*"
        r"(?:vs\.?|versus|compared\s+(?:to|with)|over|against)\s*"
        r"(?:[A-Za-z0-9 _'-]{0,25}?\s)?(?P<val2>\d{1,3}(?:\.\d+)?)\s*(?P<unit2>%|ms|s|db)?",
        re.IGNORECASE,
    ),
    # "64.8% accuracy compared to 56.2%" / "31.2 BLEU vs 28.4"
    re.compile(
        r"(?P<val1>\d{1,3}(?:\.\d+)?)\s*(?P<unit1>%|ms|s|db)?\s+"
        r"(?P<metric>accuracy|top-1|top-5|f1(?:-score)?|precision|recall(?:@\d+)?|auc|bleu|rouge(?:-[12l])?|map|pass@1|pass@k|iou|miou|psnr|wer|latency)\b"
        r"[^.]{0,35}?"
        r"(?:vs\.?|versus|compared\s+(?:to|with)|over|against)\s*"
        r"(?:the\s+|our\s+)?(?P<val2>\d{1,3}(?:\.\d+)?)\s*(?P<unit2>%|ms|s|db)?",
        re.IGNORECASE,
    ),
    # "improves BLEU from 28.4 to 31.2"
    re.compile(
        r"\b(?P<metric>accuracy|top-1|top-5|f1(?:-score)?|precision|recall|bleu|rouge(?:-[12l])?|map|psnr|wer|latency)\b"
        r"[^.]{0,40}?\bfrom\s+(?P<base>\d{1,3}(?:\.\d+)?)\s*(?P<unit1>%|ms|s|db)?\s*"
        r"\bto\s+(?P<prop>\d{1,3}(?:\.\d+)?)\s*(?P<unit2>%|ms|s|db)?",
        re.IGNORECASE,
    ),
)


def _extract_quantitative_results(
    sections: List[Dict[str, Any]],
    page_texts: List[str],
) -> List[ResultDataPoint]:
    """
    Strictly extracts comparable quantitative results ONLY when metric, values, units,
    and comparison (proposed vs. baseline/prior) are explicitly clear in the same passage.
    Never turns isolated numbers into misleading charts.
    """
    points: List[ResultDataPoint] = []
    seen_keys: set[str] = set()

    for sec in sections:
        sec_low = str(sec.get("title", "")).lower()
        if sec_low in ("references", "related work", "acknowledgments", "acknowledgements"):
            continue
        for sent in _sentences(sec.get("text", "")):
            # Patterns A & B: val1 vs val2
            for pat in COMPARISON_PATTERNS[:2]:
                for m in pat.finditer(sent):
                    metric = m.group("metric").upper()
                    try:
                        v1 = float(m.group("val1"))
                        v2 = float(m.group("val2"))
                    except ValueError:
                        continue
                    unit = (m.group("unit1") or m.group("unit2") or "").strip()
                    if unit == "%" and (v1 > 100 or v2 > 100):
                        continue
                    if v1 == v2:
                        continue
                    key = f"{metric}:{v1}:{v2}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    exact_page = find_exact_page_for_excerpt(
                        sent, page_texts, default_page=int(sec.get("page_start", 1))
                    )
                    points.append(
                        ResultDataPoint(
                            metric=metric,
                            comparison_context=f"{sec.get('title', 'Results')} comparison",
                            baseline_label="Baseline / Comparison",
                            baseline_value=v2,
                            proposed_label="Reported / Proposed",
                            proposed_value=v1,
                            unit=unit,
                            page=exact_page,
                            excerpt=sent,
                        )
                    )
                    if len(points) >= 5:
                        return points

            # Pattern C: from baseline to proposed
            for m in COMPARISON_PATTERNS[2].finditer(sent):
                metric = m.group("metric").upper()
                try:
                    base_v = float(m.group("base"))
                    prop_v = float(m.group("prop"))
                except ValueError:
                    continue
                unit = (m.group("unit2") or m.group("unit1") or "").strip()
                if unit == "%" and (base_v > 100 or prop_v > 100):
                    continue
                if base_v == prop_v:
                    continue
                key = f"{metric}:{prop_v}:{base_v}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                exact_page = find_exact_page_for_excerpt(
                    sent, page_texts, default_page=int(sec.get("page_start", 1))
                )
                points.append(
                    ResultDataPoint(
                        metric=metric,
                        comparison_context=f"Measured change in {sec.get('title', 'Results')}",
                        baseline_label="Before / Baseline",
                        baseline_value=base_v,
                        proposed_label="After / Proposed",
                        proposed_value=prop_v,
                        unit=unit,
                        page=exact_page,
                        excerpt=sent,
                    )
                )
                if len(points) >= 5:
                    return points

    return points


def _extract_glossary(
    sections: List[Dict[str, Any]],
    page_texts: List[str],
) -> List[GlossaryItem]:
    """
    Extracts real technical terms and acronyms explained in context.
    Never converts PDF section headings into fake glossary terms.
    """
    glossary: List[GlossaryItem] = []
    seen: set[str] = set()

    # Pattern 1: Explicit acronym definitions e.g. "Retrieval-Augmented Generation (RAG)"
    acronym_re = re.compile(r"\b([A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Za-z0-9-]{2,}){1,5})\s+\(([A-Z]{2,8})\)")
    for sec in sections:
        if str(sec.get("title", "")).lower() == "references":
            continue
        for sent in _sentences(sec.get("text", "")):
            for m in acronym_re.finditer(sent):
                full_term, short = m.group(1).strip(), m.group(2).strip()
                if short.lower() in GENERIC_HEADING_STOPWORDS or short in seen:
                    continue
                if full_term.lower().startswith(("figure", "table", "section", "equation")):
                    continue
                seen.add(short)
                exact_page = find_exact_page_for_excerpt(
                    sent, page_texts, default_page=int(sec.get("page_start", 1))
                )
                glossary.append(
                    GlossaryItem(
                        term=f"{short} — {full_term}",
                        definition=_clean_prose_for_reading(sent),
                        source_type="author_defined",
                        page=exact_page,
                        excerpt=sent,
                    )
                )
                if len(glossary) >= 6:
                    return glossary

    # Pattern 2: Definitional sentences ("A retrieval graph represents...", "... refers to ...", "... defined as ...")
    def_re = re.compile(
        r"^(?:A|An|The)?\s*([A-Z]?[a-zA-Z0-9-]{3,}(?:\s+[a-zA-Z0-9-]{2,}){0,3})\s+"
        r"(?:represents|refers to|is defined as|denotes|is a\s+[a-z]+)\b"
    )
    for sec in sections:
        if str(sec.get("title", "")).lower() == "references":
            continue
        for sent in _sentences(sec.get("text", "")):
            m = def_re.match(sent)
            if not m:
                continue
            cand = m.group(1).strip()
            low = cand.lower()
            if (
                low in GENERIC_HEADING_STOPWORDS
                or low in seen
                or any(stop in low for stop in ("prototype", "this study", "this paper", "small set", "section"))
                or len(cand) < 4
            ):
                continue
            seen.add(low)
            exact_page = find_exact_page_for_excerpt(
                sent, page_texts, default_page=int(sec.get("page_start", 1))
            )
            glossary.append(
                GlossaryItem(
                    term=cand[0].upper() + cand[1:],
                    definition=_clean_prose_for_reading(sent),
                    source_type="author_defined",
                    page=exact_page,
                    excerpt=sent,
                )
            )
            if len(glossary) >= 6:
                return glossary

    return glossary


def _synthesize_breakdown_with_gemini(
    metadata: Dict[str, Any],
    page_texts: List[str],
    paper_nodes: List[PaperNode],
) -> Optional[Dict[str, Any]]:
    """
    Optional single-call Gemini synthesis when GEMINI_API_KEY is configured.
    Strictly instructs the model to write genuine plain-language explanations
    separate from verbatim source quotes. Returns None on any error/absence.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

    numbered_pages = "\n\n".join(
        f"[PAGE {idx}]\n{txt[:4500]}" for idx, txt in enumerate(page_texts[:10], start=1) if txt.strip()
    )[:26000]
    if not numbered_pages.strip():
        return None

    prompt = (
        "You are an academic research explainer for university students. Return strictly valid JSON only.\n"
        "Analyze the numbered PDF pages below. Never invent facts, authors, numbers, or claims not in the pages.\n"
        "For plain_language fields, explain simply in clear everyday English without copying dense jargon verbatim.\n"
        "For quote fields, copy an exact short verbatim snippet (1-2 sentences) from the text.\n"
        "Return JSON with exact keys:\n"
        "{\n"
        '  "title": "clean paper title without watermarks",\n'
        '  "authors_and_affiliations": "authors + affiliations or Not found in the paper",\n'
        '  "venue_and_year": "venue and year or Not found in the paper",\n'
        '  "what_this_paper_does_plain": "2 concise plain-language sentences explaining what the paper builds/shows",\n'
        '  "abstract_plain": "2 plain-language sentences summarizing the abstract",\n'
        '  "problem_plain": "1-2 plain sentences on problem & why it matters",\n'
        '  "objective_plain": "1-2 plain sentences on the research question/goal",\n'
        '  "background_plain": "1-2 plain sentences on prior work & gap",\n'
        '  "method_plain": "2 plain sentences explaining the proposed method overall",\n'
        '  "data_setup_plain": "1-2 plain sentences on datasets, experiments, and metrics",\n'
        '  "results_plain": "1-2 plain sentences on main results and what they mean",\n'
        '  "contributions_plain": "1-2 plain sentences on what is new",\n'
        '  "limitations_plain": "1-2 plain sentences on limitations & assumptions",\n'
        '  "future_work_plain": "1-2 plain sentences on practical implications & future directions",\n'
        '  "glossary": [{"term": "...", "definition": "plain-language 1 sentence definition", "quote": "exact snippet from paper"}]\n'
        "}\n\n"
        f"CURRENT EXTRACTED METADATA HINT: title='{metadata.get('title')}', authors='{metadata.get('authors')}', venue='{metadata.get('venue')}'\n\n"
        + numbered_pages
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
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=22) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError):
        return None


def build_paper_breakdown(
    page_texts: List[str],
    sections: List[Dict[str, Any]],
    paper_nodes: List[PaperNode],
    reconstructed_from_headings: bool = True,
    layout_meta: Optional[Dict[str, Any]] = None,
    diagram_status: str = "ok",
    diagram_note: Optional[str] = None,
    diagram_provenance: str = "Reconstructed from the paper",
) -> PaperBreakdown:
    """Builds a complete, evidence-linked, honest `PaperBreakdown` from extracted PDF pages and sections."""
    meta = _extract_metadata(page_texts, layout_meta=layout_meta)

    # Ensure every PaperNode carries its exact verified 1-based page
    for node in paper_nodes:
        node.page = find_exact_page_for_excerpt(node.excerpt, page_texts, default_page=node.page or 1)

    llm_synth = _synthesize_breakdown_with_gemini(meta, page_texts, paper_nodes)
    full_norm = _normalize_ws(" ".join(page_texts)).lower()

    title = meta["title"]
    title_status = meta["title_status"]
    authors = meta["authors"]
    authors_status = meta["authors_status"]
    venue = meta["venue"]

    # If LLM clarified uncertain title/authors AND they actually match text on page 1, adopt cautiously
    p1_norm = _normalize_ws(page_texts[0]).lower() if page_texts else ""
    if llm_synth:
        cand_title = str(llm_synth.get("title") or "").strip()
        if cand_title and not is_pdf_furniture(cand_title) and cand_title.lower()[:25] in p1_norm:
            title = cand_title[:220]
            title_status = "verified"

        cand_auth = str(llm_synth.get("authors_and_affiliations") or "").strip()
        if (
            authors_status != "identified"
            and cand_auth
            and "not found" not in cand_auth.lower()
            and not PROSE_STARTER_RE.search(cand_auth)
            and any(tok.lower() in p1_norm for tok in cand_auth.replace(",", " ").split()[:3] if len(tok) > 2)
        ):
            authors = cand_auth[:260]
            authors_status = "identified"

        cand_venue = str(llm_synth.get("venue_and_year") or "").strip()
        if venue == "Not found in the paper" and cand_venue and "not found" not in cand_venue.lower():
            if any(y in full_norm for y in re.findall(r"\b(?:19|20)\d\d\b", cand_venue) or [cand_venue[:12].lower()]):
                venue = cand_venue[:180]

    def llm_plain(key: str) -> Optional[str]:
        if not llm_synth:
            return None
        val = str(llm_synth.get(key) or "").strip()
        return val if val and "not found" not in val.lower() else None

    abstract_field = _build_field(
        sections,
        page_texts,
        ("abstract",),
        ("we propose", "this paper", "we present", "we introduce", "this sample study", "in this work"),
        plain_override=llm_plain("abstract_plain"),
    )
    problem_field = _build_field(
        sections,
        page_texts,
        ("introduction", "problem", "motivation"),
        ("however", "challenge", "bottleneck", "limitation", "problem", "difficult", "suffer", "often ask"),
        plain_override=llm_plain("problem_plain"),
    )
    objective_field = _build_field(
        sections,
        page_texts,
        ("objective", "research question", "introduction"),
        ("we aim", "our goal", "research question", "we investigate", "we examine", "examines whether", "we address", "to solve"),
        plain_override=llm_plain("objective_plain"),
    )
    background_field = _build_field(
        sections,
        page_texts,
        ("background", "related work", "prior work", "preliminaries"),
        ("prior work", "existing", "traditionally", "previous", "baseline", "retrieval graph"),
        plain_override=llm_plain("background_plain"),
    )
    method_field = _build_field(
        sections,
        page_texts,
        ("method", "methodology", "approach", "architecture", "framework", "proposed"),
        ("pipeline", "architecture", "algorithm", "module", "we design", "prototype extracts", "stage", "divides"),
        plain_override=llm_plain("method_plain"),
    )
    data_field = _build_field(
        sections,
        page_texts,
        ("data", "dataset", "experiment", "evaluation", "setup", "benchmark"),
        ("dataset", "benchmark", "evaluated on", "synthetic papers", "metric", "hyperparameter", "training", "test"),
        plain_override=llm_plain("data_setup_plain"),
    )
    results_field = _build_field(
        sections,
        page_texts,
        ("result", "finding", "performance", "evaluation"),
        ("outperform", "achieve", "accuracy", "improvement", "produced a readable", "prevented unsupported", "demonstrate"),
        plain_override=llm_plain("results_plain"),
    )
    contributions_field = _build_field(
        sections,
        page_texts,
        ("contribution", "abstract", "introduction"),
        ("our contributions", "we contribute", "first to", "novel", "we propose", "compact retrieval graph"),
        plain_override=llm_plain("contributions_plain"),
    )
    limitations_field = _build_field(
        sections,
        page_texts,
        ("limitation", "discussion", "threat", "constraint"),
        ("limitation", "depends on", "does not perform", "mistake", "assumption", "constraint", "fail", "drawback"),
        plain_override=llm_plain("limitations_plain"),
    )
    future_field = _build_field(
        sections,
        page_texts,
        ("future work", "conclusion", "implication", "discussion"),
        ("future work", "implication", "conclude", "extend", "direction", "should compare"),
        plain_override=llm_plain("future_work_plain"),
    )

    # Step-by-step methodology grounded directly in validated method pipeline nodes
    steps: List[MethodologyStep] = []
    for idx, node in enumerate(paper_nodes, start=1):
        steps.append(
            MethodologyStep(
                step_number=idx,
                node_id=node.node_id,
                title=node.label,
                description=_clean_prose_for_reading(node.excerpt),
                plain_language=node.summary,
                source_type="author_claim",
                page=node.page,
                section=node.section or f"Stage {idx}",
                excerpt=node.excerpt,
            )
        )

    # 4-stage Problem -> Approach -> Evidence -> Conclusion interactive story map
    n0 = paper_nodes[0] if paper_nodes else None
    n_mid = paper_nodes[len(paper_nodes) // 2] if paper_nodes else n0
    n_last = paper_nodes[-1] if paper_nodes else n0

    story_map: List[EvidenceRef] = [
        EvidenceRef(
            id="SM1",
            label="Problem",
            claim_or_insight=(
                problem_field.plain_language
                or (problem_field.content if problem_field.found else (n0.excerpt if n0 else "Problem statement not isolated clearly."))
            ),
            source_type="app_interpretation" if problem_field.plain_language else "author_claim",
            excerpt=problem_field.excerpt or (n0.excerpt if n0 else ""),
            page=problem_field.page or (n0.page if n0 else 1),
            section=problem_field.section or "Introduction",
        ),
        EvidenceRef(
            id="SM2",
            label="Approach",
            claim_or_insight=(
                method_field.plain_language
                or (method_field.content if method_field.found else (n_mid.excerpt if n_mid else "See proposed method section."))
            ),
            source_type="app_interpretation" if method_field.plain_language else "author_claim",
            excerpt=method_field.excerpt or (n_mid.excerpt if n_mid else ""),
            page=method_field.page or (n_mid.page if n_mid else 1),
            section=method_field.section or "Method",
        ),
        EvidenceRef(
            id="SM3",
            label="Evidence",
            claim_or_insight=(
                results_field.plain_language
                or (results_field.content if results_field.found else "See data & evaluation sections.")
            ),
            source_type="app_interpretation" if results_field.plain_language else ("author_claim" if results_field.found else "app_interpretation"),
            excerpt=results_field.excerpt or (data_field.excerpt or (n_last.excerpt if n_last else "")),
            page=results_field.page or (data_field.page or (n_last.page if n_last else 1)),
            section=results_field.section or "Results & Evaluation",
        ),
        EvidenceRef(
            id="SM4",
            label="Conclusion",
            claim_or_insight=(
                future_field.plain_language
                or (future_field.content if future_field.found else (n_last.excerpt if n_last else "See conclusion."))
            ),
            source_type="app_interpretation" if future_field.plain_language else "author_claim",
            excerpt=future_field.excerpt or (n_last.excerpt if n_last else ""),
            page=future_field.page or (n_last.page if n_last else len(page_texts)),
            section=future_field.section or "Conclusion",
        ),
    ]

    # Key takeaways deduplicated from distinct sections/findings
    key_takeaways: List[EvidenceRef] = []
    seen_takeaway_excerpts: set[str] = set()
    takeaway_sources = [
        ("Core Objective", objective_field),
        ("Proposed Method", method_field),
        ("Main Finding", results_field),
        ("Key Limitation", limitations_field),
    ]
    for label, field in takeaway_sources:
        if field.found and field.excerpt and field.excerpt not in seen_takeaway_excerpts:
            seen_takeaway_excerpts.add(field.excerpt)
            key_takeaways.append(
                EvidenceRef(
                    id=f"KT{len(key_takeaways) + 1}",
                    label=label,
                    claim_or_insight=field.plain_language or field.content,
                    source_type="app_interpretation" if field.plain_language else "author_claim",
                    excerpt=field.excerpt,
                    page=field.page or 1,
                    section=field.section or label,
                )
            )

    # Section & page navigation index (clean, page-provenance checked)
    sections_index: List[EvidenceRef] = []
    for idx, sec in enumerate(sections[:16], start=1):
        sec_excerpt = _first_n_sentences(sec.get("text", ""), 2)
        if not sec_excerpt:
            continue
        exact_page = find_exact_page_for_excerpt(
            sec_excerpt, page_texts, default_page=int(sec.get("page_start", 1))
        )
        sections_index.append(
            EvidenceRef(
                id=f"SEC{idx}",
                label=str(sec.get("title", f"Section {idx}")),
                claim_or_insight=_clean_prose_for_reading(_first_n_sentences(sec.get("text", ""), 1)),
                source_type="author_claim",
                excerpt=sec_excerpt,
                page=exact_page,
                section=str(sec.get("title", f"Section {idx}")),
            )
        )

    what_it_does = (
        abstract_field.content
        if abstract_field.found
        else (problem_field.content if problem_field.found else (paper_nodes[0].excerpt if paper_nodes else "Analyzes the uploaded research paper."))
    )
    what_it_does_plain = llm_plain("what_this_paper_does_plain") or abstract_field.plain_language

    quant_results = _extract_quantitative_results(sections, page_texts)
    results_summary_note: Optional[str] = None
    if not quant_results:
        if results_field.found:
            results_summary_note = (
                f"No side-by-side numerical comparison table with units was detected for charting. "
                f"Cited summary (p. {results_field.page}): {results_field.content}"
            )
        else:
            results_summary_note = "No clear quantitative comparison table or paired benchmark metrics were extracted from the paper text."

    glossary = _extract_glossary(sections, page_texts)
    if llm_synth and isinstance(llm_synth.get("glossary"), list):
        llm_glossary: List[GlossaryItem] = []
        seen_terms: set[str] = set()
        for item in llm_synth["glossary"][:6]:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term") or "").strip()
            defn = str(item.get("definition") or "").strip()
            quote = str(item.get("quote") or "").strip()
            if (
                term
                and defn
                and term.lower() not in GENERIC_HEADING_STOPWORDS
                and term.lower() not in seen_terms
                and quote
                and _normalize_ws(quote)[:35].lower() in full_norm
            ):
                seen_terms.add(term.lower())
                llm_glossary.append(
                    GlossaryItem(
                        term=term,
                        definition=defn,
                        source_type="app_interpretation",
                        page=find_exact_page_for_excerpt(quote, page_texts, default_page=1),
                        excerpt=quote,
                    )
                )
        if llm_glossary:
            glossary = llm_glossary

    return PaperBreakdown(
        title=title,
        title_status=title_status,
        authors_and_affiliations=authors,
        authors_status=authors_status,
        venue_and_year=venue,
        title_block_excerpt=meta["title_block_excerpt"],
        what_this_paper_does=what_it_does,
        what_this_paper_does_plain=what_it_does_plain,
        extraction_status="ok",
        extraction_warning=None,
        page_count=max(1, len(page_texts)),
        methodology_diagram_status=diagram_status if diagram_status in ("ok", "fallback") else "ok",
        methodology_diagram_note=diagram_note,
        diagram_provenance=(
            diagram_provenance
            if diagram_provenance in ("Reconstructed from the paper", "Conceptual explanation")
            else ("Reconstructed from the paper" if reconstructed_from_headings else "Conceptual explanation")
        ),
        story_map_provenance="Conceptual explanation",
        abstract_summary=abstract_field,
        problem_and_significance=problem_field,
        research_objective=objective_field,
        background_and_prior_work=background_field,
        proposed_method=method_field,
        step_by_step_methodology=steps,
        data_setup_and_metrics=data_field,
        main_results=results_field,
        results_summary_note=results_summary_note,
        contributions=contributions_field,
        limitations_and_assumptions=limitations_field,
        implications_and_future_work=future_field,
        key_takeaways=key_takeaways,
        story_map=story_map,
        sections_index=sections_index,
        quantitative_results=quant_results,
        glossary=glossary,
        viva_questions=[],
    )


def build_scanned_pdf_breakdown(filename: str, page_count: int = 1) -> PaperBreakdown:
    """Graceful, honest breakdown when a PDF is scanned/image-only with no selectable text."""
    notice = (
        "No selectable text could be extracted from this PDF. It appears to be a scanned or image-only document. "
        "Run OCR (for example ocrmypdf or Adobe OCR) and re-upload, or load the Demo Paper to inspect the explorer."
    )
    not_found = BreakdownField(content="Not found in the paper (scanned or image-only PDF)", found=False)
    return PaperBreakdown(
        title=filename.replace(".pdf", "").replace("_", " ").strip() or "Scanned PDF Document",
        title_status="uncertain",
        authors_and_affiliations="Not found in the paper",
        authors_status="not_found",
        venue_and_year="Not found in the paper",
        title_block_excerpt=None,
        what_this_paper_does=notice,
        what_this_paper_does_plain=notice,
        extraction_status="scanned_or_empty",
        extraction_warning=notice,
        page_count=max(1, page_count),
        methodology_diagram_status="fallback",
        methodology_diagram_note="Text extraction failed on this image-only PDF; no method stages could be reconstructed.",
        diagram_provenance="Conceptual explanation",
        story_map_provenance="Conceptual explanation",
        abstract_summary=not_found,
        problem_and_significance=not_found,
        research_objective=not_found,
        background_and_prior_work=not_found,
        proposed_method=not_found,
        step_by_step_methodology=[],
        data_setup_and_metrics=not_found,
        main_results=not_found,
        results_summary_note=notice,
        contributions=not_found,
        limitations_and_assumptions=not_found,
        implications_and_future_work=not_found,
        key_takeaways=[],
        story_map=[],
        sections_index=[],
        quantitative_results=[],
        glossary=[],
        viva_questions=[],
    )
