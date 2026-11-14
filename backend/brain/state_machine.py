"""
Examiner ReAct State Machine & Adaptive L1-L4 Depth Loop (backend/brain/state_machine.py).
Owner: Member 1 (Nishit - Team Lead & AI Brain Engineer)

Implements:
- In-memory `SESSIONS` store
- `SessionManager` class + module-level `start_session()` and `process_turn()`
- ReAct reasoning loop (DrillDown, Probe, Hint, TriggerCodeChallenge)
- Revised Bloom's Taxonomy transitions (L1 Recall -> L2 Comprehension -> L3 Trade-offs -> L4 Mutation/IDE Fix)
- Gemini 2.5 Flash strict JSON generation with deterministic AST/Paper fallback for offline hackathon resilience
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Literal, Optional

from backend.brain.prompts import (
    CHALLENGE_GEN_PROMPT,
    PAPER_EXAMINER_PROMPT,
    REPO_EXAMINER_PROMPT,
    build_paper_turn_user_prompt,
    build_repo_turn_user_prompt,
)
from backend.models.schemas import (
    ASTFunctionSymbol,
    CodeHighlight,
    CodingChallenge,
    LeetCodeProfileSummary,
    PaperIndex,
    PaperNode,
    RepoIndex,
    RunCodeResponse,
    TurnResponse,
    VerdictType,
)


# ============================================================================
# ASR ARTIFACT & FILLER STRIPPING (Koenecke et al., PNAS 2020)
# ============================================================================

ASR_FILLER_PATTERNS = [
    r"\b(um+|uh+|erm+|ah+|hmm+)\b",
    r"\b(like|you know|i mean|sort of|kind of|basically|actually|literally)\b",
    r"\b(matlab|accha|haan|toh|na|yaar|dekho|basically kya hai)\b",
]


def clean_asr_transcript(raw_text: Optional[str]) -> str:
    """Strips vocal fillers, stutters, and ASR hesitation tokens while preserving technical identifiers."""
    if not raw_text:
        return ""
    cleaned = raw_text.strip()
    for pattern in ASR_FILLER_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    # Strip syllable stutters: e.g. "c-cosine" or "w-what" or "th-the" -> "cosine", "what", "the"
    cleaned = re.sub(r"\b([a-zA-Z]{1,3})-+(?=[a-zA-Z]{2,})", "", cleaned)
    # Strip stuttered word repetitions: e.g. "in, in" or "in in" -> "in", "the the" -> "the", "we we" -> "we"
    cleaned = re.sub(r"\b([a-zA-Z0-9_]+)(?:[,\s]+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)
    # Clean up orphaned punctuation and normalize whitespace
    cleaned = re.sub(r"[,\s]+([,.?!])", r"\1", cleaned)
    cleaned = re.sub(r"^[,\s;:-]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ============================================================================
# SESSION STATE DATA STRUCTURES
# ============================================================================

@dataclass
class TurnRecord:
    turn_index: int
    student_raw_transcript: str
    student_clean_transcript: str
    verdict: VerdictType
    action: str
    ack_text: str
    question_text: str
    topic: str
    depth_level: int
    highlight: Optional[CodeHighlight] = None
    diagram_node_id: Optional[str] = None
    coding_challenge: Optional[CodingChallenge] = None
    code_result: Optional[RunCodeResponse] = None


@dataclass
class VivaSession:
    session_id: str
    mode: Literal["repo", "paper", "dsa"]
    title: str
    repo_index: Optional[RepoIndex] = None
    paper_index: Optional[PaperIndex] = None
    dsa_profile: Optional[LeetCodeProfileSummary] = None
    dsa_topic: str = "Arrays & Hashing"
    current_dsa_problem: Any = None
    solved_dsa_ids: List[str] = field(default_factory=list)
    selected_author: Optional[str] = None
    current_depth: int = 1
    current_symbol_idx: int = 0
    current_node_idx: int = 0
    max_turns: int = 8
    done: bool = False
    turns: List[TurnRecord] = field(default_factory=list)
    code_results: List[Dict[str, Any]] = field(default_factory=list)
    active_challenge: Optional[CodingChallenge] = None


# Global in-memory session store as specified in Section 5
SESSIONS: Dict[str, VivaSession] = {}


# ============================================================================
# GEMINI 2.5 FLASH JSON CLIENT (WITH OFFLINE DETERMINISTIC FALLBACK)
# ============================================================================

def _robust_json_parse(raw_text: str) -> Optional[Dict[str, Any]]:
    """Robustly extracts and parses JSON dictionary from LLM response text,
    handling markdown fences, leading/trailing prose, and trailing commas."""
    if not raw_text or not raw_text.strip():
        return None
    s = raw_text.strip()

    # 1. Strip markdown fences if present (```json ... ``` or ``` ... ```)
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()

    # 2. Try direct json.loads
    try:
        val = json.loads(s)
        if isinstance(val, dict):
            return val
    except Exception:
        pass

    # 3. Search for outermost JSON object { ... }
    m = re.search(r"(\{.*\})", s, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        try:
            val = json.loads(candidate)
            if isinstance(val, dict):
                return val
        except Exception:
            pass

        # 4. Clean trailing commas before closing braces/brackets
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            val = json.loads(cleaned)
            if isinstance(val, dict):
                return val
        except Exception:
            pass

    return None


def _call_gemini_json(system_prompt: str, user_prompt: str) -> Optional[Dict[str, Any]]:
    """
    Calls Gemini 2.5 Flash enforcing `response_mime_type="application/json"`.
    Supports both `google-genai` (v1+) and `google-generativeai` SDKs.
    Returns None cleanly if no API key is configured or network fails.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key.startswith("your_"):
        return None

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Attempt 1: Modern google-genai SDK
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.25,
            ),
        )
        if response and response.text:
            parsed = _robust_json_parse(response.text)
            if parsed:
                return parsed
    except ImportError:
        pass
    except Exception:
        pass

    # Attempt 2: google-generativeai SDK
    try:
        import google.generativeai as genai_legacy  # type: ignore

        genai_legacy.configure(api_key=api_key)
        model = genai_legacy.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,
            generation_config={"response_mime_type": "application/json", "temperature": 0.25},
        )
        response = model.generate_content(user_prompt)
        if response and response.text:
            parsed = _robust_json_parse(response.text)
            if parsed:
                return parsed
    except Exception:
        pass

    return None


