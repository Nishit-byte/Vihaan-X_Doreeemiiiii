import { useEffect, useId, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Compass,
  FileText,
  Info,
  Layers,
  X,
} from 'lucide-react'
import type {
  BreakdownField,
  ClaimOrigin,
  DiagramProvenance,
  EvidenceRef,
  GlossaryItem,
  MethodologyStep,
  PaperBreakdown,
  PaperIndex,
  ResultDataPoint,
} from '../types/api'

interface Props {
  paper: PaperIndex
  onUpload?: () => void
  onDemo?: () => void
}

type SubView = 'overview' | 'breakdown'

export interface EvidenceSelection {
  id: string
  title: string
  section: string
  page: number | null
  explanation?: string | null
  excerpt: string
  origin: ClaimOrigin
  nodeId?: string | null
}

const nodeIdOf = (el: Element) => el.id.match(/flowchart-(.+)-\d+$/)?.[1] ?? null

function provenanceLabel(prov: DiagramProvenance | null | undefined) {
  return prov === 'reconstructed_from_paper' ? 'Reconstructed from the paper' : 'Conceptual explanation'
}

function originText(origin: ClaimOrigin, found = true) {
  if (!found) return 'Not found in the paper'
  return origin === 'author_claim' ? 'Author statement' : 'App explanation'
}

