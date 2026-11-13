/**
 * M3 Voice Pipeline — Examiner Dev Harness Page (Task B1)
 *
 * Standalone harness running at http://localhost:5173/examiner-dev.html
 * - 65% left placeholder ('Workspace — M4') with code preview of utils/similarity.py
 * - 35% right column mounting ExaminerPanel
 * - Collapsible debug drawer with mock turn stepping, JSON inspector, and B2-B6 slots
 */

import React, { useState, useTransition } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import ExaminerPanel from '../components/ExaminerPanel'
import { MOCK_TURNS } from './mockTurns'
import type { TurnResponse } from '../types/api'
import type { RecordedAudio } from '../services/audioRecorder'

// Mock code for utils/similarity.py to illustrate M4 workspace sync
const SIMILARITY_PY_CODE = `"""Vector similarity computation utilities."""
import math
from typing import Sequence, Dict

def dot_product(u: Sequence[float], v: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(u, v))

def l2_norm(vec: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))

def cosine_similarity(u: Sequence[float], v: Sequence[float]) -> float:
    """Computes standard cosine similarity between two dense vectors."""
    norm_u = l2_norm(u)
    norm_v = l2_norm(v)
    if norm_u < 1e-12 or norm_v < 1e-12:
        return 0.0
    return dot_product(u, v) / (norm_u * norm_v)

def normalize_vector(vec: Sequence[float]) -> list[float]:
    """L2-normalizes vector to unit length with zero-division safeguard."""
    norm = l2_norm(vec)
    if norm < 1e-12:
        return [0.0] * len(vec)
    return [x / norm for x in vec]

def batch_cosine_similarity(
    query: Sequence[float],
    corpus: Sequence[Sequence[float]],
    streaming: bool = False
) -> list[float]:
    """Computes similarity for a query against a large embedding matrix.
    
    Trade-off: In-memory matrix vs chunked streaming for 50k+ vectors.
    """
    if streaming:
        return [cosine_similarity(query, doc) for doc in corpus]
    q_norm = normalize_vector(query)
    return [dot_product(q_norm, normalize_vector(doc)) for doc in corpus]

def dot_product_fp16(u: Sequence[float], v: Sequence[float]) -> float:
    """Accumulates half-precision float16 products into float32."""
    acc = 0.0
    for a, b in zip(u, v):
        acc += float(a) * float(b)
    return float(acc)

def sparse_cosine_similarity(
    vec_a: Dict[int, float],
    vec_b: Dict[int, float]
) -> float:
    """Calculates cosine similarity over sparse dictionary embeddings."""
    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not common_keys:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return dot / (norm_a * norm_b)
`

