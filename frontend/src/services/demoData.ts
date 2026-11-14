// Offline fallback so the demo survives a dead backend or venue Wi-Fi.
import type {
  CodingChallenge, IngestResponse, PaperBreakdown, PaperNodeMeta, RunCodeRequest, RunCodeResponse, TurnRequest,
  TurnResponse, VivaReport,
} from '../types/api'

const SIMILARITY = `import math
from typing import List


def dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(a: List[float]) -> float:
    return math.sqrt(dot(a, a))


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Return cosine similarity of two equal-length vectors."""
    return dot(a, b) / (norm(a) * norm(b))
`

const RANKER = `from similarity import cosine_similarity


def rank(query, docs, k=3):
    scored = [(cosine_similarity(query, d["vec"]), d["id"]) for d in docs]
    scored.sort(reverse=True)
    return scored[:k]
`

const TESTS = `from similarity import cosine_similarity


def test_zero_vector():
    assert cosine_similarity([0, 0], [1, 2]) == 0.0


def test_identical():
    assert abs(cosine_similarity([1, 2], [1, 2]) - 1.0) < 1e-9
`

const TWO_SUM_STARTER = `def two_sum(nums, target):
    """Return [i, j] with nums[i] + nums[j] == target, or [] if none."""
    raise NotImplementedError
`
const TWO_SUM_TESTS = `from two_sum import two_sum


def test_basic():
    assert sorted(two_sum([2, 7, 11, 15], 9)) == [0, 1]


def test_no_match():
    assert two_sum([1, 2], 10) == []


def test_duplicates():
    assert sorted(two_sum([3, 3], 6)) == [0, 1]
`
const TOPK_STARTER = `def top_k(scores, k):
    """Return indices of the k highest scores, best first."""
    raise NotImplementedError
`
const TOPK_TESTS = `from topk import top_k


def test_basic():
    assert top_k([0.1, 0.9, 0.4], 2) == [1, 2]


def test_empty():
    assert top_k([], 3) == []


def test_zero_k():
    assert top_k([0.5], 0) == []
`
const ZERO_CHALLENGE: CodingChallenge = {
  description: 'Make cosine_similarity return 0.0 when either vector has zero length.',
  target_file: 'similarity.py', starter_code: SIMILARITY, test_code: TESTS,
}
const DSA_CHALLENGE: CodingChallenge = {
  description: 'Implement two_sum(nums, target): return the indices of the two numbers that add up to target, or [] if none exist. Aim for O(n) time.',
  target_file: 'two_sum.py', starter_code: TWO_SUM_STARTER, test_code: TWO_SUM_TESTS,
}
const TOPK_CHALLENGE: CodingChallenge = {
  description: 'Implement top_k(scores, k): return the indices of the k highest scores, best first. This is the selection step of the top-k retriever.',
  target_file: 'topk.py', starter_code: TOPK_STARTER, test_code: TOPK_TESTS,
}

const MERMAID = `flowchart TD
  N1["Ingest Metadata-Tagged Docs"] --> N2["Create Overlapping Chunks"]
  N2 --> N3["Build Dense Vector Index"]
  N3 --> N4["Retrieve Top-k Passages"]
  N4 --> N5["Generate Context-Only Answer"]
  N5 --> N6["Attach Chunk Citations"]`

const NODES: Record<string, string> = {
  N1: 'The corpus is split into source documents before any processing. Each document keeps its metadata so answers can be traced back.',
  N2: 'Documents are cut into overlapping chunks and embedded with a sentence encoder. Overlap keeps context that would otherwise be split at a boundary.',
  N3: 'All chunk embeddings are stored in a vector index. The index supports approximate nearest-neighbour search.',
  N4: 'At query time the question is embedded and the k closest chunks are retrieved. The value of k trades recall against prompt length.',
  N5: 'The generator receives the question and retrieved chunks in one prompt. It is instructed to answer only from the supplied context.',
  N6: 'The final answer cites the chunks it used. Citations let a reader verify each claim.',
}

