"""
Fluency-Blind Semantic Grader & Depth Radar Calculator (backend/brain/grader.py).
Owner: Member 1 (Nishit - Team Lead & AI Brain Engineer)

Theoretical Grounding:
- Koenecke et al. (PNAS 2020), Racial disparities in automated speech recognition (0% weight to ASR WER/accent/grammar)
- Anderson & Krathwohl (2001), Revised Bloom's Taxonomy L1-L4 cognitive depth radar
- Chen et al. (OpenAI 2021), Empirical Pass@k sandbox execution verification

Rubric Weights:
- Clarity: 30%
- Trade-offs: 25%
- Edge Cases: 20%
- Code Execution: 15%
- Depth: 10%
"""

from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

from backend.brain.prompts import FLUENCY_BLIND_GRADER_PROMPT
from backend.brain.state_machine import (
    SESSIONS,
    TurnRecord,
    VivaSession,
    _call_gemini_json,
    clean_asr_transcript,
)
from backend.models.schemas import (
    CodeVerificationSummary,
    RubricScores,
    TopicDepthItem,
    VivaReport,
)

# Canonical rubric weights from Section 5
RUBRIC_WEIGHTS = {
    "clarity": 0.30,
    "trade_offs": 0.25,
    "edge_cases": 0.20,
    "code_execution": 0.15,
    "depth": 0.10,
}

VERDICT_NUMERIC_MAP = {
    "strong": 92.0,
    "partial": 72.0,
    "weak": 45.0,
    "no_answer": 20.0,
    "start": 75.0,
}


def compute_weighted_overall_score(scores: RubricScores) -> float:
    """Computes the exact weighted sum: 30% Clarity + 25% Trade-offs + 20% Edge Cases + 15% Execution + 10% Depth."""
    raw = (
        scores.clarity * RUBRIC_WEIGHTS["clarity"]
        + scores.trade_offs * RUBRIC_WEIGHTS["trade_offs"]
        + scores.edge_cases * RUBRIC_WEIGHTS["edge_cases"]
        + scores.code_execution * RUBRIC_WEIGHTS["code_execution"]
        + scores.depth * RUBRIC_WEIGHTS["depth"]
    )
    return round(max(0.0, min(100.0, raw)), 1)


