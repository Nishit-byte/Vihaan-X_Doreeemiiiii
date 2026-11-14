"""
Canonical Interface Contract for VivaVoce (backend/models/schemas.py).
Owner: Member 1 (Nishit - Team Lead & AI Brain Engineer)

Locked in Hour 1 so M1, M2, M3, and M4 can develop in parallel with zero merge conflicts.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


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
    starter_code: str = Field(default="", description="Code snippet or full file with the bug / mutation")
    test_code: str = Field(default="", description="pytest snippet executed by sandbox_runner.py")


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
    label: str = Field(..., description="Short human-readable stage title")
    section: Optional[str] = None
    excerpt: str = Field(..., description="2-sentence verbatim excerpt from the paper")


class PaperIndex(BaseModel):
    title: str
    mermaid_graph: str = Field(..., description="Mermaid flowchart TD definition with N1..N8")
    nodes: List[PaperNode] = Field(default_factory=list)
    node_excerpts: Dict[str, str] = Field(default_factory=dict)
    full_text_summary: str = ""


# ============================================================================
# SANDBOX EXECUTION MODELS (M1 <-> M2 <-> M4)
# ============================================================================

class OATestCase(BaseModel):
    stdin: str
    expected_output: str
    is_hidden: bool = False


class TestCaseResult(BaseModel):
    case_num: int
    stdin: str
    expected_output: str
    actual_output: str
    passed: bool
    is_hidden: bool = False
    error: Optional[str] = None


class RunCodeRequest(BaseModel):
    session_id: str
    file_path: Optional[str] = "main.py"
    student_code: Optional[str] = None
    source_code: Optional[str] = None
    language: str = "python"
    test_code: Optional[str] = None
    test_cases: List[OATestCase] = Field(default_factory=list)
    run_hidden: bool = False
    custom_input: Optional[str] = None


class RunCodeResponse(BaseModel):
    passed: bool
    verdict: str = "Accepted"
    stdout: str
    stderr: str
    runtime_ms: int
    test_results: List[TestCaseResult] = Field(default_factory=list)
    total_cases: int = 0
    passed_cases: int = 0


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
    selected_author: Optional[str] = Field(
        default=None,
        description="Optional git blame contributor filter"
    )
    code_result: Optional[RunCodeResponse] = Field(
        default=None,
        description="Optional result from live sandbox pytest run"
    )


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
    dsa_profile: Optional[LeetCodeProfileSummary] = None
    initial_turn: TurnResponse


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
    fluency_audit_note: str = (
        "Fluency & Accent Weight: 0% — Graded strictly on technical semantics, "
        "AST-grounded reasoning, and empirical code execution (Koenecke et al., PNAS 2020)."
    )


# ============================================================================
# LEETCODE TELEMETRY & ADAPTIVE OA GENERATOR SCHEMAS
# ============================================================================

class SkillTagStat(BaseModel):
    tag_name: str
    problems_solved: int
    tier: Literal["Fundamental", "Intermediate", "Advanced"]


class OAExample(BaseModel):
    input: str
    output: str
    explanation: Optional[str] = None


class OAQuestion(BaseModel):
    question_id: str = Field(..., description="Unique question identifier, e.g. OA-1")
    title: str
    difficulty: Literal["Easy", "Medium", "Hard"]
    topics: List[str] = Field(default_factory=list)
    selection_reason: str = Field(
        ...,
        description="Explicit citation of why this question was chosen from Category 1 solved titles or Category 2 topic counts",
    )
    problem_statement: str
    examples: List[OAExample] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    starter_code: Optional[str] = None
    test_code: Optional[str] = None
    test_cases: List[OATestCase] = Field(default_factory=list)


class LeetCodeProfileData(BaseModel):
    username: str
    category: Literal["PUBLIC_SOLVED_LIST", "HIDDEN_TOPIC_COUNTS_ONLY"]
    primary_language: str
    total_solved: int
    easy_solved: int
    medium_solved: int
    hard_solved: int
    recent_ac_titles: List[str] = Field(default_factory=list)
    skill_tags: List[SkillTagStat] = Field(default_factory=list)


class IngestLeetCodeRequest(BaseModel):
    username_or_url: str
    num_easy: int = 1
    num_medium: int = 2
    num_hard: int = 2


class IngestLeetCodeResponse(BaseModel):
    session_id: str
    profile: LeetCodeProfileData
    oa_questions: List[OAQuestion]
    initial_turn: TurnResponse