# ============================================================================
# DETERMINISTIC HEURISTIC EVALUATOR & QUESTION SYNTHESIZER (FALLBACK / GUARD)
# ============================================================================

def _evaluate_student_answer_heuristically(
    clean_text: str,
    symbol: Optional[ASTFunctionSymbol],
    node: Optional[PaperNode],
    code_result: Optional[RunCodeResponse],
) -> VerdictType:
    """
    Evaluates technical density of the cleaned answer when offline or as a sanity bound.
    Fluency-blind: ignores grammar and measures technical concept coverage + sandbox pass status.
    """
    if code_result is not None:
        return "strong" if code_result.passed else "partial"

    if not clean_text or len(clean_text.strip()) < 3:
        return "no_answer"

    # Genuine surrender / give-up intent (ignoring technical uses of 'pass' or 'skip')
    surrender_patterns = [
        r"\bi\s+(don'?t|do\s+not)\s+know\b",
        r"\bnot\s+sure\b",
        r"\bno\s+idea\b",
        r"^\s*(pass|skip|i\s+pass|please\s+skip)\s*[.?!]*$",
        r"\b(i\s+pass|please\s+skip|skip\s+this|pass\s+this)\b",
    ]
    if any(re.search(pat, clean_text, re.IGNORECASE) for pat in surrender_patterns):
        return "weak"

    words = re.findall(r"[a-zA-Z0-9_]+", clean_text.lower())
    if not words:
        return "no_answer"

    # Extract domain keywords from current AST symbol or Paper node
    domain_terms: set[str] = set()
    if symbol:
        raw_items = (
            [symbol.name]
            + symbol.args
            + symbol.calls
            + symbol.constants
            + re.findall(r"[a-zA-Z_]{3,}", symbol.docstring or "")
        )
        for item in raw_items:
            lower = item.lower()
            domain_terms.add(lower)
            for sub in re.split(r"[._\s]+", lower):
                if len(sub) >= 3:
                    domain_terms.add(sub)
                    if sub == "vec":
                        domain_terms.add("vector")
                        domain_terms.add("vectors")
                    elif sub == "doc":
                        domain_terms.add("document")
    if node:
        domain_terms.update(
            t.lower() for t in re.findall(r"[a-zA-Z]{3,}", f"{node.label} {node.excerpt}")
        )

    technical_indicators = {
        "complexity", "time", "space", "memory", "loop", "hash", "dict", "list",
        "async", "await", "cache", "index", "tree", "node", "edge", "boundary",
        "null", "none", "empty", "zero", "exception", "error", "return", "function",
        "parameter", "parameters", "latency", "throughput", "threshold", "vector",
        "vectors", "matrix", "matrices", "gradient", "attention", "layer", "loss",
        "normalization", "token", "tokens", "dot", "product", "norm", "norms", "l2",
        "linear", "constant", "quadratic", "logarithmic", "tradeoff", "trade-off",
        "tradeoffs", "bottleneck", "concurrency", "concurrent", "dimension",
        "dimensions", "scale", "scaling", "iterate", "iteration", "iterating",
        "generator", "generators", "auxiliary", "magnitude", "magnitudes",
        "divide", "division", "precision", "floor", "rerank", "cosine", "similarity",
        "similarity_floor", "dot_product", "l2_norm",
    }

    matched_domain = sum(1 for w in set(words) if w in domain_terms)
    matched_tech = sum(1 for w in set(words) if w in technical_indicators)

    # Multi-word technical concept bonuses in full text
    multi_word_concepts = [
        "dot product", "cosine similarity", "time complexity", "space complexity",
        "l2 norm", "auxiliary memory", "auxiliary space", "in place", "in-place",
        "linear time", "constant space", "worst case", "worst-case", "single pass",
        "similarity floor", "zero division", "floating point", "vector dimension"
    ]
    lower_text = clean_text.lower()
    matched_phrases = sum(1 for phrase in multi_word_concepts if phrase in lower_text)
    effective_tech = matched_tech + (matched_phrases * 2)

    if len(words) >= 10 and (matched_domain >= 1 or effective_tech >= 2):
        return "strong"
    if len(words) >= 5 and (matched_domain >= 1 or effective_tech >= 1):
        return "partial"
    if len(words) >= 14:
        return "partial"
    return "weak"


