/**
 * ResearchPage — Research Paper Interview Prep
 * Upload research papers (PDF) or load demo paper, view the interactive architecture diagram,
 * and defend methodology, findings, and trade-offs against the AI examiner.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, FileText, FileUp, Mic, Play, RotateCcw } from 'lucide-react'
import PaperWorkspace from './PaperWorkspace'
import IdeWorkspace from './IdeWorkspace'
import ExaminerPanel from './ExaminerPanel'
import ReportModal from './ReportModal'
import { fetchReport, ingestPdf, submitTurn, subscribeDemoMode } from '../services/apiClient'
import type { IngestResponse, RunCodeResponse, TurnResponse, VivaReport } from '../types/api'

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong')

interface Props {
  onBack: () => void
}

export default function ResearchPage({ onBack }: Props) {
  const [session, setSession] = useState<IngestResponse | null>(null)
  const [pendingFirstTurn, setPendingFirstTurn] = useState<TurnResponse | null>(null)
  const [turn, setTurn] = useState<TurnResponse | null>(null)
  const [history, setHistory] = useState<TurnResponse[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [demo, setDemo] = useState(false)
  const [paperTab, setPaperTab] = useState<'paper' | 'code'>('paper')
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null)
  const [showReport, setShowReport] = useState(false)
  const [report, setReport] = useState<VivaReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => subscribeDemoMode(setDemo), [])

  // Switch tab when challenge or diagram node occurs
  useEffect(() => {
    if (!turn) return
    if (turn.coding_challenge) setPaperTab('code')
    else if (turn.diagram_node_id) setPaperTab('paper')
  }, [turn])

  const begin = (res: IngestResponse) => {
    setSession(res)
    setPendingFirstTurn(res.first_turn)
    setTurn(null)
    setHistory([])
    setReport(null)
  }

  const startViva = useCallback(() => {
    if (!pendingFirstTurn) return
    setTurn(pendingFirstTurn)
    setHistory([pendingFirstTurn])
    setPendingFirstTurn(null)
  }, [pendingFirstTurn])

  async function guarded(fn: () => Promise<void>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  const startPaper = (file: File | null) =>
    guarded(async () => {
      setSelectedFileName(file ? file.name : 'Sample Research Paper')
      begin(await ingestPdf(file))
    })

  const onTurn = useCallback((t: TurnResponse) => {
    setTurn(t)
    setHistory(h => [...h, t])
  }, [])

  const onRunResult = (res: RunCodeResponse) => {
    if (!session) return
    guarded(async () => onTurn(await submitTurn({ session_id: session.session_id, code_result: res })))
  }

  async function finish() {
    if (!session) return
    setShowReport(true)
    setReportLoading(true)
    setReportError(null)
    try {
      setReport(await fetchReport(session.session_id))
    } catch (e) {
      setReportError(errMsg(e))
    } finally {
      setReportLoading(false)
    }
  }

  function handleBack() {
    if (session && !window.confirm('Leave this paper viva? Progress is lost unless you press Finish first.')) return
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
          {/* Back to Home */}
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
              background: 'var(--color-pastel-magenta)',
              color: '#db2777',
              fontSize: 12,
              fontWeight: 700,
              padding: '3px 12px',
              borderRadius: 200,
            }}
          >
            Research Paper Prep
          </span>

          {selectedFileName && (
            <span
              style={{
                fontSize: 13,
                color: 'var(--color-slate-veil)',
                maxWidth: 240,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={selectedFileName}
            >
              📄 {selectedFileName}
            </span>
          )}

          {/* Right actions */}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              hidden
              onChange={e => {
                const f = e.target.files?.[0]
                if (f) startPaper(f)
                e.target.value = ''
              }}
            />

            <button
              className="btn-outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
            >
              <FileUp className="h-4 w-4" /> Upload PDF
            </button>

            <button
              className="btn-outline"
              onClick={() => startPaper(null)}
              disabled={busy}
            >
              Demo paper
            </button>

            {demo && (
              <span
                style={{
                  fontSize: 11,
                  color: 'var(--color-fog-mist)',
                  background: 'var(--color-chalk-canvas)',
                  border: '1px solid var(--color-mist-border)',
                  borderRadius: 200,
                  padding: '3px 10px',
                }}
              >
                Demo data
              </span>
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

      {/* Main content */}
      {!session ? (
        <ResearchEmptyState
          busy={busy}
          onUpload={() => fileInputRef.current?.click()}
          onDemo={() => startPaper(null)}
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
          {/* Left 65%: Workspace */}
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
            <div role="tablist" style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
              {(
                [
                  ['paper', 'Paper map'],
                  ['code', 'Coding challenge'],
                ] as const
              ).map(([id, label]) => {
                const active = paperTab === id
                return (
                  <button
                    key={id}
                    role="tab"
                    aria-selected={active}
                    onClick={() => setPaperTab(id)}
                    style={{
                      borderRadius: 200,
                      padding: '6px 16px',
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: 'pointer',
                      border: 'none',
                      background: active ? 'var(--color-iris-bolt)' : 'var(--color-paper-white)',
                      color: active ? '#ffffff' : 'var(--color-slate-veil)',
                      boxShadow: active ? 'var(--shadow-btn)' : 'none',
                    }}
                  >
                    {label}
                  </button>
                )
              })}
            </div>

            <div style={{ flex: 1, minHeight: 0 }}>
              {session.paper && (
                <div style={{ height: '100%', display: paperTab === 'paper' ? 'block' : 'none' }}>
                  <PaperWorkspace
                    key={session.session_id}
                    paper={session.paper}
                    activeNodeId={turn?.diagram_node_id}
                    excerpt={turn?.paper_excerpt}
                  />
                </div>
              )}
              <div style={{ height: '100%', display: paperTab === 'code' ? 'block' : 'none' }}>
                <IdeWorkspace
                  key={session.session_id}
                  sessionId={session.session_id}
                  files={[]}
                  highlight={null}
                  incomingChallenge={turn?.coding_challenge}
                  onRunResult={onRunResult}
                  emptyHint="A coding or algorithmic challenge will appear here when the examiner sets one."
                />
              </div>
            </div>
          </section>

          {/* Right 35%: Examiner */}
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

function ResearchEmptyState({
  busy,
  onUpload,
  onDemo,
}: {
  busy: boolean
  onUpload: () => void
  onDemo: () => void
}) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
      <div style={{ maxWidth: 580, width: '100%', textAlign: 'center' }}>
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: 20,
            background: 'var(--color-pastel-magenta)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 24px',
          }}
        >
          <FileText className="h-8 w-8" style={{ color: '#db2777' }} strokeWidth={1.5} />
        </div>
        <h2 style={{ margin: '0 0 12px', fontSize: 24, fontWeight: 700, color: 'var(--color-ink-charcoal)' }}>
          Research Paper Viva Prep
        </h2>
        <p style={{ margin: '0 0 28px', fontSize: 15, lineHeight: '24px', color: 'var(--color-slate-veil)' }}>
          Upload your scientific or engineering publication in PDF format. The examiner analyzes the paper, builds an interactive
          architecture map, and asks spoken questions challenging your methodology, baselines, and architectural choices.
        </p>

        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn-primary"
            onClick={onUpload}
            disabled={busy}
            style={{ background: '#db2777', padding: '10px 24px' }}
          >
            <FileUp className="h-4 w-4" /> Upload Research PDF
          </button>
          <button className="btn-ghost" onClick={onDemo} disabled={busy} style={{ color: '#db2777', borderColor: '#db2777' }}>
            Load cached demo paper
          </button>
        </div>

        {/* Feature summary card */}
        <div
          style={{
            marginTop: 40,
            background: 'var(--color-paper-white)',
            border: '1px solid var(--color-mist-border)',
            borderRadius: 8,
            textAlign: 'left',
            padding: 20,
            boxShadow: 'var(--shadow-card)',
          }}
        >
          <h3 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 700, color: 'var(--color-ink-charcoal)' }}>
            What the examiner probes in Paper Viva:
          </h3>
          <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: '22px', color: 'var(--color-slate-veil)' }}>
            <li><strong>Methodology & Architecture:</strong> Justifications for pipeline stages, hyperparameter choices, and loss formulations.</li>
            <li><strong>Ablations & Baselines:</strong> Trade-offs against prior art and alternative paradigms.</li>
            <li><strong>Empirical Validity:</strong> Statistical significance, dataset leakage hazards, and scalability limitations.</li>
            <li><strong>Live Evaluation (L4):</strong> Implementation or modification of algorithmic components live in the code tab.</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