function ExaminerDevHarness() {
  const [turnIndex, setTurnIndex] = useState(0)
  const [currentTurn, setCurrentTurn] = useState<TurnResponse>(MOCK_TURNS[0])
  const [simulatedDelayMs, setSimulatedDelayMs] = useState(400)
  const [debugDrawerOpen, setDebugDrawerOpen] = useState(true)
  const [actionLog, setActionLog] = useState<string[]>([
    'Dev harness mounted. Initial Turn 1 loaded.',
  ])
  const [, startTransition] = useTransition()

  const logAction = (msg: string) => {
    setActionLog((prev) => [
      `[${new Date().toLocaleTimeString()}] ${msg}`,
      ...prev.slice(0, 19),
    ])
  }

  const goToTurn = (index: number) => {
    const clamped = Math.max(0, Math.min(index, MOCK_TURNS.length - 1))
    setTurnIndex(clamped)
    setCurrentTurn(MOCK_TURNS[clamped])
    logAction(
      `Jumped to Turn ${clamped + 1}: L${MOCK_TURNS[clamped].depth_level} (${MOCK_TURNS[clamped].verdict})`
    )
  }

  const handleNextTurn = () => {
    goToTurn(turnIndex + 1)
  }

  const handlePrevTurn = () => {
    goToTurn(turnIndex - 1)
  }

  // ExaminerPanel callbacks
  const handleMockAudioSubmit = async (
    rec: RecordedAudio
  ): Promise<TurnResponse> => {
    logAction(`onSubmitAudio: ${rec.durationMs}ms, ${rec.mimeType}, size=${rec.base64.length}b64`)
    if (simulatedDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, simulatedDelayMs))
    }
    const nextIdx = Math.min(turnIndex + 1, MOCK_TURNS.length - 1)
    const next = MOCK_TURNS[nextIdx]
    startTransition(() => {
      setTurnIndex(nextIdx)
      setCurrentTurn(next)
    })
    return next
  }

  const handleMockTextSubmit = async (
    text: string
  ): Promise<TurnResponse> => {
    logAction(`onSubmitText: "${text}"`)
    if (simulatedDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, simulatedDelayMs))
    }
    const nextIdx = Math.min(turnIndex + 1, MOCK_TURNS.length - 1)
    const next = MOCK_TURNS[nextIdx]
    startTransition(() => {
      setTurnIndex(nextIdx)
      setCurrentTurn(next)
    })
    return next
  }

  const handleTurnUpdate = (turn: TurnResponse) => {
    logAction(`onTurn callback: L${turn.depth_level} - ${turn.topic}`)
  }

  const handleRequestReport = () => {
    logAction('onRequestReport invoked! (Viva completed)')
    alert('Viva Report Requested! In full app, M4 opens ReportModal.')
  }

  // Highlight lines calculation for mock workspace
  const codeLines = SIMILARITY_PY_CODE.split('\n')
  const highlightStart = currentTurn.highlight?.line_start ?? -1
  const highlightEnd = currentTurn.highlight?.line_end ?? -1

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-void-canvas text-pale-frost font-sans">
      {/* Dev Harness Navigation Bar */}
      <header className="flex shrink-0 items-center justify-between border-b border-steel-outline bg-midnight-panel px-4 py-2 text-xs">
        <div className="flex items-center gap-3">
          <span className="font-bold text-signal-white text-sm tracking-wide">
            VivaVoce
          </span>
          <span className="rounded bg-deep-slate px-2 py-0.5 font-mono text-[11px] text-nuxt-signal border border-steel-outline">
            examiner-dev.html (M3 Lane B)
          </span>
          <span className="text-muted-fog">
            Mode (a) scaffold • 6 Mock Turns Active
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-fog">Simulate Latency:</span>
          <select
            value={simulatedDelayMs}
            onChange={(e) => setSimulatedDelayMs(Number(e.target.value))}
            className="rounded bg-void-canvas px-2 py-1 text-pale-frost border border-steel-outline"
          >
            <option value={0}>0ms (Instant)</option>
            <option value={400}>400ms (Fast)</option>
            <option value={1000}>1000ms (Typical Voice)</option>
            <option value={2500}>2500ms (Full LLM)</option>
          </select>
          <button
            onClick={() => setDebugDrawerOpen((prev) => !prev)}
            className="rounded bg-deep-slate px-3 py-1 font-medium text-pale-frost hover:bg-steel-outline border border-steel-outline transition"
          >
            {debugDrawerOpen ? 'Hide Debug Drawer ↓' : 'Show Debug Drawer ↑'}
          </button>
        </div>
      </header>

      {/* Main Split View: 65% Workspace Placeholder | 35% ExaminerPanel */}
      <main className="flex flex-1 min-h-0 w-full overflow-hidden">
        {/* Left 65%: Workspace Placeholder (M4 IDE Simulation) */}
        <section
          className="flex min-w-0 basis-[65%] flex-col border-r border-steel-outline bg-void-canvas"
          aria-label="Workspace — M4"
        >
          {/* Workspace Tabs Header */}
          <div className="flex items-center justify-between border-b border-steel-outline bg-midnight-panel px-4 py-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-signal-white">
                Workspace — M4
              </span>
              <span className="rounded bg-deep-slate px-2 py-0.5 text-[11px] text-muted-fog border border-steel-outline">
                {currentTurn.highlight?.file_path ?? 'utils/similarity.py'}
              </span>
              {highlightStart > 0 && (
                <span className="text-xs text-nuxt-signal font-mono">
                  [Lines {highlightStart}–{highlightEnd}]
                </span>
              )}
            </div>
            <span className="text-[11px] text-muted-fog">
              Read-only IDE mock • Synchronized with turn.highlight
            </span>
          </div>

          {/* Code Viewer */}
          <div className="flex-1 overflow-auto p-4 font-mono text-xs leading-5 bg-void-canvas">
            <table className="w-full border-collapse">
              <tbody>
                {codeLines.map((line, idx) => {
                  const lineNum = idx + 1
                  const isHighlighted =
                    highlightStart > 0 &&
                    lineNum >= highlightStart &&
                    lineNum <= highlightEnd

                  return (
                    <tr
                      key={lineNum}
                      className={`transition-colors ${
                        isHighlighted
                          ? 'bg-nuxt-signal/15 text-signal-white font-semibold'
                          : 'hover:bg-deep-slate/40 text-pale-frost'
                      }`}
                    >
                      <td className="w-12 select-none pr-4 text-right text-muted-fog/60 border-r border-steel-outline/60">
                        {lineNum}
                      </td>
                      <td className="pl-4 whitespace-pre">
                        {isHighlighted && (
                          <span className="inline-block w-2 text-nuxt-signal mr-1 select-none">
                            ▶
                          </span>
                        )}
                        {line}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* Right 35%: ExaminerPanel Mount */}
        <aside
          className="min-w-0 basis-[35%] flex flex-col h-full overflow-hidden bg-midnight-panel"
          aria-label="Examiner Panel"
        >
          <ExaminerPanel
            initialTurn={currentTurn}
            onSubmitAudio={handleMockAudioSubmit}
            onSubmitText={handleMockTextSubmit}
            onTurn={handleTurnUpdate}
            onRequestReport={handleRequestReport}
            fillersUrl="/api/voice/fillers"
            disabled={false}
          />
        </aside>
      </main>

      {/* Collapsible Debug Drawer for Task B1 and Future Tasks (B2..B6) */}
      {debugDrawerOpen && (
        <section
          className="shrink-0 border-t border-steel-outline bg-midnight-panel text-xs transition-all max-h-56 overflow-auto"
          aria-label="Debug Drawer"
        >
          <div className="flex items-center justify-between border-b border-steel-outline px-4 py-1.5 bg-deep-slate">
            <span className="font-semibold text-signal-white">
              🛠️ M3 Voice Debug Drawer — Mock Controls & Diagnostics
            </span>
            <div className="flex items-center gap-2">
              <span className="text-muted-fog">
                Turn {turnIndex + 1} of {MOCK_TURNS.length}
              </span>
              <button
                onClick={handlePrevTurn}
                disabled={turnIndex === 0}
                className="rounded bg-midnight-panel px-2 py-0.5 font-medium border border-steel-outline hover:bg-void-canvas disabled:opacity-40"
              >
                ◀ Prev
              </button>
              <button
                onClick={handleNextTurn}
                disabled={turnIndex === MOCK_TURNS.length - 1}
                className="rounded bg-midnight-panel px-2 py-0.5 font-medium border border-steel-outline hover:bg-void-canvas disabled:opacity-40"
              >
                Next ▶
              </button>
              <button
                onClick={() => goToTurn(0)}
                className="rounded bg-midnight-panel px-2 py-0.5 font-medium text-nuxt-signal border border-steel-outline hover:bg-void-canvas"
              >
                Reset Viva
              </button>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 p-3">
            {/* Column 1: Quick Turn Selectors */}
            <div className="flex flex-col gap-1.5">
              <span className="font-semibold text-signal-white text-[11px] uppercase tracking-wider">
                Step to Mock Turn
              </span>
              <div className="flex flex-wrap gap-1.5">
                {MOCK_TURNS.map((t, idx) => (
                  <button
                    key={idx}
                    onClick={() => goToTurn(idx)}
                    className={`rounded px-2 py-1 text-[11px] font-mono border transition ${
                      idx === turnIndex
                        ? 'bg-nuxt-signal text-void-canvas font-bold border-nuxt-signal'
                        : 'bg-deep-slate text-pale-frost border-steel-outline hover:bg-steel-outline'
                    }`}
                  >
                    #{idx + 1} L{t.depth_level} ({t.verdict})
                  </button>
                ))}
              </div>
              <p className="mt-1 text-[11px] text-muted-fog">
                Topic: <strong className="text-pale-frost">{currentTurn.topic}</strong> • Done: {String(currentTurn.done)}
              </p>
            </div>

            {/* Column 2: Turn Details & Raw JSON Inspector */}
            <div className="flex flex-col gap-1">
              <span className="font-semibold text-signal-white text-[11px] uppercase tracking-wider">
                Current Turn Payload (TurnResponse)
              </span>
              <pre className="max-h-28 overflow-auto rounded bg-void-canvas p-2 font-mono text-[10px] text-muted-fog border border-steel-outline">
                {JSON.stringify(currentTurn, null, 2)}
              </pre>
            </div>

            {/* Column 3: Event Log & Task Diagnostics */}
            <div className="flex flex-col gap-1">
              <span className="font-semibold text-signal-white text-[11px] uppercase tracking-wider">
                Harness Action Log & Task Hooks
              </span>
              <div className="max-h-28 overflow-auto rounded bg-void-canvas p-2 font-mono text-[10px] text-pale-frost/80 border border-steel-outline space-y-0.5">
                {actionLog.map((log, i) => (
                  <div key={i}>{log}</div>
                ))}
              </div>
              <div className="text-[10px] text-muted-fog pt-1 flex gap-2">
                <span>[B2: Spacebar recorder hook pending]</span>
                <span>[B3: Audio playback pending]</span>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

const container = document.getElementById('root')
if (container) {
  const root = createRoot(container)
  root.render(
    <React.StrictMode>
      <ExaminerDevHarness />
    </React.StrictMode>
  )
}