def _build_coding_challenge_for_symbol(
    symbol: ASTFunctionSymbol,
    session: VivaSession,
) -> CodingChallenge:
    """Generates an L4 mutation/edge-case CodingChallenge grounded in the target AST symbol."""
    llm_payload = _call_gemini_json(
        CHALLENGE_GEN_PROMPT,
        json.dumps(
            {
                "repo_name": session.title,
                "symbol": symbol.model_dump(),
            },
            indent=2,
        ),
    )
    if llm_payload and all(
        k in llm_payload for k in ("description", "target_file", "starter_code", "test_code")
    ):
        return CodingChallenge(
            description=str(llm_payload["description"]),
            target_file=str(llm_payload["target_file"]),
            starter_code=str(llm_payload["starter_code"]),
            test_code=str(llm_payload["test_code"]),
        )

    # Deterministic AST-grounded challenge fallback
    fn_name = symbol.name
    args_list = symbol.args if symbol.args else ["items", "threshold"]
    clean_args = [a for a in args_list if a != "self"] or ["data"]
    sig_args = ", ".join(clean_args)
    first_arg = clean_args[0]

    starter_code = symbol.code_snippet or (
        f"def {fn_name}({sig_args}):\n"
        f"    \"\"\"L4 Sandbox Verification Target from {symbol.file_path} (Lines {symbol.line_start}-{symbol.line_end}).\n"
        f"    BUG: Raises an error or returns incorrect output when `{first_arg}` is empty or contains boundary values.\n"
        f"    Fix the edge-case handling below so all pytest checks pass.\n"
        f"    \"\"\"\n"
        f"    # Planted boundary bug: no guard for empty / None {first_arg}\n"
        f"    total = sum({first_arg})\n"
        f"    return round(total / len({first_arg}), 4)\n"
    )

    test_code = (
        f"import pytest\n"
        f"from student_solution import {fn_name}\n\n"
        f"def test_{fn_name}_standard_input():\n"
        f"    result = {fn_name}([10, 20, 30]{', 0.5' * (len(clean_args) - 1)})\n"
        f"    assert result == 20.0\n\n"
        f"def test_{fn_name}_empty_boundary_edge_case():\n"
        f"    # L4 Mutation check: empty or None input should return 0.0 instead of raising ZeroDivisionError/TypeError\n"
        f"    assert {fn_name}([]{', 0.5' * (len(clean_args) - 1)}) == 0.0\n"
        f"    assert {fn_name}(None{', 0.5' * (len(clean_args) - 1)}) == 0.0\n"
    )

    return CodingChallenge(
        description=(
            f"Level 4 Live Verification in `{symbol.file_path}` (lines {symbol.line_start}-{symbol.line_end}): "
            f"Fix `{fn_name}()` so that empty or `None` boundary inputs return `0.0` safely without raising `ZeroDivisionError` or `TypeError`."
        ),
        target_file=symbol.file_path,
        starter_code=starter_code,
        test_code=test_code,
    )


def _deterministic_repo_question(
    symbol: ASTFunctionSymbol,
    depth_level: int,
    verdict: VerdictType,
    code_result: Optional[RunCodeResponse] = None,
    turn_index: int = 0,
) -> Dict[str, Any]:
    """Generates varied, AST-grounded L1-L4 questions when running in offline/fallback mode."""
    args_str = ", ".join(symbol.args) if symbol.args else "no arguments"
    calls_str = ", ".join(symbol.calls[:3]) if symbol.calls else "internal operations"
    consts_str = ", ".join(symbol.constants[:2]) if symbol.constants else "local defaults"

    if code_result is not None:
        if code_result.passed:
            ack = f"Excellent—your live fix in {symbol.file_path} passed all pytest assertions in {code_result.runtime_ms}ms."
        else:
            ack = f"Your sandbox test run reported a failure; let's inspect the boundary condition on lines {symbol.line_start} to {symbol.line_end}."
    elif verdict == "start":
        ack = f"Welcome to VivaVoce. I have indexed your repository AST and selected {symbol.file_path}."
    elif verdict == "strong":
        ack = f"Strong technical point on how `{symbol.name}` handles its state."
    elif verdict == "partial":
        ack = f"You captured the high-level flow of `{symbol.name}`, let's sharpen the specifics."
    elif verdict == "weak":
        ack = f"No worries—let's look directly at lines {symbol.line_start} to {symbol.line_end} in `{symbol.file_path}`."
    else:
        ack = f"Let's anchor on `{symbol.name}` at lines {symbol.line_start} to {symbol.line_end}."

    variants: Dict[int, List[str]] = {
        1: [
            (
                f"Looking at `{symbol.name}({args_str})` in `{symbol.file_path}` (lines {symbol.line_start}-{symbol.line_end}), "
                f"what is the exact role of this function and how does it transform its inputs before calling {calls_str}?"
            ),
            (
                f"In `{symbol.file_path}` (lines {symbol.line_start}-{symbol.line_end}), trace what `{symbol.name}` returns "
                f"and how `{consts_str}` influences its output."
            ),
            (
                f"Walk me through the control flow inside `{symbol.name}` at `{symbol.file_path}`:{symbol.line_start}-{symbol.line_end}—"
                f"which input parameter drives the main branch?"
            ),
        ],
        2: [
            (
                f"In `{symbol.file_path}` lines {symbol.line_start}-{symbol.line_end}, why did you structure `{symbol.name}` "
                f"with parameters `({args_str})` instead of decoupling the state transformation?"
            ),
            (
                f"Why does `{symbol.name}` in `{symbol.file_path}` rely on {calls_str} here, and what assumption does it make about the caller's data?"
            ),
            (
                f"How would `{symbol.name}` behave differently if `{consts_str}` were changed, and why was that value chosen?"
            ),
        ],
        3: [
            (
                f"At Level 3 Analysis on `{symbol.name}` (lines {symbol.line_start}-{symbol.line_end} of `{symbol.file_path}`): "
                f"what is the worst-case time and memory complexity when input volume scales 100x, and what trade-off did you make?"
            ),
            (
                f"If `{symbol.name}` in `{symbol.file_path}` is called concurrently under heavy load, where is the bottleneck or shared-state risk?"
            ),
            (
                f"Compare your implementation of `{symbol.name}` against an alternative data structure or streaming approach—what did you gain or sacrifice?"
            ),
        ],
        4: [
            (
                f"Level 4 Mutation Challenge on `{symbol.name}` (`{symbol.file_path}`:{symbol.line_start}-{symbol.line_end}): "
                f"what breaks if an empty or degenerate boundary payload reaches this block? Fix the edge-case bug in the IDE and click Run & Verify."
            ),
            (
                f"Level 4 Edge-Case Check in `{symbol.file_path}` (`{symbol.name}`, lines {symbol.line_start}-{symbol.line_end}): "
                f"guard against zero-length or `None` inputs in the editor and click Run & Verify to prove it passes pytest."
            ),
        ],
    }

    pool = variants.get(depth_level, variants[1])
    q = pool[turn_index % len(pool)]
    action = (
        "TriggerCodeChallenge"
        if depth_level == 4
        else ("DrillDown" if verdict in ("start", "strong") else "Probe")
    )

    return {
        "action": action,
        "ack_text": ack,
        "question_text": q,
        "topic": f"{symbol.name} ({os.path.basename(symbol.file_path)})",
        "highlight": CodeHighlight(
            file_path=symbol.file_path,
            line_start=symbol.line_start,
            line_end=symbol.line_end,
        ),
    }


