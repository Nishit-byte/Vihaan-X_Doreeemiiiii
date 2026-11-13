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


class IngestResponse(BaseModel):
    session_id: str
    mode: Literal["repo", "paper"]
    title: str
    authors: List[str] = Field(default_factory=list)
    files: List[RepoFile] = Field(default_factory=list)
    mermaid_graph: Optional[str] = None
    paper_nodes: List[PaperNode] = Field(default_factory=list)
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
    mode: Literal["repo", "paper"]
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
