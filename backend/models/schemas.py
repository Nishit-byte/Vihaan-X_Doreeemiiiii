"""
Canonical Interface Contract for VivaVoce (backend/models/schemas.py).
Owner: Member 1 (Nishit - Team Lead & AI Brain Engineer)

Locked in Hour 1 so M1, M2, M3, and M4 can develop in parallel with zero merge conflicts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


# ============================================================================
# SHARED CORE ARTIFACTS (Used across Brain, Ingestion, Sandbox, Voice & UI)
# ============================================================================

class CodeHighlight(BaseModel):
    file_path: str = Field(..., description="Relative file path inside the repository")
    line_start: int = Field(..., ge=1, description="1-based start line number")
    line_end: int = Field(..., ge=1, description="1-based inclusive end line number")


class CodingChallenge(BaseModel):
    description: str = Field(..., description="Explanation of the edge-case or mutation bug to fix")
    target_file: str = Field(..., description="File path where the student should apply the fix")
    starter_code: str = Field(..., description="Code snippet or full file with the bug / mutation")
    test_code: str = Field(..., description="pytest snippet executed by sandbox_runner.py")


# ============================================================================
# INGESTION INDEX MODELS (Produced by M2, Consumed by M1 & M4)
# ============================================================================

class ASTFunctionSymbol(BaseModel):
    name: str
    file_path: str
    line_start: int
    line_end: int
    args: List[str] = Field(default_factory=list)
    docstring: Optional[str] = None
    calls: List[str] = Field(default_factory=list)
    constants: List[str] = Field(default_factory=list)
    code_snippet: Optional[str] = None


class OwnedSymbol(BaseModel):
    file_path: str
    line_start: int
    line_end: int
    symbol_name: Optional[str] = None
    commit_count: int = 1


class RepoFile(BaseModel):
    path: str
    content: str
    language: str = "python"
    line_count: int = 0


class RepoIndex(BaseModel):
    repo_name: str
    github_url: str
    local_path: Optional[str] = None
    files: List[RepoFile] = Field(default_factory=list)
    symbols: List[ASTFunctionSymbol] = Field(default_factory=list)
    authors: List[str] = Field(default_factory=list)
    author_map: Dict[str, List[OwnedSymbol]] = Field(default_factory=dict)
    summary: str = ""


class PaperNode(BaseModel):
    node_id: str = Field(..., description="Mermaid node ID, e.g. N1..N8")
    label: str = Field(..., description="Short human-readable functional stage title")
    summary: Optional[str] = Field(default=None, description="Plain-language explanation of what this stage does")
    section: Optional[str] = None
    page: int = Field(default=1, ge=1, description="1-based PDF page number")
    excerpt: str = Field(..., description="Verbatim supporting excerpt from the paper")


class EvidenceRef(BaseModel):
    id: str
    label: str
    claim_or_insight: str
    source_type: Literal["author_claim", "app_interpretation"] = "author_claim"
    excerpt: str
    page: int = 1
    section: str = "Paper overview"


class BreakdownField(BaseModel):
    content: str = "Not found in the paper"
    plain_language: Optional[str] = None
    interpretation: Optional[str] = None
    source_type: Literal["author_claim", "app_interpretation"] = "author_claim"
    page: Optional[int] = None
    section: Optional[str] = None
    excerpt: Optional[str] = None
    found: bool = False


class MethodologyStep(BaseModel):
    step_number: int
    node_id: Optional[str] = None
    title: str
    description: str
    plain_language: Optional[str] = None
    source_type: Literal["author_claim", "app_interpretation"] = "author_claim"
    page: int = 1
    section: str = "Methodology"
    excerpt: str


class ResultDataPoint(BaseModel):
    metric: str
    comparison_context: Optional[str] = None
    baseline_label: Optional[str] = None
    baseline_value: Optional[float] = None
    proposed_label: str = "Proposed"
    proposed_value: float
    unit: str = ""
    page: int = 1
    excerpt: str


class GlossaryItem(BaseModel):
    term: str
    definition: str
    source_type: Literal["author_defined", "app_interpretation"] = "app_interpretation"
    page: int = 1
    excerpt: str


class PaperVivaQuestion(BaseModel):
    id: str
    category: Literal[
        "Basic understanding",
        "Methodology & design choices",
        "Results & evidence",
        "Limitations & trade-offs",
        "What would change if...",
    ]
    question: str
    why_asked: str
    page: int = 1
    section: str = "Paper overview"
    excerpt: str


class PaperBreakdown(BaseModel):
    title: str
    title_status: Literal["verified", "uncertain"] = "verified"
    authors_and_affiliations: str = "Not found in the paper"
    authors_status: Literal["identified", "uncertain", "not_found"] = "not_found"
    venue_and_year: str = "Not found in the paper"
    title_block_excerpt: Optional[str] = None
    what_this_paper_does: str
    what_this_paper_does_plain: Optional[str] = None
    extraction_status: Literal["ok", "scanned_or_empty", "partial"] = "ok"
    extraction_warning: Optional[str] = None
    page_count: int = 1
    methodology_diagram_status: Literal["ok", "fallback"] = "ok"
    methodology_diagram_note: Optional[str] = None
    diagram_provenance: Literal[
        "Reconstructed from the paper", "Conceptual explanation"
    ] = "Reconstructed from the paper"
    story_map_provenance: Literal[
        "Reconstructed from the paper", "Conceptual explanation"
    ] = "Conceptual explanation"
    abstract_summary: BreakdownField
    problem_and_significance: BreakdownField
    research_objective: BreakdownField
    background_and_prior_work: BreakdownField
    proposed_method: BreakdownField
    step_by_step_methodology: List[MethodologyStep] = Field(default_factory=list)
    data_setup_and_metrics: BreakdownField
    main_results: BreakdownField
    results_summary_note: Optional[str] = None
    contributions: BreakdownField
    limitations_and_assumptions: BreakdownField
    implications_and_future_work: BreakdownField
    key_takeaways: List[EvidenceRef] = Field(default_factory=list)
    story_map: List[EvidenceRef] = Field(default_factory=list)
    sections_index: List[EvidenceRef] = Field(default_factory=list)
    quantitative_results: List[ResultDataPoint] = Field(default_factory=list)
    glossary: List[GlossaryItem] = Field(default_factory=list)
    viva_questions: List[PaperVivaQuestion] = Field(default_factory=list)


class PaperIndex(BaseModel):
    title: str
    mermaid_graph: str = Field(..., description="Mermaid flowchart TD definition with N1..N8")
    nodes: List[PaperNode] = Field(default_factory=list)
    node_excerpts: Dict[str, str] = Field(default_factory=dict)
    full_text_summary: str = ""
    breakdown: Optional[PaperBreakdown] = None


# ============================================================================
# SANDBOX EXECUTION MODELS (M1 <-> M2 <-> M4)
# ============================================================================

class RunCodeRequest(BaseModel):
    session_id: str
    file_path: str
    student_code: str
    test_code: Optional[str] = None


class RunCodeResponse(BaseModel):
    passed: bool
    stdout: str
    stderr: str
    runtime_ms: int


# ============================================================================
# VIVA TURN MODELS (M1 <-> M3 <-> M4)
# ============================================================================

VerdictType = Literal["start", "strong", "partial", "weak", "no_answer"]


class TurnRequest(BaseModel):
    session_id: str
    student_text: Optional[str] = Field(
        default=None,
        description="Direct text answer (if typed or pre-transcribed)"
    )
    audio_base64: Optional[str] = Field(
        default=None,
        description="Base64-encoded WebM/WAV audio from browser MediaRecorder"
    )
    audio_mime: Optional[str] = Field(
        default=None,
        description="Optional audio MIME type from browser MediaRecorder"
    )
    selected_author: Optional[str] = Field(
        default=None,
        description="Optional git blame contributor filter"
    )
    code_result: Optional[RunCodeResponse] = Field(
        default=None,
        description="Optional result from live sandbox pytest run"
    )


VivaTurnRequest = TurnRequest


class TurnResponse(BaseModel):
    session_id: str
    student_transcript: str
    verdict: VerdictType
    ack_text: str  # e.g., 'Good point on cosine similarity.'
    question_text: str  # Shown as text AND spoken aloud
    audio_base64: str  # MP3/WAV bytes encoded as base64 for instant playback
    topic: str
    depth_level: int = Field(..., ge=1, le=4)  # 1 (Recall) to 4 (Edge Case / Mutation)
    highlight: Optional[CodeHighlight] = None
    diagram_node_id: Optional[str] = None
    paper_excerpt: Optional[str] = None
    coding_challenge: Optional[CodingChallenge] = None
    done: bool = False
    examiner_message: Optional[str] = None
    question: Optional[str] = None
    is_complete: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def sync_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            ack = data.get("ack_text")
            ex_msg = data.get("examiner_message")
            eff_ack = ex_msg if (ex_msg is not None and str(ex_msg).strip()) else (ack or "")
            data["ack_text"] = eff_ack
            data["examiner_message"] = eff_ack

            q_text = data.get("question_text")
            q_alt = data.get("question")
            eff_q = q_alt if (q_alt is not None and str(q_alt).strip()) else (q_text or "")
            data["question_text"] = eff_q
            data["question"] = eff_q

            is_done = data.get("done")
            is_comp = data.get("is_complete")
            eff_done = bool(is_comp if is_comp is not None else is_done)
            data["done"] = eff_done
            data["is_complete"] = eff_done
        return data


# ============================================================================
# INGESTION API REQUEST / RESPONSE MODELS (M1 <-> M4)
# ============================================================================

class IngestRepoRequest(BaseModel):
    github_url: str
    selected_author: Optional[str] = None
    use_demo_cache: bool = False


class LeetCodeProfileSummary(BaseModel):
    username: str
    total_solved: int = 0
    easy_solved: int = 0
    medium_solved: int = 0
    hard_solved: int = 0
    weak_topics: List[str] = Field(default_factory=list)
    recent_submissions: List[str] = Field(default_factory=list)
    fetched_live: bool = False


class IngestDsaRequest(BaseModel):
    leetcode_username: str
    topic: str = "Arrays & Hashing"


class IngestResponse(BaseModel):
    session_id: str
    mode: Literal["repo", "paper", "dsa"]
    title: str
    authors: List[str] = Field(default_factory=list)
    files: List[RepoFile] = Field(default_factory=list)
    mermaid_graph: Optional[str] = None
    paper_nodes: List[PaperNode] = Field(default_factory=list)
    paper_breakdown: Optional[PaperBreakdown] = None
    dsa_profile: Optional[LeetCodeProfileSummary] = None
    initial_turn: TurnResponse
    first_turn: Optional[TurnResponse] = None
    paper: Optional[Any] = None

    @model_validator(mode="before")
    @classmethod
    def sync_first_turn(cls, data: Any) -> Any:
        if isinstance(data, dict):
            init_t = data.get("initial_turn")
            first_t = data.get("first_turn")
            chosen = init_t or first_t
            if chosen is not None:
                data["initial_turn"] = chosen
                data["first_turn"] = chosen
        return data


# ============================================================================
# FINAL COMPETENCY REPORT MODELS (Produced by M1 grader.py, Rendered by M4)
# ============================================================================

class RubricScores(BaseModel):
    clarity: float = Field(..., ge=0, le=100, description="Conceptual Clarity (30% weight)")
    trade_offs: float = Field(..., ge=0, le=100, description="Design Trade-offs (25% weight)")
    edge_cases: float = Field(..., ge=0, le=100, description="Edge Case Awareness (20% weight)")
    code_execution: float = Field(..., ge=0, le=100, description="Empirical Sandbox Verification (15% weight)")
    depth: float = Field(..., ge=0, le=100, description="Cognitive Bloom Depth L1-L4 (10% weight)")


class TopicDepthItem(BaseModel):
    topic: str
    max_depth_reached: int = Field(..., ge=1, le=4)
    verdict_summary: str


class CodeVerificationSummary(BaseModel):
    challenge_description: str
    target_file: str
    passed: bool
    runtime_ms: int


class VivaReport(BaseModel):
    session_id: str
    mode: Literal["repo", "paper", "dsa"]
    candidate_name: Optional[str] = None
    overall_score: float = Field(..., ge=0, le=100)
    rubric_scores: RubricScores
    topic_depths: List[TopicDepthItem] = Field(default_factory=list)
    code_challenges: List[CodeVerificationSummary] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    study_plan: List[str] = Field(default_factory=list)
    closing_remark: Optional[str] = None
    audio_base64: Optional[str] = None
    fluency_audit_note: str = (
        "Fluency & Accent Weight: 0% — Graded strictly on technical semantics, "
        "AST-grounded reasoning, and empirical code execution (Koenecke et al., PNAS 2020)."
    )