def _deterministic_paper_question(
    node: PaperNode,
    depth_level: int,
    verdict: VerdictType,
    turn_index: int = 0,
) -> Dict[str, Any]:
    """Generates varied, concept-map grounded L1-L4 questions for Paper mode."""
    if verdict == "start":
        ack = f"Welcome to VivaVoce Paper Mode. I have mapped your paper's methodology into a visual concept graph starting at node {node.node_id}."
    elif verdict == "strong":
        ack = f"Clear explanation of the {node.label} stage."
    elif verdict == "partial":
        ack = f"Good intuition on {node.label}; let's examine its formal assumptions."
    else:
        ack = f"Let's focus on the highlighted excerpt for node {node.node_id} ({node.label})."

    variants: Dict[int, List[str]] = {
        1: [
            f"In node {node.node_id} ({node.label}), what is the core input-to-output transformation described in this section of the paper?",
            f"Looking at {node.node_id} ({node.label}), what specific problem or bottleneck does this stage solve before passing data downstream?",
        ],
        2: [
            f"Why does the methodology at node {node.node_id} ({node.label}) adopt this specific formulation rather than a standard baseline?",
            f"What key mathematical or architectural assumption must hold for {node.node_id} ({node.label}) to work as intended?",
        ],
        3: [
            f"What are the primary computational or statistical trade-offs introduced by {node.label} ({node.node_id}), and how would an ablation study isolate its impact?",
            f"If you removed or simplified {node.node_id} ({node.label}), which downstream metric in the paper would degrade first and why?",
        ],
        4: [
            f"At Level 4 Evaluation for {node.node_id} ({node.label}): under what distribution shift or adversarial regime does this assumption fail, and how would you modify the architecture?",
            f"Design a stress-test or counterfactual experiment that would break {node.node_id} ({node.label})—what failure mode do you expect?",
        ],
    }

    pool = variants.get(depth_level, variants[1])
    q = pool[turn_index % len(pool)]

    return {
        "action": "DrillDown" if verdict in ("start", "strong") else "Probe",
        "ack_text": ack,
        "question_text": q,
        "topic": f"{node.node_id}: {node.label}",
        "diagram_node_id": node.node_id,
        "paper_excerpt": node.excerpt,
    }


# ============================================================================
# CORE SESSION MANAGER & STATE MACHINE
# ============================================================================

