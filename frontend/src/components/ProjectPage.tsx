/**
 * ProjectPage — Repository / Project Interview Prep
 * Wraps the existing repo-viva session flow in the Quizlet light theme.
 */
import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, GitBranch, Mic, Play, RotateCcw, Users } from 'lucide-react'
import IdeWorkspace from './IdeWorkspace'
import ExaminerPanel from './ExaminerPanel'
import ReportModal from './ReportModal'
import { fetchReport, ingestRepo, submitTurn, subscribeDemoMode } from '../services/apiClient'
import type { IngestResponse, RunCodeResponse, TurnResponse, VivaReport } from '../types/api'

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong')

interface Props {
  onBack: () => void
}

export default function ProjectPage({ onBack }: Props) {
  const [session, setSession] = useState<IngestResponse | null>(null)
  const [pendingFirstTurn, setPendingFirstTurn] = useState<TurnResponse | null>(null)
  const [turn, setTurn] = useState<TurnResponse | null>(null)
  const [history, setHistory] = useState<TurnResponse[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [demo, setDemo] = useState(false)
  const [repoUrl, setRepoUrl] = useState('')
  const [author, setAuthor] = useState<string | null>(null)
  const [showReport, setShowReport] = useState(false)
  const [report, setReport] = useState<VivaReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  useEffect(() => subscribeDemoMode(setDemo), [])

  const begin = (res: IngestResponse) => {
    setSession(res); setPendingFirstTurn(res.first_turn)
    setTurn(null); setHistory([]); setReport(null)
  }

  const startViva = useCallback(() => {
    if (!pendingFirstTurn) return
    setTurn(pendingFirstTurn); setHistory([pendingFirstTurn]); setPendingFirstTurn(null)
  }, [pendingFirstTurn])

  async function guarded(fn: () => Promise<void>) {
    setBusy(true); setError(null)
    try { await fn() } catch (e) { setError(errMsg(e)) } finally { setBusy(false) }
  }

  const startRepo = (url: string, a: string | null = null) =>
    guarded(async () => { begin(await ingestRepo(url, a)) })

  const changeAuthor = (a: string | null) => {
    setAuthor(a); if (repoUrl) startRepo(repoUrl, a)
  }

  const onTurn = useCallback((t: TurnResponse) => {
    setTurn(t); setHistory(h => [...h, t])
  }, [])

  const onRunResult = (res: RunCodeResponse) => {
    if (!session) return
    guarded(async () => onTurn(await submitTurn({ session_id: session.session_id, code_result: res })))
  }

  async function finish() {
    if (!session) return
    setShowReport(true); setReportLoading(true); setReportError(null)
    try { setReport(await fetchReport(session.session_id)) }
    catch (e) { setReportError(errMsg(e)) }
    finally { setReportLoading(false) }
  }

  function handleBack() {
    if (session && !window.confirm('Leave this viva? Progress is lost unless you press Finish first.')) return
    onBack()
  }

  const canStart = repoUrl.trim().length > 0 && !busy

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--color-chalk-canvas)' }}>
      {/* ── Top Nav ── */}
      <header style={{
        background: 'var(--color-paper-white)',
        boxShadow: 'var(--shadow-nav)',
        position: 'sticky', top: 0, zIndex: 50,
        flexShrink: 0,
      }}>
        <div style={{
          maxWidth: 1440, margin: '0 auto', padding: '0 16px',
          height: 56, display: 'flex', alignItems: 'center', gap: 12,
        }}>
          {/* Back */}
          <button
            onClick={handleBack}
            style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, color: 'var(--color-slate-veil)', fontSize: 14, padding: '6px 10px', borderRadius: 4 }}
          >
            <ArrowLeft className="h-4 w-4" /> Home
          </button>

          {/* Brand */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Mic className="h-5 w-5" style={{ color: 'var(--color-iris-bolt)' }} strokeWidth={2} />
            <span style={{ fontWeight: 700, fontSize: 17, color: 'var(--color-iris-bolt)' }}>VivaVoce</span>
          </div>

          {/* Mode badge */}
          <span style={{
            background: 'var(--color-pastel-violet)', color: 'var(--color-iris-bolt)',
            fontSize: 12, fontWeight: 700, padding: '3px 12px', borderRadius: 200,
          }}>
            Project Repo Viva
          </span>

          {/* Controls */}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            {/* URL input */}
            <label style={{
              display: 'flex', alignItems: 'center', gap: 8, width: 340, minWidth: 0,
              background: 'var(--color-chalk-canvas)', border: '1px solid var(--color-mist-border)',
              borderRadius: 4, padding: '8px 12px',
            }}>
              <GitBranch className="h-4 w-4 shrink-0" style={{ color: 'var(--color-fog-mist)' }} />
              <input
                value={repoUrl}
                onChange={e => setRepoUrl(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && canStart && startRepo(repoUrl.trim(), author)}
                placeholder="https://github.com/owner/repo"
                style={{
                  flex: 1, minWidth: 0, background: 'transparent', border: 'none', outline: 'none',
                  fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--color-ink-charcoal)',
                }}
              />
            </label>

            {session ? (
              <button
                className="btn-outline"
                onClick={() => startRepo(repoUrl.trim(), author)}
                disabled={!canStart}
              >
                <RotateCcw className="h-4 w-4" /> Restart
              </button>
            ) : (
              <button
                className="btn-primary"
                onClick={() => startRepo(repoUrl.trim(), author)}
                disabled={!canStart}
                style={{ padding: '8px 20px', fontSize: 14 }}
              >
                <Play className="h-4 w-4" />
                {busy ? 'Loading…' : 'Start viva'}
              </button>
            )}

            {/* Demo */}
            <button
              className="btn-outline"
              onClick={() => startRepo('demo_cache/sample_repo', null)}
              disabled={busy}
            >
              Demo repo
            </button>

            {/* Author picker */}
            {(session?.authors ?? []).length > 0 && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--color-slate-veil)' }}>
                <Users className="h-4 w-4" />
                <select
                  value={author ?? ''}
                  onChange={e => changeAuthor(e.target.value || null)}
                  disabled={busy}
                  style={{
                    background: 'var(--color-paper-white)', border: '1px solid var(--color-mist-border)',
                    borderRadius: 4, padding: '6px 10px', fontSize: 13, color: 'var(--color-ink-charcoal)',
                    cursor: 'pointer',
                  }}
                >
                  <option value="">All authors</option>
                  {session?.authors.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </label>
            )}

            {demo && (
              <span style={{ fontSize: 11, color: 'var(--color-fog-mist)', background: 'var(--color-chalk-canvas)', border: '1px solid var(--color-mist-border)', borderRadius: 200, padding: '3px 10px' }}>
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
        <div role="alert" style={{
          borderBottom: '1px solid #fca5a5', background: '#fef2f2',
          padding: '8px 16px', fontSize: 14, color: '#dc2626',
        }}>
          {error}
        </div>
      )}

      {/* ── Main workspace ── */}
      {!session ? (
        <ProjectEmptyState busy={busy} onDemo={() => startRepo('demo_cache/sample_repo', null)} />
      ) : (
        <main style={{ display: 'flex', flex: 1, minHeight: 0, maxWidth: 1440, margin: '0 auto', width: '100%' }}>
          <section style={{ display: 'flex', flexDirection: 'column', flex: '0 0 65%', minWidth: 0, padding: 12, gap: 8 }}>
            <IdeWorkspace
              key={session.session_id}
              sessionId={session.session_id}
              files={session.files}
              highlight={turn?.highlight}
              incomingChallenge={turn?.coding_challenge}
              onRunResult={onRunResult}
            />
          </section>
          <aside style={{
            flex: '0 0 35%', minWidth: 0,
            borderLeft: '1px solid var(--color-mist-border)',
            background: 'var(--color-paper-white)',
          }}>
            <ExaminerPanel
              sessionId={session.session_id} mode={session.mode}
              turn={turn} history={history} busy={busy} onTurn={onTurn} onStartViva={startViva}
            />
          </aside>
        </main>
      )}

      {showReport && (
        <ReportModal report={report} loading={reportLoading} error={reportError} onClose={() => setShowReport(false)} />
      )}
    </div>
  )
}

