/**
 * ResearchPage — Research Paper Explorer
 * Full-width, evidence-linked research paper breakdown and visual explorer.
 * Upload any research-paper PDF (or load the offline demo paper) to inspect
 * structured explanations, methodology flow, comparative results, and source citations.
 */
import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, BookOpen, FileText, FileUp, Loader2 } from 'lucide-react'
import PaperWorkspace from './PaperWorkspace'
import { ingestPdf, subscribeDemoMode } from '../services/apiClient'
import type { IngestResponse } from '../types/api'

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong while reading the PDF.')

interface Props {
  onBack: () => void
}

export default function ResearchPage({ onBack }: Props) {
  const [session, setSession] = useState<IngestResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [demo, setDemo] = useState(false)
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => subscribeDemoMode(setDemo), [])

  const loadPaper = async (file: File | null) => {
    setBusy(true)
    setError(null)
    const label = file ? file.name : 'sample_paper.pdf (Demo)'
    try {
      const res = await ingestPdf(file)
      setSelectedFileName(label)
      setSession(res)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full w-full flex-col bg-[#f6f7fb] text-[#282e3e]">
      {/* ── Sticky Single-Row Top Header ───────────────────────────────────── */}
      <header className="sticky top-0 z-30 border-b border-[#d9dde8] bg-[#ffffff]">
        <div className="mx-auto flex max-w-[1160px] flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 rounded-[4px] px-2.5 py-1.5 text-[13px] font-medium text-[#586380] hover:bg-[#f6f7fb] hover:text-[#282e3e] cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
            Home
          </button>

          <div className="h-4 w-px bg-[#d9dde8]" aria-hidden />

          <div className="flex items-center gap-2">
            <BookOpen className="h-5 w-5 text-[#4255ff]" strokeWidth={2} />
            <span className="text-[16px] font-bold tracking-tight text-[#282e3e]">
              Research Paper Explorer
            </span>
          </div>

          {selectedFileName && (
            <span
              className="max-w-[240px] truncate rounded-[200px] border border-[#d9dde8] bg-[#f6f7fb] px-3 py-1 text-[12px] font-medium text-[#586380]"
              title={selectedFileName}
            >
              {selectedFileName}
            </span>
          )}

          {demo && (
            <span className="rounded-[200px] border border-[#fde68a] bg-[#fffbeb] px-2.5 py-0.5 text-[11px] font-semibold text-[#b45309]">
              Offline demo mode
            </span>
          )}

          <div className="ml-auto flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={e => {
                const f = e.target.files?.[0]
                if (f) loadPaper(f)
                e.target.value = ''
              }}
            />

            <button
              type="button"
              className="btn-outline"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
              Upload PDF
            </button>

            <button
              type="button"
              className="btn-outline"
              onClick={() => loadPaper(null)}
              disabled={busy}
            >
              Demo paper
            </button>
          </div>
        </div>
      </header>

      {/* ── Upload / Extraction Status Banners ─────────────────────────────── */}
      {busy && session && (
        <div
          role="status"
          className="border-b border-[#c7d2fe] bg-[#edefff] px-4 py-2.5 text-[13px] font-medium text-[#4255ff]"
        >
          <div className="mx-auto flex max-w-[1160px] items-center gap-2 sm:px-2">
            <Loader2 className="h-4 w-4 animate-spin shrink-0" />
            Extracting PDF text, verifying page provenance, and mapping the paper…
          </div>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="border-b border-[#fca5a5] bg-[#fef2f2] px-4 py-3 text-[13px] text-[#b91c1c]"
        >
          <div className="mx-auto flex max-w-[1160px] flex-wrap items-center justify-between gap-2 sm:px-2">
            <span>
              <strong>Could not analyze PDF:</strong> {error}
            </span>
            <button
              type="button"
              onClick={() => loadPaper(null)}
              className="rounded-[4px] border border-[#fca5a5] bg-[#ffffff] px-3 py-1 text-[12px] font-semibold text-[#b91c1c] hover:bg-[#fee2e2] cursor-pointer"
            >
              Try Demo paper
            </button>
          </div>
        </div>
      )}

      {/* ── Main Content (Single Document Scroll, Full Width) ───────────────── */}
      {!session?.paper ? (
        <ResearchEmptyState
          busy={busy}
          onUpload={() => fileInputRef.current?.click()}
          onDemo={() => loadPaper(null)}
        />
      ) : (
        <main className="mx-auto w-full max-w-[1160px] flex-1 px-4 py-6 sm:px-6 sm:py-8">
          <PaperWorkspace
            key={session.session_id}
            paper={session.paper}
            onUpload={() => fileInputRef.current?.click()}
            onDemo={() => loadPaper(null)}
          />
        </main>
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
    <main className="mx-auto flex w-full max-w-[820px] flex-1 flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-[#edefff] text-[#4255ff]">
        <FileText className="h-8 w-8" strokeWidth={1.6} />
      </div>

      <h1 className="m-0 text-[28px] font-bold tracking-tight text-[#282e3e] sm:text-[32px]">
        Understand any research paper clearly
      </h1>
      <p className="mt-3 max-w-[600px] text-[15px] leading-6 text-[#586380]">
        Upload a research-paper PDF to read a structured, page-cited breakdown of the problem, step-by-step method,
        experiments, results, limitations, and key terminology — with every claim linked back to its source passage.
      </p>

      {busy && (
        <div
          role="status"
          className="mt-6 inline-flex items-center gap-2 rounded-[8px] border border-[#c7d2fe] bg-[#edefff] px-4 py-2.5 text-[13.5px] font-semibold text-[#4255ff]"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Extracting text, ignoring headers & watermarks, and building your paper breakdown…
        </div>
      )}

      <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
        <button type="button" className="btn-primary" onClick={onUpload} disabled={busy}>
          <FileUp className="h-4 w-4" />
          {busy ? 'Analyzing PDF…' : 'Upload Research PDF'}
        </button>
        <button type="button" className="btn-ghost" onClick={onDemo} disabled={busy}>
          {busy ? 'Loading demo…' : 'Load Demo Paper'}
        </button>
      </div>

      <div className="mt-10 grid w-full grid-cols-1 gap-4 text-left sm:grid-cols-3">
        <div className="card p-5">
          <div className="text-[13px] font-bold text-[#282e3e]">Metadata & Provenance</div>
          <p className="mt-1.5 text-[13px] leading-5 text-[#586380]">
            Separates title, authors, and venue from watermarks, and attaches exact page citations to every passage.
          </p>
        </div>
        <div className="card p-5">
          <div className="text-[13px] font-bold text-[#282e3e]">Method Flow & Story Map</div>
          <p className="mt-1.5 text-[13px] leading-5 text-[#586380]">
            Visualizes the paper’s Problem → Approach → Evidence → Conclusion flow and clickable method stages.
          </p>
        </div>
        <div className="card p-5">
          <div className="text-[13px] font-bold text-[#282e3e]">Honest Uncertainty</div>
          <p className="mt-1.5 text-[13px] leading-5 text-[#586380]">
            Separates author statements from generated summaries, detects scanned PDFs gracefully, and never fabricates charts.
          </p>
        </div>
      </div>
    </main>
  )
}