class SessionManager:
    """
    Manages VivaVoce examination sessions, author-filtered AST symbol selection,
    Bloom L1-L4 state transitions, and ReAct tool triggers.
    """

    def __init__(self, sessions_store: Optional[Dict[str, VivaSession]] = None) -> None:
        self.sessions: Dict[str, VivaSession] = sessions_store if sessions_store is not None else SESSIONS

    def _get_candidate_symbols(
        self,
        repo_index: RepoIndex,
        selected_author: Optional[str] = None,
    ) -> List[ASTFunctionSymbol]:
        """Filters AST symbols by git blame author ownership if a teammate is selected."""
        if not repo_index.symbols:
            return [
                ASTFunctionSymbol(
                    name="process_pipeline",
                    file_path="src/core.py",
                    line_start=12,
                    line_end=42,
                    args=["payload", "config"],
                    docstring="Core data processing and validation pipeline.",
                    calls=["validate_input", "compute_metrics"],
                    constants=["MAX_BATCH_SIZE"],
                )
            ]

        if not selected_author or selected_author not in repo_index.author_map:
            return repo_index.symbols

        owned_ranges = repo_index.author_map.get(selected_author, [])
        filtered: List[ASTFunctionSymbol] = []
        for sym in repo_index.symbols:
            for owned in owned_ranges:
                if owned.file_path == sym.file_path and not (
                    sym.line_end < owned.line_start or sym.line_start > owned.line_end
                ):
                    filtered.append(sym)
                    break

        return filtered if filtered else repo_index.symbols

    def start_session(
        self,
        mode: Literal["repo", "paper", "dsa"],
        repo_index: Optional[RepoIndex] = None,
        paper_index: Optional[PaperIndex] = None,
        selected_author: Optional[str] = None,
        audio_synthesizer: Optional[Callable[[str], str]] = None,
        dsa_profile: Optional[LeetCodeProfileSummary] = None,
        dsa_topic: str = "Arrays & Hashing",
    ) -> TurnResponse:
        """Initializes a new viva session at Bloom Level 1 (Recall) and emits the opening turn."""
        session_id = str(uuid.uuid4())
        if mode == "repo" and repo_index:
            title = repo_index.repo_name
        elif mode == "dsa" and dsa_profile:
            title = f"LeetCode DSA Prep ({dsa_profile.username} — {dsa_topic})"
        elif paper_index:
            title = paper_index.title
        else:
            title = "VivaVoce Session"

        initial_problem = None
        if mode == "dsa" and dsa_profile is not None:
            from backend.brain.dsa_coach import pick_initial_problem

            initial_problem = pick_initial_problem(dsa_profile, dsa_topic)

        session = VivaSession(
            session_id=session_id,
            mode=mode,
            title=title,
            repo_index=repo_index,
            paper_index=paper_index,
            dsa_profile=dsa_profile,
            dsa_topic=dsa_topic,
            current_dsa_problem=initial_problem,
            selected_author=selected_author,
            current_depth=1,
            current_symbol_idx=0,
            current_node_idx=0,
        )
        self.sessions[session_id] = session

        return self.process_turn(
            session_id=session_id,
            student_text="",
            code_result=None,
            selected_author=selected_author,
            audio_synthesizer=audio_synthesizer,
            is_initial_turn=True,
        )

    def process_turn(
        self,
        session_id: str,
        student_text: Optional[str] = None,
        code_result: Optional[RunCodeResponse] = None,
        selected_author: Optional[str] = None,
        audio_synthesizer: Optional[Callable[[str], str]] = None,
        is_initial_turn: bool = False,
    ) -> TurnResponse:
        """
        Executes one full ReAct state transition:
        1. Cleans ASR transcript (Fluency-Blind preprocessing).
        2. Evaluates student answer semantics (or sandbox pytest execution result).
        3. Updates Bloom cognitive depth (L1 -> L2 -> L3 -> L4).
        4. Generates grounded question + CodeHighlight (Repo) or diagram_node_id (Paper).
        5. Attaches CodingChallenge when reaching L4 in Repo mode.
        """
        if session_id not in self.sessions:
            raise KeyError(f"Session '{session_id}' not found.")

        session = self.sessions[session_id]
        if selected_author:
            session.selected_author = selected_author

        raw_transcript = (student_text or "").strip()
        clean_transcript = clean_asr_transcript(raw_transcript)

        if code_result is not None and session.active_challenge is not None:
            session.code_results.append(
                {
                    "challenge_description": session.active_challenge.description,
                    "target_file": session.active_challenge.target_file,
                    "passed": code_result.passed,
                    "runtime_ms": code_result.runtime_ms,
                }
            )

        if session.mode == "repo":
            return self._process_repo_turn(
                session=session,
                raw_transcript=raw_transcript,
                clean_transcript=clean_transcript,
                code_result=code_result,
                audio_synthesizer=audio_synthesizer,
                is_initial_turn=is_initial_turn,
            )
        elif session.mode == "dsa":
            return self._process_dsa_turn(
                session=session,
                raw_transcript=raw_transcript,
                clean_transcript=clean_transcript,
                code_result=code_result,
                audio_synthesizer=audio_synthesizer,
                is_initial_turn=is_initial_turn,
            )
        else:
            return self._process_paper_turn(
                session=session,
                raw_transcript=raw_transcript,
                clean_transcript=clean_transcript,
                audio_synthesizer=audio_synthesizer,
                is_initial_turn=is_initial_turn,
            )

    def _process_repo_turn(
        self,
        session: VivaSession,
        raw_transcript: str,
        clean_transcript: str,
        code_result: Optional[RunCodeResponse],
        audio_synthesizer: Optional[Callable[[str], str]],
        is_initial_turn: bool,
    ) -> TurnResponse:
        assert session.repo_index is not None
        candidate_symbols = self._get_candidate_symbols(
            session.repo_index, session.selected_author
        )
        active_symbol = candidate_symbols[session.current_symbol_idx % len(candidate_symbols)]

        # 1. Determine verdict & Bloom depth transition
        if is_initial_turn and not session.turns:
            verdict: VerdictType = "start"
            next_depth = 1
        else:
            verdict = _evaluate_student_answer_heuristically(
                clean_transcript, active_symbol, None, code_result
            )
            if verdict == "strong":
                if session.current_depth < 4:
                    next_depth = session.current_depth + 1
                else:
                    # Completed L4 for this symbol -> advance to next symbol at L2
                    session.current_symbol_idx += 1
                    active_symbol = candidate_symbols[
                        session.current_symbol_idx % len(candidate_symbols)
                    ]
                    next_depth = 2
            elif verdict == "partial":
                next_depth = session.current_depth
            else:
                next_depth = max(1, session.current_depth)

        # 2. Try Gemini 2.5 Flash ReAct generation first
        history_dicts = [
            {
                "turn": t.turn_index,
                "topic": t.topic,
                "depth": t.depth_level,
                "question": t.question_text,
                "student_answer": t.student_clean_transcript,
                "verdict": t.verdict,
            }
            for t in session.turns
        ]
        user_prompt = build_repo_turn_user_prompt(
            repo_summary=session.repo_index.summary or session.repo_index.repo_name,
            symbols_context=[s.model_dump() for s in candidate_symbols],
            history=history_dicts,
            current_depth=next_depth,
            student_transcript=clean_transcript,
            selected_author=session.selected_author,
            code_result=code_result.model_dump() if code_result else None,
        )
        llm_out = _call_gemini_json(REPO_EXAMINER_PROMPT, user_prompt)

        if llm_out and "question_text" in llm_out:
            llm_verdict = llm_out.get("verdict")
            if not is_initial_turn and llm_verdict in ("strong", "partial", "weak", "no_answer"):
                # Fluency-blind protection: If deterministic heuristic verified strong technical substance,
                # do not downgrade to weak/no_answer due to LLM ASR/fluency bias
                if verdict == "strong" and llm_verdict in ("weak", "no_answer"):
                    pass
                else:
                    verdict = llm_verdict  # type: ignore
                if verdict == "strong":
                    next_depth = min(4, session.current_depth + 1)

            ack_text = str(llm_out.get("ack_text") or "Got it.")
            question_text = str(llm_out["question_text"])
            topic = str(llm_out.get("topic") or active_symbol.name)
            action = str(llm_out.get("action") or "DrillDown")

            hl_raw = llm_out.get("highlight") or {}
            highlight = CodeHighlight(
                file_path=str(hl_raw.get("file_path") or active_symbol.file_path),
                line_start=max(1, int(hl_raw.get("line_start") or active_symbol.line_start)),
                line_end=max(1, int(hl_raw.get("line_end") or active_symbol.line_end)),
            )
        else:
            fallback = _deterministic_repo_question(
                symbol=active_symbol,
                depth_level=next_depth,
                verdict=verdict,
                code_result=code_result,
                turn_index=len(session.turns),
            )
            ack_text = fallback["ack_text"]
            question_text = fallback["question_text"]
            topic = fallback["topic"]
            action = fallback["action"]
            highlight = fallback["highlight"]

        session.current_depth = next_depth

        # 3. At L4 in Repo mode, attach a CodingChallenge
        coding_challenge: Optional[CodingChallenge] = None
        if session.current_depth == 4 and (code_result is None or not code_result.passed):
            coding_challenge = _build_coding_challenge_for_symbol(active_symbol, session)
            session.active_challenge = coding_challenge

        # 4. Check session completion
        turn_number = len(session.turns) + 1
        is_closing = False
        if code_result is not None and code_result.passed:
            is_closing = True
            session.done = True
        elif turn_number >= session.max_turns:
            is_closing = True
            session.done = True

        if is_closing:
            if code_result is not None and code_result.passed:
                ack_text = f"Excellent work! Your live bug fix in {active_symbol.file_path} passed all pytest verification tests in {code_result.runtime_ms}ms."
            else:
                # Keep the real feedback on the final answer; append a neutral closing line
                sep = "" if ack_text.rstrip().endswith((".", "!", "?")) else "."
                ack_text = f"{ack_text.rstrip()}{sep} Thank you for completing the technical viva for {session.title}."
            question_text = "That concludes your examination across all cognitive levels. Click 'View Full Report' to review your competency scores, topic depth radar, and personalized study plan."
            topic = "Viva Complete"
            action = "ConcludeViva"

        try:
            from backend.voice.tts_service import build_spoken_text
            spoken_script = build_spoken_text(ack_text, question_text)
        except Exception:
            spoken_script = f"{ack_text} {question_text}".strip()
        audio_b64 = audio_synthesizer(spoken_script) if audio_synthesizer else ""

        record = TurnRecord(
            turn_index=turn_number,
            student_raw_transcript=raw_transcript,
            student_clean_transcript=clean_transcript,
            verdict=verdict,
            action=action,
            ack_text=ack_text,
            question_text=question_text,
            topic=topic,
            depth_level=session.current_depth,
            highlight=highlight,
            coding_challenge=coding_challenge,
            code_result=code_result,
        )
        session.turns.append(record)

        return TurnResponse(
            session_id=session.session_id,
            student_transcript=raw_transcript or clean_transcript,
            verdict=verdict,
            ack_text=ack_text,
            question_text=question_text,
            audio_base64=audio_b64,
            topic=topic,
            depth_level=session.current_depth,
            highlight=highlight,
            diagram_node_id=None,
            paper_excerpt=None,
            coding_challenge=coding_challenge,
            done=session.done,
        )

    def _process_paper_turn(
        self,
        session: VivaSession,
        raw_transcript: str,
        clean_transcript: str,
        audio_synthesizer: Optional[Callable[[str], str]],
        is_initial_turn: bool,
    ) -> TurnResponse:
        assert session.paper_index is not None
        nodes = session.paper_index.nodes or [
            PaperNode(
                node_id="N1",
                label="Problem Formulation & Inputs",
                excerpt="The proposed architecture ingests raw multi-modal inputs and normalizes token representations.",
            )
        ]
        active_node = nodes[session.current_node_idx % len(nodes)]

        if is_initial_turn and not session.turns:
            verdict: VerdictType = "start"
            next_depth = 1
        else:
            verdict = _evaluate_student_answer_heuristically(
                clean_transcript, None, active_node, None
            )
            if verdict == "strong":
                if session.current_depth < 4:
                    next_depth = session.current_depth + 1
                else:
                    session.current_node_idx += 1
                    active_node = nodes[session.current_node_idx % len(nodes)]
                    next_depth = 1
            elif verdict == "partial":
                next_depth = session.current_depth
            else:
                next_depth = max(1, session.current_depth)

        history_dicts = [
            {
                "turn": t.turn_index,
                "node": t.diagram_node_id,
                "depth": t.depth_level,
                "question": t.question_text,
                "student_answer": t.student_clean_transcript,
                "verdict": t.verdict,
            }
            for t in session.turns
        ]
        user_prompt = build_paper_turn_user_prompt(
            paper_title=session.paper_index.title,
            nodes_context=[n.model_dump() for n in nodes],
            history=history_dicts,
            current_depth=next_depth,
            active_node_id=active_node.node_id,
            student_transcript=clean_transcript,
        )
        llm_out = _call_gemini_json(PAPER_EXAMINER_PROMPT, user_prompt)

        if llm_out and "question_text" in llm_out:
            llm_verdict = llm_out.get("verdict")
            if not is_initial_turn and llm_verdict in ("strong", "partial", "weak", "no_answer"):
                # Fluency-blind protection: If deterministic heuristic verified strong technical substance,
                # do not downgrade to weak/no_answer due to LLM ASR/fluency bias
                if verdict == "strong" and llm_verdict in ("weak", "no_answer"):
                    pass
                else:
                    verdict = llm_verdict  # type: ignore
                if verdict == "strong":
                    next_depth = min(4, session.current_depth + 1)

            ack_text = str(llm_out.get("ack_text") or "Good point.")
            question_text = str(llm_out["question_text"])
            topic = str(llm_out.get("topic") or f"{active_node.node_id}: {active_node.label}")
            action = str(llm_out.get("action") or "DrillDown")
            node_id = str(llm_out.get("diagram_node_id") or active_node.node_id)
            excerpt = str(
                llm_out.get("paper_excerpt")
                or session.paper_index.node_excerpts.get(node_id)
                or active_node.excerpt
            )
        else:
            fallback = _deterministic_paper_question(
                node=active_node,
                depth_level=next_depth,
                verdict=verdict,
                turn_index=len(session.turns),
            )
            ack_text = fallback["ack_text"]
            question_text = fallback["question_text"]
            topic = fallback["topic"]
            action = fallback["action"]
            node_id = fallback["diagram_node_id"]
            excerpt = fallback["paper_excerpt"]

        session.current_depth = next_depth
        turn_number = len(session.turns) + 1
        if turn_number >= session.max_turns:
            session.done = True
            # Keep the real feedback on the final answer; append a neutral closing line
            sep = "" if ack_text.rstrip().endswith((".", "!", "?")) else "."
            ack_text = f"{ack_text.rstrip()}{sep} Thank you for completing the paper viva for {session.title}."
            question_text = "That concludes your paper viva examination. Click 'View Full Report' to review your competency scores, topic depth radar, and personalized study plan."
            topic = "Viva Complete"
            action = "ConcludeViva"

        try:
            from backend.voice.tts_service import build_spoken_text
            spoken_script = build_spoken_text(ack_text, question_text)
        except Exception:
            spoken_script = f"{ack_text} {question_text}".strip()
        audio_b64 = audio_synthesizer(spoken_script) if audio_synthesizer else ""

        record = TurnRecord(
            turn_index=turn_number,
            student_raw_transcript=raw_transcript,
            student_clean_transcript=clean_transcript,
            verdict=verdict,
            action=action,
            ack_text=ack_text,
            question_text=question_text,
            topic=topic,
            depth_level=session.current_depth,
            diagram_node_id=node_id,
        )
        session.turns.append(record)

        return TurnResponse(
            session_id=session.session_id,
            student_transcript=raw_transcript or clean_transcript,
            verdict=verdict,
            ack_text=ack_text,
            question_text=question_text,
            audio_base64=audio_b64,
            topic=topic,
            depth_level=session.current_depth,
            highlight=None,
            diagram_node_id=node_id,
            paper_excerpt=excerpt,
            coding_challenge=None,
            done=session.done,
        )


    def _process_dsa_turn(
        self,
        session: VivaSession,
        raw_transcript: str,
        clean_transcript: str,
        code_result: Optional[RunCodeResponse],
        audio_synthesizer: Optional[Callable[[str], str]],
        is_initial_turn: bool,
    ) -> TurnResponse:
        from backend.brain.dsa_coach import (
            DSA_PROBLEMS,
            detect_student_lacks,
            pick_next_problem,
        )

        problem = session.current_dsa_problem or DSA_PROBLEMS[0]
        session.current_dsa_problem = problem
        profile = session.dsa_profile

        if is_initial_turn and not session.turns:
            verdict: VerdictType = "start"
            next_depth = 1
            weak_summary = (
                ", ".join(profile.weak_topics[:2])
                if profile and profile.weak_topics
                else session.dsa_topic
            )
            ack_text = (
                f"Connected LeetCode profile @{profile.username} "
                f"({profile.total_solved} solved; focus areas: {weak_summary})."
                if profile
                else f"Started DSA Prep on {session.dsa_topic}."
            )
            question_text = (
                f"Problem 1 [{problem.difficulty}]: {problem.title}. {problem.prompt_summary} "
                f"Before coding in `{problem.target_file}`, explain your approach and target time/space complexity."
            )
            action = "TriggerCodeChallenge"
        else:
            lacks = detect_student_lacks(clean_transcript, code_result, problem)
            if code_result is not None:
                if code_result.passed:
                    verdict = "strong"
                    session.solved_dsa_ids.append(problem.problem_id)
                    next_depth = min(4, session.current_depth + 1)
                    next_prob = pick_next_problem(
                        topic=session.dsa_topic,
                        current_problem=problem,
                        lacks=lacks,
                        passed_sandbox=True,
                        solved_ids=set(session.solved_dsa_ids),
                    )
                    session.current_dsa_problem = next_prob
                    problem = next_prob
                    lack_note = (
                        f" Watch out for: {lacks[0]}."
                        if lacks
                        else " Complexity and edge cases look solid."
                    )
                    ack_text = f"All pytest cases passed in {code_result.runtime_ms}ms!{lack_note}"
                    question_text = (
                        f"Moving to your next adaptive problem [{problem.difficulty}]: {problem.title} "
                        f"({problem.pattern}). {problem.prompt_summary} Explain your strategy and implement it in `{problem.target_file}`."
                    )
                    action = "TriggerCodeChallenge"
                else:
                    verdict = "partial"
                    next_depth = max(2, session.current_depth)
                    ack_text = (
                        f"Your code failed a sandbox test—gap detected in {problem.edge_case_focus}."
                    )
                    question_text = (
                        f"Look at `{problem.target_file}`: why does your current logic break on {problem.edge_case_focus}? "
                        f"Explain the fix or update the code and click Run & Verify."
                    )
                    action = "Probe"
            else:
                # Spoken / typed conceptual explanation
                word_count = len(clean_transcript.split())
                if not clean_transcript:
                    verdict = "no_answer"
                elif not lacks and word_count >= 7:
                    verdict = "strong"
                elif word_count >= 5:
                    verdict = "partial"
                else:
                    verdict = "weak"

                if verdict == "strong":
                    next_depth = min(4, session.current_depth + 1)
                    ack_text = f"Good reasoning on {problem.pattern} ({problem.optimal_complexity})."
                    question_text = (
                        f"Now implement `{problem.title}` in `{problem.target_file}` (pay attention to {problem.edge_case_focus}) "
                        f"and click Run & Verify to prove it passes all pytest cases."
                    )
                    action = "TriggerCodeChallenge"
                else:
                    next_depth = session.current_depth
                    gap_msg = lacks[0] if lacks else f"handling {problem.edge_case_focus}"
                    ack_text = f"I noticed a gap in: {gap_msg}."
                    question_text = (
                        f"For {problem.title}, how can you apply {problem.pattern} to reach {problem.optimal_complexity} "
                        f"while handling {problem.edge_case_focus}?"
                    )
                    action = "Hint"

        challenge = problem.to_coding_challenge()
        session.active_challenge = challenge
        session.current_depth = next_depth
        turn_number = len(session.turns) + 1
        if turn_number >= session.max_turns:
            session.done = True

        spoken_script = f"{ack_text} {question_text}".strip()
        audio_b64 = audio_synthesizer(spoken_script) if audio_synthesizer else ""
        topic_label = f"{problem.topic}: {problem.title} ({problem.difficulty})"

        record = TurnRecord(
            turn_index=turn_number,
            student_raw_transcript=raw_transcript,
            student_clean_transcript=clean_transcript,
            verdict=verdict,
            action=action,
            ack_text=ack_text,
            question_text=question_text,
            topic=topic_label,
            depth_level=session.current_depth,
            coding_challenge=challenge,
            code_result=code_result,
        )
        session.turns.append(record)

        return TurnResponse(
            session_id=session.session_id,
            student_transcript=raw_transcript or clean_transcript,
            verdict=verdict,
            ack_text=ack_text,
            question_text=question_text,
            audio_base64=audio_b64,
            topic=topic_label,
            depth_level=session.current_depth,
            highlight=None,
            diagram_node_id=None,
            paper_excerpt=None,
            coding_challenge=challenge,
            done=session.done,
        )