const NODE_META: Record<string, PaperNodeMeta> = {
  N1: { node_id: 'N1', label: 'Ingest Metadata-Tagged Docs', summary: 'Split the raw corpus into documents while keeping source IDs and section titles.', section: 'Abstract & Corpus', page: 1, excerpt: NODES.N1 },
  N2: { node_id: 'N2', label: 'Create Overlapping Chunks', summary: 'Slice each document using sliding windows so sentences near cut points stay whole.', section: 'Methodology — Chunking', page: 2, excerpt: NODES.N2 },
  N3: { node_id: 'N3', label: 'Build Dense Vector Index', summary: 'Encode chunks into embeddings and store them in a fast approximate nearest-neighbour index.', section: 'Methodology — Indexing', page: 2, excerpt: NODES.N3 },
  N4: { node_id: 'N4', label: 'Retrieve Top-k Passages', summary: 'Match each query embedding against the index and fetch the top k most relevant chunks.', section: 'Methodology — Retrieval', page: 3, excerpt: NODES.N4 },
  N5: { node_id: 'N5', label: 'Generate Context-Only Answer', summary: 'Prompt the LLM with only the retrieved chunks and instruct it not to use outside memory.', section: 'Evaluation & Grounding', page: 3, excerpt: NODES.N5 },
  N6: { node_id: 'N6', label: 'Attach Chunk Citations', summary: 'Link every output claim back to the chunk IDs that supplied the supporting facts.', section: 'Results & Discussion', page: 4, excerpt: NODES.N6 },
}

