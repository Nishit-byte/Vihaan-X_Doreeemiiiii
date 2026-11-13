// Offline fallback so the demo survives a dead backend or venue Wi-Fi.
import type {
  CodingChallenge, IngestResponse, RunCodeRequest, RunCodeResponse, TurnRequest,
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
  N1["Input documents"] --> N2["Chunking and embedding"]
  N2 --> N3["Vector index"]
  N3 --> N4["Top-k retriever"]
  N4 --> N5["Generator LLM"]
  N5 --> N6["Answer with citations"]`

const NODES: Record<string, string> = {
  N1: 'The corpus is split into source documents before any processing. Each document keeps its metadata so answers can be traced back.',
  N2: 'Documents are cut into overlapping chunks and embedded with a sentence encoder. Overlap keeps context that would otherwise be split at a boundary.',
  N3: 'All chunk embeddings are stored in a vector index. The index supports approximate nearest-neighbour search.',
  N4: 'At query time the question is embedded and the k closest chunks are retrieved. The value of k trades recall against prompt length.',
  N5: 'The generator receives the question and retrieved chunks in one prompt. It is instructed to answer only from the supplied context.',
  N6: 'The final answer cites the chunks it used. Citations let a reader verify each claim.',
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
    session_id: sid, mode: 'paper', files: [], authors: [],
    paper: { mermaid: MERMAID, nodes: NODES },
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
  const code = req.student_code
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