# Singleton manager + module-level convenience functions matching Section 5 table
session_manager = SessionManager(SESSIONS)


def start_session(
    mode: Literal["repo", "paper", "dsa"],
    repo_index: Optional[RepoIndex] = None,
    paper_index: Optional[PaperIndex] = None,
    selected_author: Optional[str] = None,
    audio_synthesizer: Optional[Callable[[str], str]] = None,
    dsa_profile: Optional[LeetCodeProfileSummary] = None,
    dsa_topic: str = "Arrays & Hashing",
) -> TurnResponse:
    """Module-level entrypoint to start a new VivaVoce session."""
    return session_manager.start_session(
        mode=mode,
        repo_index=repo_index,
        paper_index=paper_index,
        selected_author=selected_author,
        audio_synthesizer=audio_synthesizer,
        dsa_profile=dsa_profile,
        dsa_topic=dsa_topic,
    )


def process_turn(
    session_id: str,
    student_text: Optional[str] = None,
    code_result: Optional[RunCodeResponse] = None,
    selected_author: Optional[str] = None,
    audio_synthesizer: Optional[Callable[[str], str]] = None,
) -> TurnResponse:
    """Module-level entrypoint to process a student turn in an active session."""
    return session_manager.process_turn(
        session_id=session_id,
        student_text=student_text,
        code_result=code_result,
        selected_author=selected_author,
        audio_synthesizer=audio_synthesizer,
    )