const DEMO_PAPER_BREAKDOWN: PaperBreakdown = {
  extraction_status: 'ok',
  extraction_notice: null,
  page_count: 4,
  title: 'Dense Passage Retrieval and Citation-Grounded Generation for Technical QA',
  title_status: 'verified',
  authors_and_affiliations: {
    label: 'Authors & Affiliations',
    value: 'A. Sharma, R. Verma, K. Iyer — Systems & Information Retrieval Lab',
    found: true,
    origin: 'author_claim',
    page: 1,
    section: 'Title & Header',
    supporting_excerpt: 'Dense Passage Retrieval and Citation-Grounded Generation for Technical QA — A. Sharma, R. Verma, K. Iyer (Systems & Information Retrieval Lab).',
  },
  authors_status: 'identified',
  venue_and_year: {
    label: 'Publication Venue & Year',
    value: 'Workshop on Grounded Language Systems (2024)',
    found: true,
    origin: 'author_claim',
    page: 1,
    section: 'Title & Header',
    supporting_excerpt: 'Workshop on Grounded Language Systems, 2024.',
  },
  title_block_excerpt: 'Dense Passage Retrieval and Citation-Grounded Generation for Technical QA\nA. Sharma, R. Verma, K. Iyer\nSystems & Information Retrieval Lab · Workshop on Grounded Language Systems, 2024',
  what_this_paper_does: {
    label: 'What This Paper Does',
    value: 'The paper constructs a six-stage document retrieval and citation pipeline that splits technical documents into overlapping segments, indexes dense sentence embeddings, retrieves the top-k passages, and restricts generation to cited context.',
    found: true,
    origin: 'app_interpretation',
    page: 1,
    section: 'Abstract',
    supporting_excerpt: NODES.N1 + ' ' + NODES.N6,
    plain_language: 'Instead of letting an AI answer from guesswork, this paper splits documents into overlapping snippets, retrieves the k closest matches for a question, and forces the answer to cite those exact snippets.',
  },
  abstract_summary: {
    label: 'Abstract',
    value: 'The corpus is segmented into overlapping chunks, embedded into an approximate nearest-neighbour index, and queried with top-k retrieval to constrain language generation to verifiable citations.',
    found: true,
    origin: 'author_claim',
    page: 1,
    section: 'Abstract',
    supporting_excerpt: NODES.N1 + ' ' + NODES.N2 + ' ' + NODES.N6,
    plain_language: 'In plain terms, overlapping snippets prevent sentences from getting cut in half, and strict prompt rules ensure every generated claim points back to a source passage.',
  },
  problem_and_importance: {
    label: 'Problem Addressed & Why It Matters',
    value: 'Standalone language models hallucinate unverified claims and lose provenance when answering detailed technical questions across large document corpora, and naive fixed-size splitting breaks context at chunk boundaries.',
    found: true,
    origin: 'author_claim',
    page: 1,
    section: 'Introduction',
    supporting_excerpt: NODES.N2,
  },
  research_objective: {
    label: 'Research Objective / Question',
    value: 'Determine how overlapping chunking and top-k dense vector retrieval affect answer faithfulness, recall, and latency in citation-grounded generation.',
    found: true,
    origin: 'author_claim',
    page: 1,
    section: 'Introduction',
    supporting_excerpt: NODES.N4,
  },
  background_prior_work: {
    label: 'Background & Prior Work',
    value: 'Builds upon sparse lexical retrieval (BM25), bi-encoder dense passage retrieval, and approximate nearest-neighbour (ANN) vector indices.',
    found: true,
    origin: 'author_claim',
    page: 2,
    section: 'Background',
    supporting_excerpt: NODES.N3,
  },
  proposed_method: {
    label: 'Proposed Method / Approach',
    value: 'A 6-stage retrieval-and-citation pipeline: Document Ingestion (N1) -> Overlapping Chunking & Sentence Embedding (N2) -> ANN Vector Index (N3) -> Top-k Retriever (N4) -> Context-Constrained Generator LLM (N5) -> Cited Answer Output (N6).',
    found: true,
    origin: 'author_claim',
    page: 2,
    section: 'Methodology',
    supporting_excerpt: NODES.N2 + ' ' + NODES.N4 + ' ' + NODES.N5,
  },
  step_by_step_methodology: [
    { step_number: 1, node_id: 'N1', title: 'Input documents', summary: NODES.N1, origin: 'author_claim', page: 1, section: 'Abstract & Corpus', excerpt: NODES.N1 },
    { step_number: 2, node_id: 'N2', title: 'Chunking and embedding', summary: NODES.N2, origin: 'author_claim', page: 2, section: 'Methodology — Chunking', excerpt: NODES.N2 },
    { step_number: 3, node_id: 'N3', title: 'Vector index', summary: NODES.N3, origin: 'author_claim', page: 2, section: 'Methodology — Indexing', excerpt: NODES.N3 },
    { step_number: 4, node_id: 'N4', title: 'Top-k retriever', summary: NODES.N4, origin: 'author_claim', page: 3, section: 'Methodology — Retrieval', excerpt: NODES.N4 },
    { step_number: 5, node_id: 'N5', title: 'Generator LLM', summary: NODES.N5, origin: 'author_claim', page: 3, section: 'Evaluation & Grounding', excerpt: NODES.N5 },
    { step_number: 6, node_id: 'N6', title: 'Answer with citations', summary: NODES.N6, origin: 'author_claim', page: 4, section: 'Results & Discussion', excerpt: NODES.N6 },
  ],
  data_setup_metrics: {
    label: 'Data, Experimental Setup & Evaluation Metrics',
    value: 'Evaluated on multi-document technical QA benchmarks measuring Recall@k, Citation Precision, Faithfulness %, and end-to-end query latency across varying k values.',
    found: true,
    origin: 'author_claim',
    page: 3,
    section: 'Evaluation & Grounding',
    supporting_excerpt: NODES.N4 + ' ' + NODES.N5,
  },
  main_results: {
    label: 'Main Results & What They Mean',
    value: 'Overlapping chunks improve boundary recall to 88.4% (+9.2% over non-overlapping), and context-constrained generation reaches 94.1% citation faithfulness at k=5 before prompt noise degrades precision at higher k.',
    found: true,
    origin: 'author_claim',
    page: 4,
    section: 'Results & Discussion',
    supporting_excerpt: 'Boundary recall reaches 88.4% with 20% chunk overlap, while citation faithfulness reaches 94.1% at k=5.',
  },
  contributions_novelty: {
    label: 'Contributions & What Is New',
    value: '1) Metadata-preserving overlapping chunk pipeline; 2) Systematic characterization of the k recall-vs-prompt-noise trade-off; 3) Strict chunk-level citation verification.',
    found: true,
    origin: 'author_claim',
    page: 1,
    section: 'Introduction',
    supporting_excerpt: NODES.N1 + ' ' + NODES.N6,
  },
  limitations_assumptions: {
    label: 'Limitations & Assumptions Stated by Authors',
    value: 'Assumes the answer exists within the top-k retrieved chunks; very large k increases prompt length and distracts the generator; approximate nearest-neighbour search can miss rare lexical exact matches.',
    found: true,
    origin: 'author_claim',
    page: 4,
    section: 'Limitations',
    supporting_excerpt: NODES.N4 + ' ' + NODES.N5,
  },
  implications_future_work: {
    label: 'Practical Implications & Possible Future Work',
    value: 'Hybrid sparse + dense retrieval and cross-encoder re-ranking can allow smaller k values in production prompts while maintaining high recall.',
    found: true,
    origin: 'app_interpretation',
    page: 4,
    section: 'Results & Discussion',
    supporting_excerpt: NODES.N4,
  },
  key_takeaways: [
    { label: 'Takeaway 1', value: 'Overlapping chunks prevent context loss at split boundaries (p. 2).', found: true, origin: 'author_claim', page: 2, section: 'Methodology — Chunking', supporting_excerpt: NODES.N2 },
    { label: 'Takeaway 2', value: 'Choosing top-k balances retrieval recall against prompt length and distraction (p. 3).', found: true, origin: 'author_claim', page: 3, section: 'Methodology — Retrieval', supporting_excerpt: NODES.N4 },
    { label: 'Takeaway 3', value: 'Constrained generation + chunk citations let readers audit every claim (p. 4).', found: true, origin: 'author_claim', page: 4, section: 'Results & Discussion', supporting_excerpt: NODES.N6 },
  ],
  story_map: [
    { label: 'Problem', value: 'Unconstrained LLMs hallucinate and fixed chunk boundaries split critical technical context.', found: true, origin: 'author_claim', page: 1, section: 'Introduction', supporting_excerpt: NODES.N2 },
    { label: 'Approach', value: 'Embed overlapping document chunks into an ANN vector index and retrieve top-k passages per query.', found: true, origin: 'author_claim', page: 2, section: 'Methodology', supporting_excerpt: NODES.N3 + ' ' + NODES.N4 },
    { label: 'Evidence', value: '88.4% Recall@5 with overlapping chunks and 94.1% citation faithfulness under strict prompt grounding.', found: true, origin: 'author_claim', page: 4, section: 'Results & Discussion', supporting_excerpt: NODES.N5 + ' ' + NODES.N6 },
    { label: 'Conclusion', value: 'Citation-grounded RAG delivers verifiable answers provided k is tuned to avoid prompt dilution.', found: true, origin: 'app_interpretation', page: 4, section: 'Results & Discussion', supporting_excerpt: NODES.N6 },
  ],
  story_map_provenance: 'conceptual_explanation',
  methodology_diagram_status: 'ok',
  methodology_diagram_note: null,
  methodology_diagram_provenance: 'reconstructed_from_paper',
  quantitative_results: [
    {
      metric_label: 'Recall@5 (Chunk Overlap vs Disjoint)',
      comparison_context: '20% overlapping windows vs non-overlapping chunks',
      baseline_label: 'Disjoint chunks',
      baseline_value: 79.2,
      proposed_label: 'Overlapping chunks',
      proposed_value: 88.4,
      value_display: '88.4% vs 79.2%',
      numeric_value: 88.4,
      unit: '%',
      baseline_or_context: 'Disjoint baseline: 79.2% (p. 4)',
      page: 4,
      section: 'Results & Discussion',
      excerpt: 'Overlapping chunks achieve 88.4% Recall@5 compared to 79.2% for disjoint chunks.',
    },
    {
      metric_label: 'Citation Faithfulness (k=5 vs Unconstrained)',
      comparison_context: 'Context-only prompt constraint vs unconstrained generation',
      baseline_label: 'Unconstrained LLM',
      baseline_value: 71.5,
      proposed_label: 'Citation-grounded (k=5)',
      proposed_value: 94.1,
      value_display: '94.1% vs 71.5%',
      numeric_value: 94.1,
      unit: '%',
      baseline_or_context: 'Unconstrained baseline: 71.5% (p. 4)',
      page: 4,
      section: 'Results & Discussion',
      excerpt: 'Citation faithfulness improves from 71.5% under unconstrained prompting to 94.1% at k=5.',
    },
  ],
  results_chart_provenance: 'reconstructed_from_paper',
  glossary: [
    { term: 'Chunk Overlap', definition: 'Repeating a sliding window of tokens between adjacent document segments so sentences split at boundaries remain intact in at least one chunk.', origin: 'author_claim', page: 2, excerpt: NODES.N2 },
    { term: 'ANN Vector Index', definition: 'Approximate Nearest-Neighbour data structure (such as HNSW or IVF) that retrieves close embedding vectors in sub-linear time.', origin: 'author_claim', page: 2, excerpt: NODES.N3 },
    { term: 'Top-k Retriever', definition: 'Selection step that ranks embedded chunks by similarity to the query embedding and returns the k highest-scoring passages.', origin: 'author_claim', page: 3, excerpt: NODES.N4 },
    { term: 'Grounded Generation', definition: 'Instructing the generator LLM to synthesize answers strictly from retrieved passages and attach passage citations.', origin: 'author_claim', page: 3, excerpt: NODES.N5 },
  ],
  sections_index: [
    { section: 'Abstract & Corpus', page: 1, excerpt: NODES.N1, node_id: 'N1', origin: 'author_claim' },
    { section: 'Methodology — Chunking', page: 2, excerpt: NODES.N2, node_id: 'N2', origin: 'author_claim' },
    { section: 'Methodology — Indexing', page: 2, excerpt: NODES.N3, node_id: 'N3', origin: 'author_claim' },
    { section: 'Methodology — Retrieval', page: 3, excerpt: NODES.N4, node_id: 'N4', origin: 'author_claim' },
    { section: 'Evaluation & Grounding', page: 3, excerpt: NODES.N5, node_id: 'N5', origin: 'author_claim' },
    { section: 'Results & Discussion', page: 4, excerpt: NODES.N6, node_id: 'N6', origin: 'author_claim' },
  ],
  viva_questions: [],
}

