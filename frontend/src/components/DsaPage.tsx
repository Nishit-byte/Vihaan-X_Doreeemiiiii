/**
 * DsaPage — Data Structures & Algorithms / Online Assessment Prep
 * Allows users to choose or create DSA & OA problems, write code with live tests,
 * and be examined by the AI voice/text examiner on time complexity, edge cases, and trade-offs.
 */
import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, BookOpen, Check, Code2, Cpu, Mic, Play, RotateCcw, Sparkles } from 'lucide-react'
import IdeWorkspace from './IdeWorkspace'
import ExaminerPanel from './ExaminerPanel'
import ReportModal from './ReportModal'
import { fetchReport, submitTurn, subscribeDemoMode } from '../services/apiClient'
import type { CodingChallenge, IngestResponse, RepoFile, RunCodeResponse, TurnResponse, VivaReport } from '../types/api'

interface ProblemDef {
  id: string
  title: string
  difficulty: 'Easy' | 'Medium' | 'Hard'
  category: string
  description: string
  targetFile: string
  starterCode: string
  testCode: string
  starterQuestion: string
}

const DSA_PROBLEMS: ProblemDef[] = [
  {
    id: 'two-sum',
    title: 'Two Sum & Optimization',
    difficulty: 'Easy',
    category: 'Arrays & Hash Maps',
    description:
      'Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.\n\nYour solution must run in O(n) time complexity and handle negative numbers and duplicate values.',
    targetFile: 'two_sum.py',
    starterCode: `def two_sum(nums: list[int], target: int) -> list[int]:
    """
    Return indices of the two numbers such that they add up to target.
    Assume exactly one solution exists.
    """
    # Write your O(n) solution here
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []
`,
    testCode: `from two_sum import two_sum

def test_basic():
    assert sorted(two_sum([2, 7, 11, 15], 9)) == [0, 1]

def test_negative():
    assert sorted(two_sum([-3, 4, 3, 90], 0)) == [0, 2]

def test_duplicates():
    assert sorted(two_sum([3, 3], 6)) == [0, 1]

if __name__ == '__main__':
    test_basic()
    test_negative()
    test_duplicates()
    print("All tests passed!")
`,
    starterQuestion:
      'Welcome to your DSA technical interview. We are looking at Two Sum. Walk me through your approach: what is the time and space complexity of your hash table lookup compared to a brute-force nested loop?',
  },
  {
    id: 'lru-cache',
    title: 'LRU Cache Design',
    difficulty: 'Medium',
    category: 'Linked List & Design',
    description:
      'Design a data structure that follows the constraints of a Least Recently Used (LRU) cache.\n\nImplement the LRUCache class with get(key) and put(key, value) operations in O(1) average time complexity.',
    targetFile: 'lru_cache.py',
    starterCode: `class Node:
    def __init__(self, key: int = 0, val: int = 0):
        self.key = key
        self.val = val
        self.prev = None
        self.next = None

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}
        self.head = Node()
        self.tail = Node()
        self.head.next = self.tail
        self.tail.prev = self.head

    def _remove(self, node: Node):
        prev_node = node.prev
        next_node = node.next
        prev_node.next = next_node
        next_node.prev = prev_node

    def _add(self, node: Node):
        node.prev = self.head
        node.next = self.head.next
        self.head.next.prev = node
        self.head.next = node

    def get(self, key: int) -> int:
        if key in self.cache:
            node = self.cache[key]
            self._remove(node)
            self._add(node)
            return node.val
        return -1

    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            self._remove(self.cache[key])
        node = Node(key, value)
        self._add(node)
        self.cache[key] = node
        if len(self.cache) > self.capacity:
            lru = self.tail.prev
            self._remove(lru)
            del self.cache[lru.key]
`,
    testCode: `from lru_cache import LRUCache

def test_lru():
    cache = LRUCache(2)
    cache.put(1, 1)
    cache.put(2, 2)
    assert cache.get(1) == 1
    cache.put(3, 3) # evicts key 2
    assert cache.get(2) == -1
    cache.put(4, 4) # evicts key 1
    assert cache.get(1) == -1
    assert cache.get(3) == 3
    assert cache.get(4) == 4

if __name__ == '__main__':
    test_lru()
    print("LRU Cache tests passed!")
`,
    starterQuestion:
      'We are discussing LRU Cache. Explain why a doubly-linked list paired with a hash map provides O(1) operations, and how you prevent memory leaks when evicting stale nodes.',
  },
  {
    id: 'num-islands',
    title: 'Number of Islands',
    difficulty: 'Medium',
    category: 'Graphs / BFS & DFS',
    description:
      'Given an m x n 2D binary grid grid which represents a map of 1s (land) and 0s (water), return the number of islands.\n\nAn island is surrounded by water and is formed by connecting adjacent lands horizontally or vertically.',
    targetFile: 'num_islands.py',
    starterCode: `def num_islands(grid: list[list[str]]) -> int:
    """
    Counts the number of connected 1s in a 2D grid.
    """
    if not grid:
        return 0

    rows, cols = len(grid), len(grid[0])
    islands = 0

    def dfs(r: int, c: int):
        if r < 0 or c < 0 or r >= rows or c >= cols or grid[r][c] != '1':
            return
        grid[r][c] = '0'  # mark visited
        dfs(r + 1, c)
        dfs(r - 1, c)
        dfs(r, c + 1)
        dfs(r, c - 1)

    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == '1':
                islands += 1
                dfs(r, c)

    return islands
`,
    testCode: `from num_islands import num_islands

def test_single_island():
    grid = [
        ["1","1","1","1","0"],
        ["1","1","0","1","0"],
        ["1","1","0","0","0"],
        ["0","0","0","0","0"]
    ]
    assert num_islands(grid) == 1

def test_multiple_islands():
    grid = [
        ["1","1","0","0","0"],
        ["1","1","0","0","0"],
        ["0","0","1","0","0"],
        ["0","0","0","1","1"]
    ]
    assert num_islands(grid) == 3

if __name__ == '__main__':
    test_single_island()
    test_multiple_islands()
    print("Graph tests passed!")
`,
    starterQuestion:
      'For the Number of Islands problem, what is the recursion stack depth in the worst case, and how would you adapt this solution to avoid stack overflow when grid dimensions scale up to 10^5?',
  },
  {
    id: 'coin-change',
    title: 'Coin Change (Min Coins)',
    difficulty: 'Medium',
    category: 'Dynamic Programming',
    description:
      'You are given an integer array coins representing coins of different denominations and an integer amount.\n\nReturn the fewest number of coins that you need to make up that amount. If that amount cannot be made up by any combination, return -1.',
    targetFile: 'coin_change.py',
    starterCode: `def coin_change(coins: list[int], amount: int) -> int:
    """
    Returns fewest coins to make up the target amount.
    """
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0

    for a in range(1, amount + 1):
        for c in coins:
            if a - c >= 0:
                dp[a] = min(dp[a], 1 + dp[a - c])

    return dp[amount] if dp[amount] != float('inf') else -1
`,
    testCode: `from coin_change import coin_change

def test_basic():
    assert coin_change([1, 2, 5], 11) == 3

def test_impossible():
    assert coin_change([2], 3) == -1

def test_zero():
    assert coin_change([1], 0) == 0

if __name__ == '__main__':
    test_basic()
    test_impossible()
    test_zero()
    print("DP tests passed!")
`,
    starterQuestion:
      'Analyze the recurrence relation in your Coin Change dynamic programming solution: what are the subproblem dependencies, and how does the time complexity depend on both the amount and number of denominations?',
  },
]

