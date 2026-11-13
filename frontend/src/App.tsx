import { useCallback, useEffect, useState } from 'react'
import TopNavbar from './components/TopNavbar'
import EmptyState from './components/EmptyState'
import IdeWorkspace from './components/IdeWorkspace'
import PaperWorkspace from './components/PaperWorkspace'
import ExaminerPanel from './components/ExaminerPanel'
import ReportModal from './components/ReportModal'
import { fetchReport, ingestPdf, ingestRepo, submitTurn, subscribeDemoMode } from './services/apiClient'
import type { IngestResponse, RunCodeResponse, TurnResponse, VivaReport } from './types/api'

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong')

export default function App() {
  const [session, setSession] = useState<IngestResponse | null>(null)
  const [pendingFirstTurn, setPendingFirstTurn] = useState<TurnResponse | null>(null)
  const [turn, setTurn] = useState<TurnResponse | null>(null)
  const [history, setHistory] = useState<TurnResponse[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [demo, setDemo] = useState(false)
  const [repoUrl, setRepoUrl] = useState<string | null>(null)
  const [author, setAuthor] = useState<string | null>(null)
  const [homeKey, setHomeKey] = useState(0)
  const [paperTab, setPaperTab] = useState<'paper' | 'code'>('paper')
  const [showReport, setShowReport] = useState(false)
  const [report, setReport] = useState<VivaReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  useEffect(() => subscribeDemoMode(setDemo), [])

  // Paper mode: a coding challenge switches the left panel to the IDE
  useEffect(() => {
    if (session?.mode !== 'paper' || !turn) return
    if (turn.coding_challenge) setPaperTab('code')
    else if (turn.diagram_node_id) setPaperTab('paper')
  }, [turn, session])

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
    setBusy(true); setError(null)
    try { await fn() } catch (e) { setError(errMsg(e)) } finally { setBusy(false) }
  }

  const startRepo = (url: string, a: string | null = null) => guarded(async () => {
    setRepoUrl(url); setAuthor(a); begin(await ingestRepo(url, a))
  })
  const startPaper = (file: File | null) => guarded(async () => {
    setRepoUrl(null); setAuthor(null); begin(await ingestPdf(file))
  })
  const changeAuthor = (a: string | null) => { if (repoUrl) startRepo(repoUrl, a); else setAuthor(a) }

  function goHome() {
    if (session && !window.confirm('Leave this viva? Progress is lost unless you press Finish viva first.')) return
    setSession(null); setPendingFirstTurn(null); setTurn(null); setHistory([]); setReport(null); setShowReport(false)
    setError(null); setRepoUrl(null); setAuthor(null); setPaperTab('paper'); setHomeKey(k => k + 1)
  }

  const onTurn = useCallback((t: TurnResponse) => {
    setTurn(t); setHistory(h => [...h, t])
  }, [])

  // Sandbox result goes back to the examiner as the next turn
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

  return (
    <div className="flex h-full flex-col">
      <TopNavbar
        key={homeKey}
        mode={session?.mode ?? null} hasSession={!!session} busy={busy} demo={demo}
        authors={session?.authors ?? []} author={author} onAuthorChange={changeAuthor}
        onStartRepo={url => startRepo(url, null)} onUploadPdf={startPaper} onFinish={finish} onHome={goHome}
      />

      {error && (
        <div role="alert" className="border-b border-steel-outline bg-deep-slate px-4 py-2 text-sm text-pale-frost">
          {error}
        </div>
      )}

      <main className="mx-auto flex min-h-0 w-full max-w-[1440px] flex-1">
        {/* Left 65%: workspace */}
        <section className="flex min-w-0 basis-[65%] flex-col gap-2 p-3" aria-label="Workspace">
          {!session ? (
            <EmptyState busy={busy} onDemoRepo={() => startRepo('demo_cache/sample_repo')} onDemoPaper={() => startPaper(null)} />
          ) : session.mode === 'repo' ? (
            <IdeWorkspace
              key={session.session_id}
              sessionId={session.session_id} files={session.files}
              highlight={turn?.highlight} incomingChallenge={turn?.coding_challenge} onRunResult={onRunResult}
            />
          ) : (
            <>
              <div role="tablist" className="flex shrink-0 gap-1">
                {([['paper', 'Paper map'], ['code', 'Coding challenge']] as const).map(([id, label]) => (
                  <button key={id} role="tab" aria-selected={paperTab === id} onClick={() => setPaperTab(id)}
                    className={`rounded-md px-2.5 py-1.5 text-sm font-medium ${paperTab === id ? 'bg-deep-slate text-signal-white' : 'text-muted-fog hover:text-pale-frost'}`}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="min-h-0 flex-1">
                {session.paper && (
                  <div className={paperTab === 'paper' ? 'h-full' : 'hidden'}>
                    <PaperWorkspace key={session.session_id} paper={session.paper}
                      activeNodeId={turn?.diagram_node_id} excerpt={turn?.paper_excerpt} />
                  </div>
                )}
                <div className={paperTab === 'code' ? 'h-full' : 'hidden'}>
                  <IdeWorkspace key={session.session_id} sessionId={session.session_id} files={[]}
                    highlight={null} incomingChallenge={turn?.coding_challenge} onRunResult={onRunResult}
                    emptyHint="A coding challenge appears here when the examiner sets one." />
                </div>
              </div>
            </>
          )}
        </section>

        {/* Right 35%: always-on examiner */}
        <aside className="min-w-0 basis-[35%] border-l border-steel-outline" aria-label="Examiner">
          <ExaminerPanel
            sessionId={session?.session_id ?? null} mode={session?.mode ?? null}
            turn={turn} history={history} busy={busy} onTurn={onTurn} onStartViva={startViva}
          />
        </aside>
      </main>

      {showReport && (
        <ReportModal report={report} loading={reportLoading} error={reportError} onClose={() => setShowReport(false)} />
      )}
    </div>
  )
}