const base = (sid: string) => ({
  session_id: sid, student_transcript: '', audio_base64: '', done: false,
})

const REPO_TURNS = (sid: string): TurnResponse[] => [
  { ...base(sid), verdict: 'start', ack_text: '', depth_level: 1, topic: 'Cosine similarity',
    question_text: 'What does cosine_similarity return, and why does it divide by both norms?',
    highlight: { file_path: 'similarity.py', line_start: 13, line_end: 15 } },
  { ...base(sid), verdict: 'strong', ack_text: 'Good, normalising makes the score independent of length.', depth_level: 2, topic: 'Norm helper',
    question_text: 'Why does norm reuse dot instead of looping over the vector again?',
    highlight: { file_path: 'similarity.py', line_start: 9, line_end: 10 } },
  { ...base(sid), verdict: 'partial', ack_text: 'Close. Think about reuse and where bugs would live.', depth_level: 3, topic: 'Input shapes',
    question_text: 'zip stops at the shorter input. What does that mean for vectors of different lengths?',
    highlight: { file_path: 'similarity.py', line_start: 5, line_end: 6 } },
  { ...base(sid), verdict: 'strong', ack_text: 'Right, it silently truncates.', depth_level: 4, topic: 'Zero vectors',
    question_text: 'What breaks if one vector is all zeros? Fix it in the editor, then run the tests.',
    highlight: { file_path: 'similarity.py', line_start: 13, line_end: 15 },
    coding_challenge: ZERO_CHALLENGE },
]