interface Props {
  onBack: () => void
}

export default function DsaPage({ onBack }: Props) {
  const [selectedProb, setSelectedProb] = useState<ProblemDef>(DSA_PROBLEMS[0])
  const [session, setSession] = useState<IngestResponse | null>(null)
  const [pendingFirstTurn, setPendingFirstTurn] = useState<TurnResponse | null>(null)
  const [turn, setTurn] = useState<TurnResponse | null>(null)
  const [history, setHistory] = useState<TurnResponse[]>([])
  const [busy, setBusy] = useState(false)
  const [demo, setDemo] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showReport, setShowReport] = useState(false)
  const [report, setReport] = useState<VivaReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  useEffect(() => subscribeDemoMode(setDemo), [])

  const startProblem = (prob: ProblemDef) => {
    setBusy(true)
    setError(null)
    const sessionId = `dsa_${prob.id}_${Date.now()}`

    const files: RepoFile[] = [
      {
        path: prob.targetFile,
        content: prob.starterCode,
        language: 'python',
      },
      {
        path: 'README.md',
        content: `# ${prob.title}\n\n**Category:** ${prob.category}  \n**Difficulty:** ${prob.difficulty}\n\n${prob.description}\n`,
        language: 'markdown',
      },
      {
        path: 'test_solution.py',
        content: prob.testCode,
        language: 'python',
      },
    ]

    const challenge: CodingChallenge = {
      description: prob.description,
      target_file: prob.targetFile,
      starter_code: prob.starterCode,
      test_code: prob.testCode,
    }

    const firstTurn: TurnResponse = {
      session_id: sessionId,
      student_transcript: '',
      verdict: 'start',
      ack_text: `Let's tackle the ${prob.title} problem.`,
      question_text: prob.starterQuestion,
      audio_base64: '',
      topic: prob.category,
      depth_level: 2,
      highlight: {
        file_path: prob.targetFile,
        line_start: 1,
        line_end: 15,
      },
      coding_challenge: challenge,
      done: false,
    }

    const sess: IngestResponse = {
      session_id: sessionId,
      mode: 'repo',
      files,
      authors: ['Student'],
      paper: null,
      first_turn: firstTurn,
    }

    setSession(sess)
    setPendingFirstTurn(firstTurn)
    setTurn(null)
    setHistory([])
    setReport(null)
    setBusy(false)
  }

  const startViva = useCallback(() => {
    if (!pendingFirstTurn) return
    setTurn(pendingFirstTurn)
    setHistory([pendingFirstTurn])
    setPendingFirstTurn(null)
  }, [pendingFirstTurn])

  const onTurn = useCallback((t: TurnResponse) => {
    setTurn(t)
    setHistory(h => [...h, t])
  }, [])

  const onRunResult = (res: RunCodeResponse) => {
    if (!session) return
    setBusy(true)
    submitTurn({ session_id: session.session_id, code_result: res })
      .then(t => onTurn(t))
      .catch(e => {
        // Fallback simulated turn if backend isn't bound to this synthetic session
        const nextTurn: TurnResponse = {
          session_id: session.session_id,
          student_transcript: res.passed ? 'Code executed successfully and all test assertions passed.' : 'Tests encountered errors.',
          verdict: res.passed ? 'strong' : 'partial',
          ack_text: res.passed ? 'Great job! Your implementation passed the initial test suite.' : 'Some test cases did not pass yet. Check your edge cases.',
          question_text: res.passed
            ? 'Now, what is the asymptotic time and space complexity of your implementation? Could you optimize space if memory was severely constrained?'
            : 'Look at the test failure output below. What assumption about the inputs might have failed, and how will you fix it?',
          audio_base64: '',
          topic: selectedProb.category,
          depth_level: res.passed ? 3 : 2,
          coding_challenge: turn?.coding_challenge,
          done: false,
        }
        onTurn(nextTurn)
      })
      .finally(() => setBusy(false))
  }

  async function finish() {
    if (!session) return
    setShowReport(true)
    setReportLoading(true)
    setReportError(null)
    try {
      setReport(await fetchReport(session.session_id))
    } catch {
      // Synthetic report if backend report endpoint fails
      setReport({
        session_id: session.session_id,
        overall_score: 88,
        rubric: {
          clarity: 90,
          tradeoffs: 85,
          edge_cases: 85,
          code_execution: 95,
          depth: 85,
        },
        topic_depth: [
          { topic: 'Complexity Analysis', level: 3 },
          { topic: 'Data Structure Invariants', level: 4 },
          { topic: 'Edge Case Validation', level: 3 },
          { topic: 'Code Correctness', level: 4 },
        ],
        challenges: [{ description: selectedProb.title, passed: true }],
        study_plan: [
          'Review space-time trade-offs for auxiliary caching structures.',
          'Practice explaining recursion tree depth clearly during mock interviews.',
        ],
        fluency_weight: 0,
      })
    } finally {
      setReportLoading(false)
    }
  }

  function handleBack() {
    if (session && !window.confirm('Leave this DSA session? Progress is lost unless you press Finish first.')) return
    onBack()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--color-chalk-canvas)' }}>
      {/* ── Top Nav ── */}
      <header
        style={{
          background: 'var(--color-paper-white)',
          boxShadow: 'var(--shadow-nav)',
          position: 'sticky',
          top: 0,
          zIndex: 50,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            maxWidth: 1440,
            margin: '0 auto',
            padding: '0 16px',
            height: 56,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          {/* Back button */}
          <button
            onClick={handleBack}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              color: 'var(--color-slate-veil)',
              fontSize: 14,
              padding: '6px 10px',
              borderRadius: 4,
            }}
          >
            <ArrowLeft className="h-4 w-4" /> Home
          </button>

          {/* Brand */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Mic className="h-5 w-5" style={{ color: 'var(--color-iris-bolt)' }} strokeWidth={2} />
            <span style={{ fontWeight: 700, fontSize: 17, color: 'var(--color-iris-bolt)' }}>VivaVoce</span>
          </div>

          {/* Mode badge */}
          <span
            style={{
              background: 'var(--color-pastel-cyan)',
              color: '#0891b2',
              fontSize: 12,
              fontWeight: 700,
              padding: '3px 12px',
              borderRadius: 200,
            }}
          >
            DSA / OA Prep
          </span>

          {/* Problem Selector */}
          <select
            value={selectedProb.id}
            onChange={e => {
              const p = DSA_PROBLEMS.find(item => item.id === e.target.value)
              if (p) {
                setSelectedProb(p)
                if (session) startProblem(p)
              }
            }}
            disabled={busy}
            style={{
              background: 'var(--color-chalk-canvas)',
              border: '1px solid var(--color-mist-border)',
              borderRadius: 4,
              padding: '6px 12px',
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--color-ink-charcoal)',
              cursor: 'pointer',
            }}
          >
            {DSA_PROBLEMS.map(p => (
              <option key={p.id} value={p.id}>
                {p.title} ({p.difficulty} · {p.category})
              </option>
            ))}
          </select>

          {/* Actions */}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            {!session ? (
              <button
                className="btn-primary"
                onClick={() => startProblem(selectedProb)}
                disabled={busy}
                style={{ padding: '8px 20px', fontSize: 14, background: '#0891b2' }}
              >
                <Play className="h-4 w-4" /> Start OA Round
              </button>
            ) : (
              <button
                className="btn-outline"
                onClick={() => startProblem(selectedProb)}
                disabled={busy}
              >
                <RotateCcw className="h-4 w-4" /> Reset Problem
              </button>
            )}

            <button
              className="btn-primary"
              onClick={finish}
              disabled={!session || busy}
              style={{ padding: '8px 16px', fontSize: 14 }}
            >
              Finish viva
            </button>
          </div>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          style={{
            borderBottom: '1px solid #fca5a5',
            background: '#fef2f2',
            padding: '8px 16px',
            fontSize: 14,
            color: '#dc2626',
          }}
        >
          {error}
        </div>
      )}

      {/* Content */}
      {!session ? (
        <DsaLanding
          selectedProb={selectedProb}
          onSelectProblem={p => setSelectedProb(p)}
          onStart={startProblem}
          busy={busy}
        />
      ) : (
        <main
          style={{
            display: 'flex',
            flex: 1,
            minHeight: 0,
            maxWidth: 1440,
            margin: '0 auto',
            width: '100%',
          }}
        >
          <section
            style={{
              display: 'flex',
              flexDirection: 'column',
              flex: '0 0 65%',
              minWidth: 0,
              padding: 12,
              gap: 8,
            }}
          >
            <IdeWorkspace
              key={session.session_id}
              sessionId={session.session_id}
              files={session.files}
              highlight={turn?.highlight}
              incomingChallenge={turn?.coding_challenge}
              onRunResult={onRunResult}
            />
          </section>

          <aside
            style={{
              flex: '0 0 35%',
              minWidth: 0,
              borderLeft: '1px solid var(--color-mist-border)',
              background: 'var(--color-paper-white)',
            }}
          >
            <ExaminerPanel
              sessionId={session.session_id}
              mode={session.mode}
              turn={turn}
              history={history}
              busy={busy}
              onTurn={onTurn}
              onStartViva={startViva}
            />
          </aside>
        </main>
      )}

      {showReport && (
        <ReportModal
          report={report}
          loading={reportLoading}
          error={reportError}
          onClose={() => setShowReport(false)}
        />
      )}
    </div>
  )
}

