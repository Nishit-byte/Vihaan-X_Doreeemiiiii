"""Build deterministic fictional research paper PDF for VivaVoce demo cache.

Generates a 3-4 page fictional lab report:
'Adaptive Spaced Repetition with Peer Matching'
Sections:
- Abstract
- 1 Introduction
- 2 Method (with 6 clear stages: 2.1 to 2.6)
- 3 Evaluation
- 4 Limitations
- References

Uses fpdf2 with built-in fonts only and fixed creation date for 100% deterministic output.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional
from fpdf import FPDF


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_PDF = DEFAULT_OUTPUT_DIR / "sample_paper.pdf"

PAPER_TITLE = "Adaptive Spaced Repetition with Peer Matching"
PAPER_AUTHORS = "Aman Verma, Priya Nair, Rohan Gupta"
PAPER_AFFILIATION = "Department of Computer Science, National Institute of Technology"

SECTIONS_DATA: list[tuple[str, str]] = [
    (
        "Abstract",
        "Spaced repetition systems traditionally optimize long-term memory retention through solitary flashcard reviews scheduled against calibrated forgetting curves. While highly effective for atomic fact retrieval, isolated practice fails to cultivate dialectical defense, trade-off analysis, or deep conceptual explanation under real-time interrogation. In this paper, we introduce Adaptive Spaced Repetition with Peer Matching (ASR-PM), a collaborative learning framework that pairs learners with complementary mastery profiles for synchronous, concept-grounded viva practice sessions.\n\n"
        "Our system constructs a curriculum dependency graph, tracks student memory decay via exponential half-life estimation, and matches learners into reciprocal peer dyads using bipartite complementarity scoring. Over a four-week empirical evaluation with 48 undergraduate computer science students, our approach achieved a 27.4% improvement in analytical explanation scores and a 34.1% reduction in forgetting rate variance compared to standard solitary spaced repetition baselines."
    ),
    (
        "1 Introduction",
        "Mastery in computer science and software engineering requires far more than passive recall of syntax and definitions. Practicing engineers must articulate complex design trade-offs, identify edge cases, explain failure modes, and defend architectural choices under rigorous peer review and technical scrutiny. Traditional computer-assisted study platforms rely heavily on solitary spaced repetition algorithms, such as SuperMemo SM-2 or half-life regression models. While these algorithms schedule individual retrieval practice effectively, solitary study creates an illusion of competence: learners frequently recognize terms and concepts without possessing the ability to explain underlying mechanisms coherently.\n\n"
        "Reciprocal peer instruction offers substantial cognitive benefits by compelling learners to formulate explicit verbal explanations, detect misconceptions, and reconcile conflicting perspectives. Nevertheless, coordinating peer study in educational institutions faces persistent obstacles: student schedules conflict, skill disparities often reduce interactions to one-sided tutoring, and unguided discussions frequently drift off-topic.\n\n"
        "To overcome these limitations, we design and implement Adaptive Spaced Repetition with Peer Matching (ASR-PM). ASR-PM coordinates structured, 15-minute peer viva sessions anchored directly in curriculum dependency graphs. By pairing students based on asymmetric concept mastery, the system guarantees reciprocal dialogue where participants alternate between the roles of examiner and candidate, ensuring balanced collaborative reinforcement across the entire curriculum."
    ),
    (
        "2 Method",
        "The ASR-PM architecture consists of six continuous functional stages designed to transform curriculum ontologies and student interaction telemetry into structured peer viva examinations. The pipeline integrates offline dependency indexing with online matching and bayesian performance updating."
    ),
    (
        "2.1 Concept Knowledge Graph Construction",
        "We construct a directed concept knowledge graph from the curriculum ontology where vertices represent granular technical concepts and directed edges denote prerequisite dependencies. Topological ordering over this graph ensures that foundational competencies are scheduled before advanced downstream topics. Each node stores pedagogical metadata including reference code snippets, common antipatterns, and calibrated difficulty ratings.\n\n"
        "The graph structure enforces strict transitive prerequisite validation before any node is marked eligible for peer examination. When a syllabus module is updated, an automated AST parser scans repository milestones and problem sets to extract symbol dependencies, updating topological weights and prerequisite chains across the graph."
    ),
    (
        "2.2 Dynamic Memory Decay Modeling",
        "Student retention probability for each concept node is modeled using a modified half-life exponential decay function calibrated by historical retrieval latency. The decay parameter dynamically updates after each review session to reflect individual consolidation rates. Let R_i(t) denote the recall probability of concept i at elapsed time t since the last review.\n\n"
        "When R_i(t) approaches the critical retrieval threshold of 0.65, the concept enters the student active review candidate queue. Unlike univariate spaced repetition models, our decay formulation incorporates cross-concept interference penalties derived from topological graph proximity, ensuring that related concepts with competing memory representations receive accelerated review scheduling."
    ),
    (
        "2.3 Peer Complementarity Scoring",
        "A multi-factor affinity metric computes bipartite complementarity between student pairs based on orthogonal mastery profiles. Pairs with asymmetric knowledge distributions yield significantly higher collaborative reinforcement than homogeneous groupings. Specifically, given student A with high mastery in concept X and emerging mastery in concept Y, the matching engine searches for peer B exhibiting inverted mastery coordinates.\n\n"
        "An alignment weight penalizes scheduling latency while rewarding cognitive tension, guaranteeing balanced reciprocal dialogue rather than unilateral tutoring. Complementarity scores are normalized between zero and one, incorporating historical rating variance and peer feedback reliability factors to prevent persistent mismatching."
    ),
    (
        "2.4 Synchronous Pairing and Session Scheduling",
        "The matching engine solves a constrained maximum-weight bipartite matching problem to allocate learners into synchronous 15-minute viva practice rooms. A greedy priority queue handles real-time arrivals while enforcing constraints on mutual availability. When matching candidates arrive asynchronously within a 5-minute scheduling window, Edmonds blossom algorithm computes optimal pairings that maximize global cohort complementarity.\n\n"
        "Sessions are bounded by strict countdown timers to maintain high cognitive cadence and prevent fatigue. The scheduling subsystem dynamically dispatches web socket notification payloads to both participants upon room allocation, providing seamless transition from queue to active dialogue."
    ),
    (
        "2.5 Collaborative Question Generation",
        "An LLM-driven scaffold synthesizes personalized technical prompts targeted at the intersection of one peer strength and the other retention deficit. Prompts enforce reciprocal interrogation where each partner alternates between examiner and candidate roles. For each concept turn, the system displays code highlights or architecture diagrams to the designated student while providing the peer examiner with rubric checkpoints and probing follow-up questions.\n\n"
        "This structured scaffolding prevents topic drift and anchors discourse in concrete technical artifacts. Probing prompts are stratified across Bloom taxonomy levels, escalating from fundamental comprehension checks to complex mutation and trade-off challenges."
    ),
    (
        "2.6 Dual-Feedback Performance Update",
        "Following the session, both explicit rubric ratings and implicit response latency signals update the bayesian mastery estimators for both participants. Posterior mastery values are propagated backward through the concept graph to adjust subsequent spacing intervals. If a candidate demonstrates robust analytical depth on an edge-case challenge, the half-life parameter of all prerequisite concept nodes is extended.\n\n"
        "Conversely, failure on foundational concepts triggers immediate remedial re-queuing within 48 hours. Both qualitative verbal notes and quantitative rubric ticks are logged into persistent student profiles, establishing longitudinal calibration curves across multi-week instructional units."
    ),
    (
        "3 Evaluation",
        "We conducted a four-week controlled trial comparing ASR-PM against solitary flashcard spaced repetition (Baseline A) and unstructured peer discussion (Baseline B). A cohort of 48 undergraduate computer science students was partitioned into three counterbalanced groups of 16 participants each. All participants completed identical pre-test and post-test assessments covering distributed consensus, synchronization primitives, and concurrent data structures.\n\n"
        "Our evaluation measured conceptual explanation depth graded on Bloom taxonomy (L1 Recall to L4 Evaluation), four-week retention stability, and session completion rates. Students in the ASR-PM condition achieved a mean Bloom depth score of 3.42 out of 4.0, representing a 27.4% improvement over solitary spaced repetition (2.68) and a 19.8% improvement over unstructured peer discussion (2.85).\n\n"
        "Furthermore, retention decay variance across the cohort decreased by 34.1%, confirming that reciprocal peer interrogation mitigates individual forgetting curves. Voluntary session completion was 91.2% in the ASR-PM group compared to 64.5% in the unstructured discussion baseline, demonstrating superior student engagement."
    ),
    (
        "4 Limitations",
        "Several practical limitations of our framework warrant consideration. First, the peer matching algorithm requires a minimum concurrent user pool density to discover complementary dyads within acceptable wait times (< 3 minutes); in low-density settings, matching quality degrades toward random pairing.\n\n"
        "Second, the automated question generator relies on well-structured syllabus ontologies, requiring initial curriculum engineering effort. Finally, our current trial evaluated synchronous interactions in controlled lab settings; noisy network environments or asynchronous modalities may introduce coordination overhead that dampens collaborative efficacy."
    ),
    (
        "References",
        "[1] Ebbinghaus, H. Memory: A Contribution to Experimental Psychology. Teachers College, Columbia University, 1913.\n"
        "[2] Mazur, E. Peer Instruction: A User Manual. Prentice Hall, Upper Saddle River, NJ, 1997.\n"
        "[3] Settles, B., & Meeder, B. A trainable spaced repetition model for language learning. In Proceedings of the 54th Annual Meeting of the ACL, pp. 1848-1858, 2016.\n"
        "[4] Chi, M. T., & Wylie, R. The ICAP framework: Linking cognitive engagement to active learning outcomes. Educational Psychologist, 49(4), 219-243, 2014.\n"
        "[5] Koenecke, A., et al. Racial disparities in automated speech recognition. Proceedings of the National Academy of Sciences (PNAS), 117(14), 7684-7689, 2020.\n"
        "[6] Bloom, B. S. Taxonomy of Educational Objectives: The Classification of Educational Goals. Longmans, Green, 1956."
    ),
]


def build_sample_paper(output_path: Optional[str | Path] = None) -> bytes:
    """Generate deterministic fictional research paper PDF and optionally save to disk."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    # Fixed timestamp ensures 100% deterministic binary output across builds
    pdf.set_creation_date(datetime.datetime(2026, 1, 1, 0, 0, 0))
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title block (Page 1)
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(
        pdf.epw, 10, PAPER_TITLE, align="C", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.ln(4)

    # Authors and affiliations
    pdf.set_font("Helvetica", "I", 11)
    author_block = f"{PAPER_AUTHORS}\n{PAPER_AFFILIATION}"
    pdf.multi_cell(
        pdf.epw, 6, author_block, align="C", new_x="LMARGIN", new_y="NEXT"
    )
    pdf.ln(8)

    # Sections
    for heading, content in SECTIONS_DATA:
        # Level 1 headings: 13pt bold; Level 2 subheadings (e.g. 2.1): 11pt bold
        is_subheading = "." in heading.split()[0] if heading.split() else False
        heading_size = 11 if is_subheading else 13
        pdf.set_font("Helvetica", "B", heading_size)
        pdf.multi_cell(
            pdf.epw, 7, heading, new_x="LMARGIN", new_y="NEXT"
        )
        pdf.ln(1)

        # Body paragraphs: 10pt regular
        pdf.set_font("Helvetica", "", 10)
        paragraphs = content.split("\n\n")
        for para in paragraphs:
            pdf.multi_cell(
                pdf.epw, 5.2, para.strip(), new_x="LMARGIN", new_y="NEXT"
            )
            pdf.ln(2.5)
        pdf.ln(2.5)

    pdf_bytes = bytes(pdf.output())

    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf_bytes)

    return pdf_bytes


if __name__ == "__main__":
    out = build_sample_paper(DEFAULT_OUTPUT_PDF)
    print(f"Generated sample_paper.pdf ({len(out)} bytes) at {DEFAULT_OUTPUT_PDF}")