def _aggregate_deterministic_metrics(session: VivaSession) -> VivaReport:
    """
    Calculates deterministic fluency-blind rubric scores, topic depth radar items,
    and actionable study recommendations directly from session turns and pytest sandbox logs.
    """
    answered_turns: List[TurnRecord] = [
        t for t in session.turns if t.verdict != "start" or t.student_clean_transcript
    ]

    if not answered_turns:
        verdict_scores = [75.0]
    else:
        verdict_scores = [VERDICT_NUMERIC_MAP.get(t.verdict, 65.0) for t in answered_turns]

    avg_verdict_score = sum(verdict_scores) / len(verdict_scores)
    max_depth = max((t.depth_level for t in session.turns), default=1)

    # 1. Clarity (30%): Grounded in L1/L2 conceptual explanations (stripped of ASR fillers)
    l1_l2_scores = [
        VERDICT_NUMERIC_MAP.get(t.verdict, 70.0)
        for t in answered_turns
        if t.depth_level in (1, 2)
    ] or verdict_scores
    clarity_score = round(sum(l1_l2_scores) / len(l1_l2_scores), 1)

    # 2. Trade-offs (25%): Grounded in L2/L3 architectural and complexity reasoning
    l2_l3_scores = [
        VERDICT_NUMERIC_MAP.get(t.verdict, 70.0)
        for t in answered_turns
        if t.depth_level in (2, 3)
    ] or [avg_verdict_score * 0.95]
    trade_offs_score = round(sum(l2_l3_scores) / len(l2_l3_scores), 1)

    # 3. Edge Cases (20%): Grounded in L3/L4 boundary & failure mode analysis
    l3_l4_scores = [
        VERDICT_NUMERIC_MAP.get(t.verdict, 68.0)
        for t in answered_turns
        if t.depth_level in (3, 4)
    ] or [avg_verdict_score * 0.9]
    edge_cases_score = round(sum(l3_l4_scores) / len(l3_l4_scores), 1)

    # 4. Code Execution (15%): Empirical sandbox pytest verification (or Paper methodological rigor)
    if session.code_results:
        passed_count = sum(1 for r in session.code_results if r.get("passed"))
        code_exec_score = round((passed_count / len(session.code_results)) * 100.0, 1)
    elif session.mode == "paper":
        code_exec_score = round(min(100.0, avg_verdict_score), 1)
    else:
        # No sandbox challenge triggered yet; estimate conservatively from technical verdicts
        code_exec_score = round(min(90.0, avg_verdict_score * 0.92), 1)

    # 5. Cognitive Depth (10%): Max Bloom tier reached (L1=45, L2=65, L3=85, L4=100)
    depth_map = {1: 45.0, 2: 68.0, 3: 86.0, 4: 100.0}
    depth_score = depth_map.get(max_depth, 70.0)

    rubric = RubricScores(
        clarity=clarity_score,
        trade_offs=trade_offs_score,
        edge_cases=edge_cases_score,
        code_execution=code_exec_score,
        depth=depth_score,
    )

    # Topic Depth Radar aggregation (for M4 Recharts RadarChart)
    topic_map: Dict[str, TopicDepthItem] = {}
    for t in session.turns:
        existing = topic_map.get(t.topic)
        summary_label = (
            f"Reached Bloom L{t.depth_level} ({t.verdict.upper()})"
            if t.verdict != "start"
            else f"Examined up to Bloom L{t.depth_level}"
        )
        if existing is None or t.depth_level >= existing.max_depth_reached:
            topic_map[t.topic] = TopicDepthItem(
                topic=t.topic,
                max_depth_reached=t.depth_level,
                verdict_summary=summary_label,
            )

    topic_depths = list(topic_map.values())
    if not topic_depths:
        topic_depths = [
            TopicDepthItem(
                topic=session.title,
                max_depth_reached=max_depth,
                verdict_summary="Initial architectural walk-through completed.",
            )
        ]

    code_summaries = [
        CodeVerificationSummary(
            challenge_description=str(c.get("challenge_description", "L4 Edge-Case Sandbox Check")),
            target_file=str(c.get("target_file", "student_solution.py")),
            passed=bool(c.get("passed", False)),
            runtime_ms=int(c.get("runtime_ms", 0)),
        )
        for c in session.code_results
    ]

    # Try enriching strengths, study_plan, and fine-tuned rubric scores via Gemini 2.5 Flash
    llm_input = {
        "session_id": session.session_id,
        "mode": session.mode,
        "title": session.title,
        "candidate_name": session.selected_author,
        "turns": [
            {
                "turn": t.turn_index,
                "topic": t.topic,
                "depth_level": t.depth_level,
                "question": t.question_text,
                "cleaned_student_answer": clean_asr_transcript(t.student_raw_transcript),
                "verdict": t.verdict,
            }
            for t in session.turns
        ],
        "sandbox_code_results": session.code_results,
        "baseline_rubric": rubric.model_dump(),
    }
    llm_report = _call_gemini_json(
        FLUENCY_BLIND_GRADER_PROMPT, json.dumps(llm_input, indent=2)
    )

    if llm_report and "rubric_scores" in llm_report:
        rs = llm_report["rubric_scores"]
        rubric = RubricScores(
            clarity=float(rs.get("clarity", rubric.clarity)),
            trade_offs=float(rs.get("trade_offs", rubric.trade_offs)),
            edge_cases=float(rs.get("edge_cases", rubric.edge_cases)),
            code_execution=float(rs.get("code_execution", rubric.code_execution)),
            depth=float(rs.get("depth", rubric.depth)),
        )
        if llm_report.get("topic_depths"):
            topic_depths = [
                TopicDepthItem(
                    topic=str(item.get("topic", "Core Module")),
                    max_depth_reached=max(1, min(4, int(item.get("max_depth_reached", 1)))),
                    verdict_summary=str(item.get("verdict_summary", "Evaluated during viva")),
                )
                for item in llm_report["topic_depths"]
            ]
        strengths = [str(s) for s in llm_report.get("strengths", []) if s]
        study_plan = [str(s) for s in llm_report.get("study_plan", []) if s]
    else:
        strengths = []
        study_plan = []

    if not strengths:
        strengths = [
            f"Reached Bloom Cognitive Depth Level L{max_depth} on {topic_depths[0].topic}.",
            "Demonstrated grounded understanding of control flow and component boundaries.",
        ]
        if any(c.passed for c in code_summaries):
            strengths.append(
                "Empirically verified live bug fix inside the isolated pytest execution sandbox."
            )

    if not study_plan:
        study_plan = [
            "Practice articulating asymptotic time/space trade-offs (Bloom Level 3) before jumping to implementation details.",
            "Add defensive unit tests for degenerate boundary inputs (empty collections, None payloads, zero-norm vectors).",
        ]
        if max_depth < 4:
            study_plan.append(
                f"Progress from Level {max_depth} to Level 4 (Mutation & Failure Mode Analysis) by tracing what breaks when invariants are violated."
            )

    overall = compute_weighted_overall_score(rubric)

    return VivaReport(
        session_id=session.session_id,
        mode=session.mode,
        candidate_name=session.selected_author,
        overall_score=overall,
        rubric_scores=rubric,
        topic_depths=topic_depths,
        code_challenges=code_summaries,
        strengths=strengths,
        study_plan=study_plan,
    )


def generate_final_report(
    session_id: str,
    audio_synthesizer: Optional[Callable[[str], str]] = None,
) -> VivaReport:
    """
    Canonical entrypoint for `GET /api/report/{id}`.
    Aggregates turn verdicts, sandbox test results, and cleaned transcripts into a VivaReport.
    """
    if session_id not in SESSIONS:
        raise KeyError(f"Session '{session_id}' not found in SESSIONS store.")

    session = SESSIONS[session_id]
    session.done = True
    report = _aggregate_deterministic_metrics(session)

    closing_text = (
        f"Your technical viva for {session.title} is complete with an overall score of {round(report.overall_score)} out of 100. "
        "Your rubric breakdown and topic depth radar are now available in your final report."
    )
    report.closing_remark = closing_text
    if audio_synthesizer:
        try:
            report.audio_base64 = audio_synthesizer(closing_text)
        except Exception:
            report.audio_base64 = ""
    return report