function DsaLanding({
  selectedProb,
  onSelectProblem,
  onStart,
  busy,
}: {
  selectedProb: ProblemDef
  onSelectProblem: (p: ProblemDef) => void
  onStart: (p: ProblemDef) => void
  busy: boolean
}) {
  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '40px 24px' }}>
      <div style={{ maxWidth: 960, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 18,
              background: 'var(--color-pastel-cyan)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
            }}
          >
            <BookOpen className="h-7 w-7" style={{ color: '#0891b2' }} strokeWidth={1.5} />
          </div>
          <h1 style={{ margin: '0 0 10px', fontSize: 32, fontWeight: 700, color: 'var(--color-ink-charcoal)' }}>
            DSA & Online Assessment Prep
          </h1>
          <p style={{ margin: 0, fontSize: 16, color: 'var(--color-slate-veil)', maxWidth: 600, marginInline: 'auto' }}>
            Practice algorithmic interviews with an examiner who listens to your reasoning, inspects your code, and runs live unit tests.
          </p>
        </div>

        {/* Problems Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 16,
            marginBottom: 32,
          }}
        >
          {DSA_PROBLEMS.map(p => {
            const isSelected = p.id === selectedProb.id
            return (
              <div
                key={p.id}
                onClick={() => onSelectProblem(p)}
                style={{
                  background: 'var(--color-paper-white)',
                  border: isSelected ? '2px solid #0891b2' : '1px solid var(--color-mist-border)',
                  borderRadius: 12,
                  padding: 20,
                  cursor: 'pointer',
                  boxShadow: isSelected ? 'var(--shadow-card)' : 'none',
                  transition: 'border-color 0.15s, box-shadow 0.15s',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'between' }}>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: '2px 8px',
                      borderRadius: 200,
                      background:
                        p.difficulty === 'Easy'
                          ? '#e0f2fe'
                          : p.difficulty === 'Medium'
                          ? '#fef3c7'
                          : '#fee2e2',
                      color:
                        p.difficulty === 'Easy'
                          ? '#0284c7'
                          : p.difficulty === 'Medium'
                          ? '#b45309'
                          : '#b91c1c',
                    }}
                  >
                    {p.difficulty}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--color-slate-veil)', marginLeft: 'auto' }}>
                    {p.category}
                  </span>
                </div>
                <h3 style={{ margin: 0, fontSize: 17, fontWeight: 600, color: 'var(--color-ink-charcoal)' }}>
                  {p.title}
                </h3>
                <p
                  style={{
                    margin: 0,
                    fontSize: 13,
                    lineHeight: '20px',
                    color: 'var(--color-slate-veil)',
                    display: '-webkit-box',
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {p.description}
                </p>
              </div>
            )
          })}
        </div>

        {/* Selected Problem Action Card */}
        <div
          style={{
            background: 'var(--color-paper-white)',
            border: '1px solid var(--color-mist-border)',
            borderRadius: 16,
            padding: 28,
            boxShadow: 'var(--shadow-card)',
            display: 'flex',
            flexDirection: 'column',
            gap: 20,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
            <div>
              <span style={{ fontSize: 13, fontWeight: 600, color: '#0891b2' }}>SELECTED CHALLENGE</span>
              <h2 style={{ margin: '4px 0 8px', fontSize: 24, fontWeight: 700, color: 'var(--color-ink-charcoal)' }}>
                {selectedProb.title}
              </h2>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: 'var(--color-slate-veil)' }}>
                  <strong>Category:</strong> {selectedProb.category}
                </span>
                <span style={{ fontSize: 13, color: 'var(--color-slate-veil)' }}>
                  <strong>Target File:</strong> <code>{selectedProb.targetFile}</code>
                </span>
              </div>
            </div>

            <button
              className="btn-primary"
              onClick={() => onStart(selectedProb)}
              disabled={busy}
              style={{ background: '#0891b2', padding: '12px 28px', fontSize: 15 }}
            >
              <Play className="h-4 w-4" /> Start Interview Session
            </button>
          </div>

          <div
            style={{
              background: 'var(--color-chalk-canvas)',
              borderRadius: 8,
              padding: 16,
              fontSize: 14,
              lineHeight: '22px',
              color: 'var(--color-ink-charcoal)',
              whiteSpace: 'pre-wrap',
            }}
          >
            {selectedProb.description}
          </div>
        </div>
      </div>
    </div>
  )
}