const PAPER_TURNS = (sid: string): TurnResponse[] => [
  { ...base(sid), verdict: 'start', ack_text: '', depth_level: 1, topic: 'Chunking',
    question_text: 'What happens to the documents in this stage, and why is overlap used?',
    diagram_node_id: 'N2', paper_excerpt: NODES.N2 },
  { ...base(sid), verdict: 'strong', ack_text: 'Good, overlap preserves context across boundaries.', depth_level: 2, topic: 'Retrieval',
    question_text: 'Why is k a trade-off rather than just "bigger is better"?',
    diagram_node_id: 'N4', paper_excerpt: NODES.N4 },
  { ...base(sid), verdict: 'partial', ack_text: 'Partly. Consider prompt length and noise.', depth_level: 3, topic: 'Generation',
    question_text: 'What fails if the generator ignores the retrieved context?',
    diagram_node_id: 'N5', paper_excerpt: NODES.N5 },
  { ...base(sid), verdict: 'strong', ack_text: 'Yes, hallucinated answers.', depth_level: 4, topic: 'Top-k retrieval',
    question_text: 'Show it in code: implement the selection step of the top-k retriever.',
    diagram_node_id: 'N4', paper_excerpt: NODES.N4, coding_challenge: TOPK_CHALLENGE },
]

const progress = new Map<string, { n: number; mode: 'repo' | 'paper'; solved: number; current: CodingChallenge | null }>()

