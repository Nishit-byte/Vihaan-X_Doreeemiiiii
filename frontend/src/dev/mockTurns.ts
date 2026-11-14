/**
 * M3 Voice Pipeline — Mock Turn Dataset (Task B1)
 *
 * 6 realistic TurnResponse turns cycling depth levels 1..4 grounded in utils/similarity.py:
 * 1. start (depth 1): Cosine similarity definition and return range.
 * 2. strong (depth 2): Vector normalization and epsilon check (< 1e-12).
 * 3. partial (depth 3): Batch cosine similarity RAM vs streaming trade-offs for 50k vectors.
 * 4. weak (depth 3): Numerical stability and FP16 overflow prevention.
 * 5. no_answer (depth 4): Mutation challenge for sparse vector dot product bug.
 * 6. done (depth 4): Evaluation summary and completion of technical viva.
 *
 * audio_base64 is "" so browser-TTS or local synthesis handles playback.
 */

import type { TurnResponse } from '../types/api'

export const MOCK_TURNS: TurnResponse[] = [
  {
    session_id: 'mock-session-similarity',
    student_transcript: '',
    verdict: 'start',
    ack_text: "Welcome to your viva on utils/similarity.py. Let's begin with vector mathematics.",
    question_text:
      'In utils/similarity.py, what mathematical formula is used to compute the cosine similarity between two embedding vectors, and what range of values does it return?',
    audio_base64: '',
    topic: 'Cosine Similarity Definition',
    depth_level: 1,
    highlight: {
      file_path: 'utils/similarity.py',
      line_start: 12,
      line_end: 25,
    },
    diagram_node_id: null,
    paper_excerpt: null,
    coding_challenge: null,
    done: false,
  },
  {
    session_id: 'mock-session-similarity',
    student_transcript:
      'We compute the dot product of vectors u and v divided by the product of their L2 Euclidean norms. It returns values between -1 and 1, or 0 and 1 for non-negative embeddings.',
    verdict: 'strong',
    ack_text: 'Exact definition. Good call on the non-negative embedding range.',
    question_text:
      'Why does normalize_vector check whether the L2 norm is strictly below 1e-12 before dividing, and what numerical edge case does that prevent?',
    audio_base64: '',
    topic: 'Vector Normalization & Zero-Division',
    depth_level: 2,
    highlight: {
      file_path: 'utils/similarity.py',
      line_start: 28,
      line_end: 42,
    },
    diagram_node_id: null,
    paper_excerpt: null,
    coding_challenge: null,
    done: false,
  },
  {
    session_id: 'mock-session-similarity',
    student_transcript:
      'It prevents division by zero when a vector has all zero components.',
    verdict: 'partial',
    ack_text:
      'Correct on zero-division, though floating-point underflow with near-zero vectors is also why the epsilon threshold is chosen.',
    question_text:
      'Looking at batch_cosine_similarity in lines 45 to 68, what is the memory complexity trade-off of computing the full pairwise similarity matrix in RAM versus streaming chunk-by-chunk for 50,000 vectors?',
    audio_base64: '',
    topic: 'Batch Similarity & Memory Trade-offs',
    depth_level: 3,
    highlight: {
      file_path: 'utils/similarity.py',
      line_start: 45,
      line_end: 68,
    },
    diagram_node_id: null,
    paper_excerpt: null,
    coding_challenge: null,
    done: false,
  },
  {
    session_id: 'mock-session-similarity',
    student_transcript:
      'Streaming is slower because of Python loops, but RAM is big so matrix multiplication is usually fine.',
    verdict: 'weak',
    ack_text:
      'Be careful: a 50k by 50k float32 matrix consumes 10 gigabytes of RAM, which can easily trigger an Out-of-Memory crash.',
    question_text:
      'How would you modify the dot product calculation when handling half-precision float16 embeddings to prevent intermediate numerical overflow during summation?',
    audio_base64: '',
    topic: 'Numerical Stability & Precision',
    depth_level: 3,
    highlight: {
      file_path: 'utils/similarity.py',
      line_start: 70,
      line_end: 88,
    },
    diagram_node_id: null,
    paper_excerpt: null,
    coding_challenge: null,
    done: false,
  },
  {
    session_id: 'mock-session-similarity',
    student_transcript: '',
    verdict: 'no_answer',
    ack_text:
      "I didn't catch an answer on numerical overflow. Let's move to a code mutation challenge.",
    question_text:
      'In lines 95 to 110 of utils/similarity.py, there is a bug where sparse vectors fail because indices are assumed contiguous. How would you refactor this to support dictionary-based or CSR sparse embeddings?',
    audio_base64: '',
    topic: 'Mutation & Live Bug Fix',
    depth_level: 4,
    highlight: {
      file_path: 'utils/similarity.py',
      line_start: 95,
      line_end: 110,
    },
    diagram_node_id: null,
    paper_excerpt: null,
    coding_challenge: {
      description: 'Fix sparse dot product index assumption in utils/similarity.py',
      target_file: 'utils/similarity.py',
      starter_code:
        'def sparse_cosine_similarity(vec_a: dict[int, float], vec_b: dict[int, float]) -> float:\n    # Fix: only multiply overlapping keys\n    pass\n',
      test_code:
        'def test_sparse_cosine():\n    assert sparse_cosine_similarity({0: 1.0, 5: 2.0}, {0: 1.0, 2: 3.0}) > 0\n',
    },
    done: false,
  },
  {
    session_id: 'mock-session-similarity',
    student_transcript:
      'We find the key intersection of non-zero indices, multiply only common coordinates, and normalize by precomputed sparse L2 norms.',
    verdict: 'strong',
    ack_text: 'Excellent architectural fix using index intersection.',
    question_text:
      'Great job completing the technical viva on utils/similarity.py. You demonstrated strong comprehension of vector operations and numerical trade-offs. Your evaluation report is ready.',
    audio_base64: '',
    topic: 'Evaluation & Wrap-up',
    depth_level: 4,
    highlight: null,
    diagram_node_id: null,
    paper_excerpt: null,
    coding_challenge: null,
    done: true,
  },
]