function ProjectEmptyState({ busy, onDemo }: { busy: boolean; onDemo: () => void }) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
      <div style={{ maxWidth: 560, width: '100%', textAlign: 'center' }}>
        <div style={{
          width: 72, height: 72, borderRadius: 20, background: 'var(--color-pastel-violet)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px',
        }}>
          <GitBranch className="h-8 w-8" style={{ color: 'var(--color-iris-bolt)' }} strokeWidth={1.5} />
        </div>
        <h2 style={{ margin: '0 0 12px', fontSize: 24, fontWeight: 700, color: 'var(--color-ink-charcoal)' }}>
          Repository Interview Prep
        </h2>
        <p style={{ margin: '0 0 28px', fontSize: 15, lineHeight: '24px', color: 'var(--color-slate-veil)' }}>
          Paste a GitHub repository URL in the top bar and press <strong>Start viva</strong>. 
          The examiner will walk through your code with escalating questions — from recall to live coding challenges.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <button className="btn-ghost" onClick={onDemo} disabled={busy} style={{ fontSize: 14, padding: '8px 20px' }}>
            Try with demo repo
          </button>
        </div>

        {/* Depth ladder reminder */}
        <div style={{
          marginTop: 40, background: 'var(--color-paper-white)',
          border: '1px solid var(--color-mist-border)', borderRadius: 8, overflow: 'hidden',
        }}>
          {[
            { level: 'L1', name: 'Recall', desc: 'What does this function do?' },
            { level: 'L2', name: 'Comprehend', desc: 'Why was it implemented this way?' },
            { level: 'L3', name: 'Analyze', desc: 'What are the trade-offs vs the alternative?' },
            { level: 'L4', name: 'Evaluate', desc: 'What breaks if it changes? Fix it live.' },
          ].map((r, i) => (
            <div key={r.level} style={{
              display: 'flex', alignItems: 'baseline', gap: 12, padding: '12px 16px',
              borderTop: i > 0 ? '1px solid var(--color-mist-border)' : 'none',
              textAlign: 'left',
            }}>
              <span style={{ width: 28, fontWeight: 700, fontSize: 12, color: 'var(--color-iris-bolt)', fontFamily: 'var(--font-mono)' }}>{r.level}</span>
              <span style={{ width: 110, fontSize: 13, fontWeight: 600, color: 'var(--color-ink-charcoal)', flexShrink: 0 }}>{r.name}</span>
              <span style={{ fontSize: 13, color: 'var(--color-slate-veil)' }}>{r.desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