export function mockIngestRepo(_author?: string | null): IngestResponse {
  const sid = 'demo-repo-' + Math.random().toString(36).slice(2, 8)
  progress.set(sid, { n: 0, mode: 'repo', solved: 0, current: null })
  return {
    session_id: sid, mode: 'repo', paper: null,
    authors: ['Nishit', 'Vidit', 'Shagun'],
    files: [
      { path: 'similarity.py', content: SIMILARITY, language: 'python' },
      { path: 'app/ranker.py', content: RANKER, language: 'python' },
    ],
    first_turn: REPO_TURNS(sid)[0],
  }
}

export function mockIngestPdf(): IngestResponse {
  const sid = 'demo-paper-' + Math.random().toString(36).slice(2, 8)
  progress.set(sid, { n: 0, mode: 'paper', solved: 0, current: null })
  return {
    session_id: sid, mode: 'paper', files: [], authors: ['A. Sharma', 'R. Verma', 'K. Iyer'],
    paper: { mermaid: MERMAID, nodes: NODES, node_meta: NODE_META, breakdown: DEMO_PAPER_BREAKDOWN },
    first_turn: PAPER_TURNS(sid)[0],
  }
}

export function mockTurn(req: TurnRequest): TurnResponse {
  const p = progress.get(req.session_id) ?? { n: 0, mode: 'repo' as const, solved: 0, current: null }
  progress.set(req.session_id, p)
  if (req.code_result) {
    if (!req.code_result.passed) {
      return { ...base(req.session_id), verdict: 'partial', depth_level: 4, topic: 'Coding challenge',
        ack_text: 'Tests are still failing. Read the error and try again.',
        question_text: 'Adjust your solution and run the tests again.', coding_challenge: p.current }
    }
    p.solved += 1
    if (p.mode === 'repo' && p.solved === 1) {
      p.current = DSA_CHALLENGE
      return { ...base(req.session_id), verdict: 'strong', depth_level: 4, topic: 'Two Sum (DSA)',
        ack_text: 'Verified. Both tests pass.',
        question_text: 'One more. Solve this DSA problem in the editor, then run the tests.',
        coding_challenge: DSA_CHALLENGE }
    }
    return { ...base(req.session_id), verdict: 'strong', ack_text: 'Verified. All tests pass.', depth_level: 4,
      topic: 'Coding challenge', question_text: 'That completes the viva. Finish to see your report.', done: true }
  }
  p.n = Math.min(p.n + 1, 3)
  const turns = p.mode === 'repo' ? REPO_TURNS(req.session_id) : PAPER_TURNS(req.session_id)
  const t = turns[p.n]
  if (t.coding_challenge) p.current = t.coding_challenge
  return { ...t, student_transcript: req.student_text ? req.student_text : (req.audio_base64 ? '(voice answer)' : '') }
}

export async function mockRun(req: RunCodeRequest): Promise<RunCodeResponse> {
  await new Promise(r => setTimeout(r, 700))
  const code = req.student_code ?? req.source_code ?? ''
  const fixed = req.file_path === 'similarity.py'
    ? /==\s*0|<=\s*0|if not|eps|1e-/.test(code.split('def cosine_similarity')[1] ?? '')
    : !code.includes('NotImplementedError') && /return\s+\S/.test(code)
  if (fixed) return { passed: true, stdout: '...  [100%]\n3 passed in 0.03s', stderr: '', runtime_ms: 31 }
  return {
    passed: false, stdout: 'F..  [100%]\n1 failed, 2 passed in 0.04s',
    stderr: req.file_path === 'similarity.py'
      ? 'ZeroDivisionError: float division by zero\n  similarity.py:15 in cosine_similarity'
      : 'NotImplementedError\n  ' + req.file_path + ': function body not implemented',
    runtime_ms: 42,
  }
}

export function mockReport(sessionId: string): VivaReport {
  return {
    session_id: sessionId, overall_score: 78,
    rubric: { clarity: 82, tradeoffs: 74, edge_cases: 70, code_execution: 100, depth: 65 },
    topic_depth: [
      { topic: 'Cosine similarity', level: 3 }, { topic: 'Norm helper', level: 2 },
      { topic: 'Input shapes', level: 2 }, { topic: 'Zero vectors', level: 4 },
      { topic: 'Ranking', level: 1 },
    ],
    challenges: [{ description: 'Return 0.0 for zero-length vectors', passed: true }],
    study_plan: [
      'Review how zip truncates mismatched inputs and add a length check.',
      'Practise stating trade-offs: say what you gain and what you give up.',
      'Write edge-case tests before the implementation for numeric helpers.',
    ],
    fluency_weight: 0,
  }
}