export default function PaperWorkspace({ paper, onUpload, onDemo }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const uid = useId().replace(/:/g, '')
  const [subView, setSubView] = useState<SubView>('overview')
  const [ready, setReady] = useState(false)
  const [diagramError, setDiagramError] = useState<string | null>(null)
  const [labels, setLabels] = useState<Record<string, string>>({})
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceSelection | null>(null)
  const [activeNavId, setActiveNavId] = useState<string>('sec-abstract')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  const breakdown: PaperBreakdown | null = paper.breakdown ?? null
  const isScannedOrEmpty = breakdown?.extraction_status === 'scanned_or_empty'
  const hasMethodDiagram =
    !isScannedOrEmpty &&
    breakdown?.methodology_diagram_status !== 'fallback' &&
    Boolean(paper.mermaid?.trim()) &&
    Object.keys(paper.nodes).length >= 3

  // Escape closes the compact evidence drawer
  useEffect(() => {
    if (!selectedEvidence) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedEvidence(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedEvidence])

  // Render Mermaid diagram whenever Overview is shown and diagram exists
  useEffect(() => {
    if (subView !== 'overview' || !hasMethodDiagram || !paper.mermaid?.trim()) return
    let cancelled = false
    setReady(false)
    setDiagramError(null)
    ;(async () => {
      try {
        const mermaid = (await import('mermaid')).default
        mermaid.initialize({
          startOnLoad: false,
          theme: 'base',
          themeVariables: {
            background: '#ffffff',
            primaryColor: '#edefff',
            primaryTextColor: '#282e3e',
            primaryBorderColor: '#c7d2fe',
            lineColor: '#586380',
            fontFamily: 'Inter, sans-serif',
            fontSize: '13px',
          },
          flowchart: { curve: 'basis', padding: 14 },
        })
        const { svg } = await mermaid.render('vv' + uid + Math.random().toString(36).slice(2, 6), paper.mermaid)
        if (cancelled || !hostRef.current) return
        hostRef.current.innerHTML = svg
        const map: Record<string, string> = {}
        hostRef.current.querySelectorAll('g.node').forEach(g => {
          const id = nodeIdOf(g)
          if (id) map[id] = (g.textContent ?? '').trim()
        })
        setLabels(map)
        setReady(true)
      } catch (e) {
        if (!cancelled) setDiagramError(e instanceof Error ? e.message : 'Could not render diagram')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [paper.mermaid, uid, subView, hasMethodDiagram])

  useEffect(() => {
    if (!ready || !hostRef.current) return
    hostRef.current.querySelectorAll('g.node').forEach(g =>
      g.classList.toggle('vv-active', nodeIdOf(g) === selectedEvidence?.nodeId)
    )
  }, [ready, selectedEvidence])

  const openNodeEvidence = (nodeId: string) => {
    const meta = paper.node_meta?.[nodeId]
    const excerpt = meta?.excerpt ?? paper.nodes[nodeId]
    if (!excerpt) return
    setSelectedEvidence({
      id: `node-${nodeId}`,
      title: meta?.label ?? labels[nodeId] ?? `Stage ${nodeId}`,
      section: meta?.section ?? 'Methodology',
      page: meta?.page ?? 1,
      explanation: meta?.summary ?? null,
      excerpt,
      origin: 'author_claim',
      nodeId,
    })
  }

  const openFieldEvidence = (id: string, field: BreakdownField, overrideTitle?: string) => {
    const excerpt = field.supporting_excerpt || field.value
    setSelectedEvidence({
      id,
      title: overrideTitle ?? field.label,
      section: field.section ?? 'Extracted Section',
      page: field.page ?? 1,
      explanation: field.plain_language ?? null,
      excerpt,
      origin: field.origin,
      nodeId: null,
    })
  }

  const maxQuantitativeVal = useMemo(() => {
    if (!breakdown?.quantitative_results?.length) return 100
    const vals: number[] = []
    for (const r of breakdown.quantitative_results) {
      if (typeof r.proposed_value === 'number') vals.push(Math.abs(r.proposed_value))
      if (typeof r.baseline_value === 'number') vals.push(Math.abs(r.baseline_value))
      if (typeof r.numeric_value === 'number') vals.push(Math.abs(r.numeric_value))
    }
    return vals.length ? Math.max(...vals, 100) : 100
  }, [breakdown])

  const navSections = useMemo(
    () => [
      { id: 'sec-abstract', label: 'Abstract & Purpose' },
      { id: 'sec-problem', label: 'Problem & Prior Work' },
      { id: 'sec-method', label: 'Proposed Method' },
      { id: 'sec-steps', label: 'Step-by-Step Pipeline' },
      { id: 'sec-results', label: 'Data, Setup & Results' },
      { id: 'sec-discussion', label: 'Contributions & Limits' },
      { id: 'sec-glossary', label: 'Technical Glossary' },
    ],
    []
  )

  const jumpToSection = (id: string) => {
    setActiveNavId(id)
    setMobileNavOpen(false)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="space-y-6">
      {/* ── Scanned / Image-Only PDF Graceful Notice ──────────────────────── */}
      {isScannedOrEmpty && (
        <div
          role="status"
          className="rounded-[8px] border border-[#fde68a] bg-[#fffbeb] p-4 text-[13.5px] text-[#92400e]"
        >
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[#d97706]" />
            <div className="space-y-2">
              <div className="font-bold">Scanned or image-only PDF detected</div>
              <p className="m-0 leading-5">
                {breakdown?.extraction_notice ??
                  'No selectable text layer was found in this PDF. Rather than guessing missing details, unavailable fields are marked accordingly. Run OCR on the PDF first, or inspect the Demo Paper.'}
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                {onUpload && (
                  <button
                    type="button"
                    onClick={onUpload}
                    className="rounded-[4px] border border-[#fcd34d] bg-[#ffffff] px-3 py-1.5 text-[12px] font-semibold text-[#92400e] hover:bg-[#fef3c7] cursor-pointer"
                  >
                    Upload searchable PDF
                  </button>
                )}
                {onDemo && (
                  <button
                    type="button"
                    onClick={onDemo}
                    className="rounded-[4px] bg-[#b45309] px-3 py-1.5 text-[12px] font-semibold text-[#ffffff] hover:opacity-90 cursor-pointer"
                  >
                    Load Demo Paper
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Paper Header Card & View Switcher ─────────────────────────────── */}
      <section className="card p-5 sm:p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-[12px] text-[#586380]">
              <span className="font-semibold text-[#4255ff]">
                {breakdown ? `${breakdown.page_count} ${breakdown.page_count === 1 ? 'page' : 'pages'} indexed` : 'Paper Indexed'}
              </span>
              {breakdown?.venue_and_year?.found && (
                <>
                  <span aria-hidden>·</span>
                  <button
                    type="button"
                    onClick={() => openFieldEvidence('venue_and_year', breakdown.venue_and_year)}
                    className="text-left font-medium text-[#2e3856] hover:text-[#4255ff] hover:underline cursor-pointer"
                  >
                    {breakdown.venue_and_year.value}
                  </button>
                </>
              )}
              {breakdown?.title_status === 'uncertain' && (
                <span className="rounded-[4px] bg-[#fef3c7] px-2 py-0.5 text-[11px] font-semibold text-[#b45309]">
                  Title confidence uncertain
                </span>
              )}
            </div>

            <h1 className="m-0 text-[22px] font-bold leading-snug text-[#282e3e] sm:text-[26px]">
              {breakdown?.title ?? 'Uploaded Research Paper'}
            </h1>

            {breakdown && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 text-[13.5px] text-[#586380]">
                <div>
                  <span className="font-semibold text-[#282e3e]">Authors: </span>
                  <span className={breakdown.authors_status === 'identified' ? 'text-[#282e3e]' : 'italic text-[#586380]'}>
                    {breakdown.authors_and_affiliations.value}
                  </span>
                </div>

                {!breakdown.venue_and_year.found && (
                  <div>
                    <span className="font-semibold text-[#282e3e]">Venue / Year: </span>
                    <span className="italic text-[#586380]">Not found in the paper</span>
                  </div>
                )}

                {breakdown.title_block_excerpt && (
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedEvidence({
                        id: 'page1-header',
                        title: 'Page 1 Title & Header Block',
                        section: 'Page 1 Top Region',
                        page: 1,
                        explanation:
                          breakdown.authors_status === 'identified'
                            ? 'Raw top-of-page lines used to verify title, authors, and publication venue.'
                            : 'Author names were ambiguous or omitted above the Abstract. Inspect the extracted Page 1 header below.',
                        excerpt: breakdown.title_block_excerpt || '',
                        origin: 'author_claim',
                      })
                    }
                    className="text-[12px] font-semibold text-[#4255ff] hover:underline cursor-pointer"
                  >
                    Inspect Page 1 header →
                  </button>
                )}
              </div>
            )}
          </div>

          {/* 2 Clean Views: Overview & Full Breakdown */}
          <div
            role="tablist"
            aria-label="Paper Explorer views"
            className="inline-flex shrink-0 self-start rounded-[200px] border border-[#d9dde8] bg-[#f6f7fb] p-1"
          >
            {(
              [
                { id: 'overview', label: 'Overview', icon: Compass },
                { id: 'breakdown', label: 'Full Breakdown', icon: BookOpen },
              ] as const
            ).map(({ id, label, icon: Icon }) => {
              const active = subView === id
              return (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setSubView(id)}
                  className={`inline-flex items-center gap-1.5 rounded-[200px] px-4 py-1.5 text-[13px] font-semibold transition-colors cursor-pointer ${
                    active
                      ? 'bg-[#4255ff] text-[#ffffff]'
                      : 'text-[#586380] hover:text-[#282e3e]'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {label}
                </button>
              )
            })}
          </div>
        </div>
      </section>

      {/* =====================================================================
          VIEW 1: OVERVIEW
         ===================================================================== */}
      {subView === 'overview' && breakdown && (
        <div className="space-y-6">
          {/* 1. What This Paper Does */}
          <section className="card p-5 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="m-0 text-[16px] font-bold text-[#282e3e]">What this paper is about</h2>
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-[#586380]">
                  {breakdown.what_this_paper_does.plain_language ? 'App explanation + Author abstract' : 'Author statement from abstract'}
                </span>
                {breakdown.what_this_paper_does.page && (
                  <button
                    type="button"
                    onClick={() => openFieldEvidence('what_this_paper_does', breakdown.what_this_paper_does)}
                    className="font-semibold text-[#4255ff] hover:underline cursor-pointer"
                  >
                    Source (p. {breakdown.what_this_paper_does.page})
                  </button>
                )}
              </div>
            </div>

            {breakdown.what_this_paper_does.plain_language ? (
              <div className="mt-3 space-y-3">
                <div className="rounded-[8px] bg-[#edefff] px-4 py-3 text-[14.5px] leading-6 text-[#282e3e]">
                  <span className="font-semibold text-[#4255ff]">In plain language: </span>
                  {breakdown.what_this_paper_does.plain_language}
                </div>
                <p className="m-0 text-[14px] leading-6 text-[#586380]">
                  <strong className="text-[#282e3e]">Abstract summary: </strong>
                  {breakdown.what_this_paper_does.value}
                </p>
              </div>
            ) : (
              <p className="mt-3 m-0 text-[14.5px] leading-6 text-[#2e3856]">
                {breakdown.what_this_paper_does.value}
              </p>
            )}
          </section>

          {/* 2. Problem -> Approach -> Evidence -> Conclusion Story Map */}
          {breakdown.story_map.length > 0 && (
            <section className="card p-5 sm:p-6">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-[#4255ff]" />
                  <h2 className="m-0 text-[16px] font-bold text-[#282e3e]">
                    Problem → Approach → Evidence → Conclusion
                  </h2>
                </div>
                <ProvenanceTag provenance={breakdown.story_map_provenance} />
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {breakdown.story_map.map((stage, idx) => {
                  const sid = `story-${idx}`
                  const isActive = selectedEvidence?.id === sid
                  return (
                    <button
                      key={sid}
                      type="button"
                      onClick={() => openFieldEvidence(sid, stage)}
                      className={`flex flex-col justify-between rounded-[8px] border p-4 text-left transition-colors cursor-pointer ${
                        isActive
                          ? 'border-[#4255ff] bg-[#edefff]/50'
                          : 'border-[#d9dde8] bg-[#f6f7fb] hover:border-[#939bb4]'
                      }`}
                    >
                      <div>
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <span className="text-[12px] font-bold uppercase tracking-wide text-[#4255ff]">
                            {idx + 1}. {stage.label}
                          </span>
                          {stage.page && (
                            <span className="text-[11px] font-semibold text-[#586380]">p. {stage.page}</span>
                          )}
                        </div>
                        <p className="m-0 text-[13.5px] leading-5 text-[#282e3e]">{stage.value}</p>
                      </div>

                      <div className="mt-3 flex items-center justify-between border-t border-[#d9dde8]/70 pt-2 text-[11.5px]">
                        <span className="text-[#586380]">{originText(stage.origin, stage.found)}</span>
                        <span className="font-semibold text-[#4255ff]">View excerpt →</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </section>
          )}

          {/* 3. Interactive Methodology Flow Diagram (or Honest Fallback) */}
          <section className="card p-5 sm:p-6">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="m-0 text-[16px] font-bold text-[#282e3e]">How the Proposed Method Works</h2>
                <p className="m-0 mt-0.5 text-[12.5px] text-[#586380]">
                  {hasMethodDiagram
                    ? 'Click any stage to read its explanation, verbatim source passage, and exact page.'
                    : 'Method pipeline overview'}
                </p>
              </div>
              <ProvenanceTag provenance={breakdown.methodology_diagram_provenance} />
            </div>

            {hasMethodDiagram ? (
              <>
                <div className="overflow-x-auto rounded-[8px] border border-[#d9dde8] bg-[#ffffff] p-4">
                  {diagramError ? (
                    <p className="m-0 text-[13px] text-[#586380]">
                      Diagram layout unavailable ({diagramError}). Select any stage below to inspect it.
                    </p>
                  ) : (
                    <>
                      {!ready && (
                        <p className="m-0 text-[13px] text-[#586380]">Rendering method flow diagram…</p>
                      )}
                      <div
                        ref={hostRef}
                        className="mermaid-host flex justify-center"
                        onClick={e => {
                          const g = (e.target as Element).closest('g.node')
                          if (!g) return
                          const id = nodeIdOf(g)
                          if (id && paper.nodes[id]) openNodeEvidence(id)
                        }}
                      />
                    </>
                  )}
                </div>

                {/* Accessible stage cards/buttons */}
                <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.keys(paper.nodes).map(nodeId => {
                    const meta = paper.node_meta?.[nodeId]
                    const isActive = selectedEvidence?.nodeId === nodeId
                    return (
                      <button
                        key={nodeId}
                        type="button"
                        onClick={() => openNodeEvidence(nodeId)}
                        className={`flex items-start justify-between gap-2 rounded-[6px] border px-3.5 py-2.5 text-left transition-colors cursor-pointer ${
                          isActive
                            ? 'border-[#4255ff] bg-[#edefff]/60'
                            : 'border-[#d9dde8] bg-[#f6f7fb] hover:border-[#939bb4]'
                        }`}
                      >
                        <div className="min-w-0">
                          <div className="text-[12.5px] font-bold text-[#282e3e]">
                            <span className="mr-1.5 font-mono text-[#4255ff]">{nodeId}</span>
                            {meta?.label ?? labels[nodeId] ?? 'Stage'}
                          </div>
                          {meta?.summary && (
                            <p className="mt-0.5 line-clamp-2 text-[12px] leading-4 text-[#586380]">
                              {meta.summary}
                            </p>
                          )}
                        </div>
                        <span className="shrink-0 text-[11px] font-semibold text-[#4255ff]">
                          p. {meta?.page ?? 1}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </>
            ) : (
              <div className="rounded-[8px] border border-dashed border-[#d9dde8] bg-[#f6f7fb] p-4 text-[13.5px] leading-6 text-[#586380]">
                {breakdown.methodology_diagram_note ??
                  'A clear sequential method pipeline could not be reconstructed reliably from this paper. Refer to the Problem → Approach → Evidence → Conclusion map above or read the Full Breakdown tab.'}
              </div>
            )}
          </section>

          {/* 4. Results & Key Takeaways Row */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Quantitative Results (ONLY when true comparisons exist) */}
            <section className="card p-5 sm:p-6">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-[#4255ff]" />
                  <h2 className="m-0 text-[16px] font-bold text-[#282e3e]">Results & Evidence</h2>
                </div>
                {breakdown.quantitative_results.length > 0 && breakdown.results_chart_provenance && (
                  <ProvenanceTag provenance={breakdown.results_chart_provenance} />
                )}
              </div>

              {breakdown.quantitative_results.length > 0 ? (
                <div className="space-y-3">
                  {breakdown.quantitative_results.map((res, idx) => (
                    <ResultComparisonCard
                      key={`quant-${idx}`}
                      res={res}
                      maxVal={maxQuantitativeVal}
                      active={selectedEvidence?.id === `quant-${idx}`}
                      onInspect={() =>
                        setSelectedEvidence({
                          id: `quant-${idx}`,
                          title: `${res.metric_label}: ${res.value_display}`,
                          section: res.section,
                          page: res.page,
                          explanation: res.comparison_context ?? res.baseline_or_context,
                          excerpt: res.excerpt,
                          origin: 'author_claim',
                        })
                      }
                    />
                  ))}
                </div>
              ) : (
                <div className="space-y-2.5 rounded-[8px] border border-[#d9dde8] bg-[#f6f7fb] p-4 text-[13.5px] leading-6 text-[#2e3856]">
                  <p className="m-0">
                    {breakdown.results_summary_note ?? breakdown.main_results.value}
                  </p>
                  {breakdown.main_results.found && breakdown.main_results.page && (
                    <button
                      type="button"
                      onClick={() => openFieldEvidence('main_results', breakdown.main_results)}
                      className="text-[12.5px] font-semibold text-[#4255ff] hover:underline cursor-pointer"
                    >
                      Inspect cited passage (p. {breakdown.main_results.page}) →
                    </button>
                  )}
                </div>
              )}
            </section>

            {/* Key Takeaways */}
            <section className="card p-5 sm:p-6">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="m-0 text-[16px] font-bold text-[#282e3e]">Key Takeaways</h2>
                <span className="text-[12px] text-[#586380]">Click any point for source text</span>
              </div>

              {breakdown.key_takeaways.length > 0 ? (
                <div className="space-y-2.5">
                  {breakdown.key_takeaways.map((tk, idx) => {
                    const tid = `takeaway-${idx}`
                    const active = selectedEvidence?.id === tid
                    return (
                      <button
                        key={tid}
                        type="button"
                        onClick={() => openFieldEvidence(tid, tk)}
                        className={`w-full rounded-[8px] border p-3.5 text-left transition-colors cursor-pointer ${
                          active
                            ? 'border-[#4255ff] bg-[#edefff]/50'
                            : 'border-[#d9dde8] bg-[#f6f7fb] hover:border-[#939bb4]'
                        }`}
                      >
                        <div className="mb-1 flex items-center justify-between text-[11.5px]">
                          <span className="font-semibold text-[#4255ff]">{tk.label}</span>
                          <span className="text-[#586380]">
                            {originText(tk.origin, tk.found)} · p. {tk.page ?? 1}
                          </span>
                        </div>
                        <p className="m-0 text-[13.5px] leading-5 text-[#282e3e]">{tk.value}</p>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <p className="m-0 text-[13.5px] italic text-[#586380]">
                  No key takeaways could be extracted cleanly.
                </p>
              )}
            </section>
          </div>
        </div>
      )}

      {/* =====================================================================
          VIEW 2: FULL BREAKDOWN (Sticky Sidebar + Single Page Document Scroll)
         ===================================================================== */}
      {subView === 'breakdown' && breakdown && (
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          {/* Mobile collapsible section jump bar */}
          <div className="lg:hidden">
            <button
              type="button"
              onClick={() => setMobileNavOpen(o => !o)}
              className="flex w-full items-center justify-between rounded-[8px] border border-[#d9dde8] bg-[#ffffff] px-4 py-2.5 text-[13.5px] font-semibold text-[#282e3e] cursor-pointer"
            >
              <span>Jump to section or page</span>
              <ChevronDown className={`h-4 w-4 transition-transform ${mobileNavOpen ? 'rotate-180' : ''}`} />
            </button>
            {mobileNavOpen && (
              <div className="mt-2 rounded-[8px] border border-[#d9dde8] bg-[#ffffff] p-3">
                <div className="grid grid-cols-2 gap-1.5">
                  {navSections.map(item => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => jumpToSection(item.id)}
                      className="rounded-[4px] bg-[#f6f7fb] px-2.5 py-2 text-left text-[12.5px] font-medium text-[#282e3e] cursor-pointer"
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Desktop sticky navigation rail (NO internal scrollbar) */}
          <aside className="hidden lg:block lg:w-[230px] lg:shrink-0 lg:sticky lg:top-[76px]">
            <nav aria-label="Breakdown sections" className="card p-3.5 space-y-4">
              <div>
                <div className="mb-2 px-2 text-[11px] font-bold uppercase tracking-wider text-[#586380]">
                  Sections
                </div>
                <ul className="m-0 list-none space-y-0.5 p-0">
                  {navSections.map(item => (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => jumpToSection(item.id)}
                        className={`w-full rounded-[4px] px-2.5 py-1.5 text-left text-[13px] transition-colors cursor-pointer ${
                          activeNavId === item.id
                            ? 'bg-[#edefff] font-semibold text-[#4255ff]'
                            : 'text-[#282e3e] hover:bg-[#f6f7fb]'
                        }`}
                      >
                        {item.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>

              {breakdown.sections_index.length > 0 && (
                <div className="border-t border-[#d9dde8] pt-3">
                  <div className="mb-2 px-2 text-[11px] font-bold uppercase tracking-wider text-[#586380]">
                    Document Pages
                  </div>
                  <div className="space-y-1">
                    {breakdown.sections_index.map((sec, idx) => (
                      <button
                        key={`idx-${idx}`}
                        type="button"
                        onClick={() =>
                          setSelectedEvidence({
                            id: `sec-ref-${idx}`,
                            title: sec.section,
                            section: sec.section,
                            page: sec.page,
                            excerpt: sec.excerpt,
                            origin: sec.origin ?? 'author_claim',
                            nodeId: sec.node_id ?? null,
                          })
                        }
                        className="flex w-full items-center justify-between gap-2 rounded-[4px] px-2 py-1 text-left text-[12px] text-[#586380] hover:bg-[#f6f7fb] hover:text-[#282e3e] cursor-pointer"
                      >
                        <span className="truncate">{sec.section}</span>
                        <span className="shrink-0 font-semibold text-[#4255ff]">p.{sec.page}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </nav>
          </aside>

          {/* Main Readable Editorial Breakdown Column */}
          <div className="min-w-0 flex-1 space-y-6">
            {/* Section 1: Abstract */}
            <BreakdownSectionCard
              id="sec-abstract"
              title="Abstract & Overview"
              fields={[
                { id: 'abstract_summary', field: breakdown.abstract_summary },
                { id: 'what_this_paper_does', field: breakdown.what_this_paper_does },
              ]}
              selectedId={selectedEvidence?.id}
              onInspect={openFieldEvidence}
            />

            {/* Section 2: Problem, Objective & Background */}
            <BreakdownSectionCard
              id="sec-problem"
              title="Problem, Research Question & Prior Work"
              fields={[
                { id: 'problem_and_importance', field: breakdown.problem_and_importance },
                { id: 'research_objective', field: breakdown.research_objective },
                { id: 'background_prior_work', field: breakdown.background_prior_work },
              ]}
              selectedId={selectedEvidence?.id}
              onInspect={openFieldEvidence}
            />

            {/* Section 3: Proposed Method */}
            <BreakdownSectionCard
              id="sec-method"
              title="Proposed Method, System, or Approach"
              fields={[{ id: 'proposed_method', field: breakdown.proposed_method }]}
              selectedId={selectedEvidence?.id}
              onInspect={openFieldEvidence}
            />

            {/* Section 4: Step-by-Step Methodology */}
            <section id="sec-steps" className="card scroll-mt-[84px] p-5 sm:p-6">
              <h2 className="m-0 text-[17px] font-bold text-[#282e3e]">Step-by-Step Methodology</h2>
              {breakdown.step_by_step_methodology.length > 0 ? (
                <ol className="mt-4 m-0 list-none space-y-3 p-0">
                  {breakdown.step_by_step_methodology.map((step: MethodologyStep) => {
                    const stepId = `step-${step.node_id}-${step.step_number}`
                    const active = selectedEvidence?.id === stepId
                    return (
                      <li
                        key={stepId}
                        className={`rounded-[8px] border p-4 transition-colors ${
                          active ? 'border-[#4255ff] bg-[#edefff]/40' : 'border-[#d9dde8] bg-[#f6f7fb]'
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-[#4255ff] text-[12px] font-bold text-[#ffffff]">
                              {step.step_number}
                            </span>
                            <span className="text-[14.5px] font-bold text-[#282e3e]">{step.title}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedEvidence({
                                id: stepId,
                                title: `Step ${step.step_number}: ${step.title}`,
                                section: step.section,
                                page: step.page,
                                explanation: step.plain_language ?? null,
                                excerpt: step.excerpt,
                                origin: step.origin,
                                nodeId: step.node_id,
                              })
                            }
                            className="text-[12px] font-semibold text-[#4255ff] hover:underline cursor-pointer"
                          >
                            Evidence · p. {step.page} →
                          </button>
                        </div>

                        {step.plain_language && (
                          <div className="mt-2 rounded-[6px] bg-[#edefff] px-3 py-2 text-[13.5px] leading-5 text-[#282e3e]">
                            <span className="font-semibold text-[#4255ff]">Plain-language explanation: </span>
                            {step.plain_language}
                          </div>
                        )}
                        <p className="mt-2 m-0 text-[13.5px] leading-6 text-[#2e3856]">{step.summary}</p>
                      </li>
                    )
                  })}
                </ol>
              ) : (
                <p className="mt-3 m-0 text-[14px] italic text-[#586380]">
                  Not found in the paper as a distinct step sequence.
                </p>
              )}
            </section>

            {/* Section 5: Data, Experiments & Results */}
            <section id="sec-results" className="card scroll-mt-[84px] p-5 sm:p-6 space-y-5">
              <h2 className="m-0 text-[17px] font-bold text-[#282e3e]">
                Datasets, Experiments & Main Results
              </h2>

              <FieldBlock
                id="data_setup_metrics"
                field={breakdown.data_setup_metrics}
                active={selectedEvidence?.id === 'data_setup_metrics'}
                onInspect={() => openFieldEvidence('data_setup_metrics', breakdown.data_setup_metrics)}
              />

              <FieldBlock
                id="main_results"
                field={breakdown.main_results}
                active={selectedEvidence?.id === 'main_results'}
                onInspect={() => openFieldEvidence('main_results', breakdown.main_results)}
              />

              {breakdown.quantitative_results.length > 0 ? (
                <div className="space-y-3 border-t border-[#d9dde8] pt-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[13px] font-bold text-[#282e3e]">
                      Extracted Comparative Benchmarks
                    </span>
                    {breakdown.results_chart_provenance && (
                      <ProvenanceTag provenance={breakdown.results_chart_provenance} />
                    )}
                  </div>
                  {breakdown.quantitative_results.map((res, idx) => (
                    <ResultComparisonCard
                      key={`bd-quant-${idx}`}
                      res={res}
                      maxVal={maxQuantitativeVal}
                      active={selectedEvidence?.id === `quant-${idx}`}
                      onInspect={() =>
                        setSelectedEvidence({
                          id: `quant-${idx}`,
                          title: `${res.metric_label}: ${res.value_display}`,
                          section: res.section,
                          page: res.page,
                          explanation: res.comparison_context ?? res.baseline_or_context,
                          excerpt: res.excerpt,
                          origin: 'author_claim',
                        })
                      }
                    />
                  ))}
                </div>
              ) : (
                breakdown.results_summary_note && (
                  <p className="m-0 rounded-[6px] border border-[#d9dde8] bg-[#f6f7fb] p-3 text-[13px] leading-5 text-[#586380]">
                    {breakdown.results_summary_note}
                  </p>
                )
              )}
            </section>

            {/* Section 6: Contributions, Limitations & Future Directions */}
            <BreakdownSectionCard
              id="sec-discussion"
              title="Contributions, Limitations & Future Directions"
              fields={[
                { id: 'contributions_novelty', field: breakdown.contributions_novelty },
                { id: 'limitations_assumptions', field: breakdown.limitations_assumptions },
                { id: 'implications_future_work', field: breakdown.implications_future_work },
              ]}
              selectedId={selectedEvidence?.id}
              onInspect={openFieldEvidence}
            />

            {/* Section 7: Technical Glossary */}
            <section id="sec-glossary" className="card scroll-mt-[84px] p-5 sm:p-6">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h2 className="m-0 text-[17px] font-bold text-[#282e3e]">Glossary of Important Terms</h2>
                <span className="text-[12px] text-[#586380]">Click a term to read its paper passage</span>
              </div>

              {breakdown.glossary.length > 0 ? (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {breakdown.glossary.map((g: GlossaryItem, idx: number) => {
                    const gid = `glossary-${idx}`
                    const active = selectedEvidence?.id === gid
                    return (
                      <button
                        key={gid}
                        type="button"
                        onClick={() =>
                          setSelectedEvidence({
                            id: gid,
                            title: g.term,
                            section: 'Technical Glossary Context',
                            page: g.page,
                            explanation: g.definition,
                            excerpt: g.excerpt,
                            origin: g.origin,
                          })
                        }
                        className={`rounded-[8px] border p-3.5 text-left transition-colors cursor-pointer ${
                          active
                            ? 'border-[#4255ff] bg-[#edefff]/50'
                            : 'border-[#d9dde8] bg-[#f6f7fb] hover:border-[#939bb4]'
                        }`}
                      >
                        <div className="mb-1 flex items-center justify-between gap-2">
                          <span className="text-[13.5px] font-bold text-[#4255ff]">{g.term}</span>
                          <span className="text-[11px] font-semibold text-[#586380]">p. {g.page}</span>
                        </div>
                        <p className="m-0 text-[13px] leading-5 text-[#2e3856]">{g.definition}</p>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <p className="m-0 text-[14px] italic text-[#586380]">
                  No explicit term definitions were extracted from this paper.
                </p>
              )}
            </section>
          </div>
        </div>
      )}

      {/* =====================================================================
          COMPACT DISMISSIBLE EVIDENCE DRAWER (Zero space taken when closed)
         ===================================================================== */}
      {selectedEvidence && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-[#282e3e]/25"
          role="dialog"
          aria-modal="true"
          aria-label="Source evidence inspector"
          onClick={() => setSelectedEvidence(null)}
        >
          <div
            className="flex h-full w-[420px] max-w-[92vw] flex-col border-l border-[#d9dde8] bg-[#ffffff] shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#d9dde8] px-5 py-4">
              <div className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-[#4255ff]" />
                <span className="text-[13px] font-bold uppercase tracking-wide text-[#4255ff]">
                  Source Evidence
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedEvidence(null)}
                aria-label="Close evidence panel"
                className="rounded-[4px] p-1 text-[#586380] hover:bg-[#f6f7fb] hover:text-[#282e3e] cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-5">
              <div>
                <h3 className="m-0 text-[16px] font-bold leading-snug text-[#282e3e]">
                  {selectedEvidence.title}
                </h3>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px] text-[#586380]">
                  <span className="rounded-[4px] bg-[#edefff] px-2 py-0.5 font-bold text-[#4255ff]">
                    Page {selectedEvidence.page ?? 1}
                  </span>
                  <span>{selectedEvidence.section}</span>
                  <span>·</span>
                  <span>{originText(selectedEvidence.origin)}</span>
                </div>
              </div>

              {selectedEvidence.explanation && (
                <div className="rounded-[8px] bg-[#edefff] p-3.5 text-[13.5px] leading-6 text-[#282e3e]">
                  <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-[#4255ff]">
                    Plain-Language Explanation
                  </div>
                  {selectedEvidence.explanation}
                </div>
              )}

              <div>
                <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-[#586380]">
                  Verbatim Passage from Paper (p. {selectedEvidence.page ?? 1})
                </div>
                <blockquote className="m-0 rounded-[8px] border border-[#d9dde8] border-l-4 border-l-[#4255ff] bg-[#f6f7fb] p-4 text-[13.5px] leading-6 text-[#2e3856] whitespace-pre-wrap">
                  “{selectedEvidence.excerpt}”
                </blockquote>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function BreakdownSectionCard({
  id,
  title,
  fields,
  selectedId,
  onInspect,
}: {
  id: string
  title: string
  fields: { id: string; field: BreakdownField }[]
  selectedId?: string | null
  onInspect: (id: string, field: BreakdownField) => void
}) {
  return (
    <section id={id} className="card scroll-mt-[84px] p-5 sm:p-6 space-y-5">
      <h2 className="m-0 text-[17px] font-bold text-[#282e3e]">{title}</h2>
      <div className="space-y-4">
        {fields.map(({ id: fid, field }) => (
          <FieldBlock
            key={fid}
            id={fid}
            field={field}
            active={selectedId === fid}
            onInspect={() => onInspect(fid, field)}
          />
        ))}
      </div>
    </section>
  )
}

function FieldBlock({
  id,
  field,
  active,
  onInspect,
}: {
  id: string
  field: BreakdownField
  active: boolean
  onInspect: () => void
}) {
  return (
    <div
      id={id}
      className={`rounded-[8px] border p-4 transition-colors ${
        active ? 'border-[#4255ff] bg-[#edefff]/35' : 'border-[#d9dde8] bg-[#f6f7fb]'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="m-0 text-[14.5px] font-bold text-[#282e3e]">{field.label}</h3>
          <span className="text-[11.5px] font-medium text-[#586380]">
            · {originText(field.origin, field.found)}
          </span>
        </div>
        {field.found && (
          <button
            type="button"
            onClick={onInspect}
            className="inline-flex items-center gap-0.5 text-[12px] font-semibold text-[#4255ff] hover:underline cursor-pointer"
          >
            {field.section ? `${field.section} · ` : ''}p. {field.page ?? 1}
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {field.found ? (
        <div className="mt-2.5 space-y-2.5">
          {field.plain_language && (
            <div className="rounded-[6px] bg-[#edefff] px-3.5 py-2.5 text-[13.5px] leading-6 text-[#282e3e]">
              <span className="font-semibold text-[#4255ff]">Plain-language explanation: </span>
              {field.plain_language}
            </div>
          )}
          <p className="m-0 text-[14px] leading-6 text-[#2e3856]">{field.value}</p>
        </div>
      ) : (
        <p className="mt-2 m-0 text-[13.5px] italic text-[#586380]">{field.value}</p>
      )}
    </div>
  )
}

function ResultComparisonCard({
  res,
  maxVal,
  active,
  onInspect,
}: {
  res: ResultDataPoint
  maxVal: number
  active: boolean
  onInspect: () => void
}) {
  const propNum = typeof res.proposed_value === 'number' ? res.proposed_value : res.numeric_value ?? 0
  const baseNum = typeof res.baseline_value === 'number' ? res.baseline_value : null
  const scaleMax = res.unit === '%' ? 100 : maxVal

  const widthFor = (v: number) => `${Math.min(100, Math.max(8, (Math.abs(v) / scaleMax) * 100))}%`

  return (
    <button
      type="button"
      onClick={onInspect}
      className={`w-full rounded-[8px] border p-3.5 text-left transition-colors cursor-pointer ${
        active ? 'border-[#4255ff] bg-[#edefff]/50' : 'border-[#d9dde8] bg-[#f6f7fb] hover:border-[#939bb4]'
      }`}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[13px] font-bold text-[#282e3e]">{res.metric_label}</span>
        <span className="text-[11.5px] font-semibold text-[#4255ff]">p. {res.page} · View source</span>
      </div>

      <div className="space-y-1.5">
        <div>
          <div className="mb-0.5 flex justify-between text-[12px]">
            <span className="font-medium text-[#282e3e]">{res.proposed_label ?? 'Reported'}</span>
            <span className="font-bold text-[#4255ff]">
              {propNum}
              {res.unit}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-[#e2e8f0]">
            <div className="h-full rounded-full bg-[#4255ff]" style={{ width: widthFor(propNum) }} />
          </div>
        </div>

        {baseNum !== null && (
          <div>
            <div className="mb-0.5 flex justify-between text-[12px] text-[#586380]">
              <span>{res.baseline_label ?? 'Baseline'}</span>
              <span className="font-semibold">
                {baseNum}
                {res.unit}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-[#e2e8f0]">
              <div className="h-full rounded-full bg-[#939bb4]" style={{ width: widthFor(baseNum) }} />
            </div>
          </div>
        )}
      </div>
    </button>
  )
}

function ProvenanceTag({ provenance }: { provenance: DiagramProvenance }) {
  const isReconstructed = provenance === 'reconstructed_from_paper'
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-[200px] border px-2.5 py-0.5 text-[11px] font-semibold ${
        isReconstructed
          ? 'border-[#bbf7d0] bg-[#f0fdf4] text-[#15803d]'
          : 'border-[#c7d2fe] bg-[#edefff] text-[#4255ff]'
      }`}
    >
      <Info className="h-3 w-3" />
      {provenanceLabel(provenance)}
    </span>
  )
}
