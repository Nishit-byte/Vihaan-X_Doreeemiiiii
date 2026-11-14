import type {
  BreakdownField, ClaimOrigin, DiagramProvenance,
  IngestLeetCodeRequest, IngestLeetCodeResponse,
  IngestRepoRequest, IngestResponse,
  PaperBreakdown, PaperNodeMeta,
  RunCodeRequest, RunCodeResponse,
  TurnRequest, TurnResponse, VivaReport,
} from '../types/api'
import { mockIngestPdf, mockIngestRepo, mockReport, mockRun, mockTurn } from './demoData'

const BASE: string = import.meta.env.VITE_API_BASE ?? '/api'
const ALLOW_DEMO: boolean = import.meta.env.VITE_DEMO_FALLBACK !== 'false'

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

// Once the backend fails, stay on demo data until reload so session ids stay consistent.
let demo = false
const listeners = new Set<(v: boolean) => void>()
export function subscribeDemoMode(cb: (v: boolean) => void) {
  listeners.add(cb); cb(demo)
  return () => { listeners.delete(cb) }
}
function setDemo(v: boolean) { demo = v; listeners.forEach(l => l(v)) }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init)
  if (!res.ok) {
    let detail = res.statusText
    try { const j = await res.json(); detail = j.detail ?? detail } catch { /* ignore */ }
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json() as Promise<T>
}

async function withFallback<T>(real: () => Promise<T>, fake: () => T | Promise<T>): Promise<T> {
  if (demo) return fake()
  try {
    return await real()
  } catch (e) {
    const unreachable = e instanceof TypeError || (e instanceof ApiError && e.status >= 500)
    if (ALLOW_DEMO && unreachable) { setDemo(true); return fake() }
    throw e
  }
}

const json = (body: unknown): RequestInit => ({
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
})

interface BackendPaperNode {
  node_id: string
  label: string
  summary?: string | null
  section?: string | null
  page?: number
  excerpt: string
}

interface BackendIngestResponse {
  session_id: string
  mode: 'repo' | 'paper'
  title?: string
  authors?: string[]
  files?: IngestResponse['files']
  mermaid_graph?: string | null
  paper_nodes?: BackendPaperNode[]
  paper_breakdown?: Record<string, unknown> | null
  initial_turn?: TurnResponse
  first_turn?: TurnResponse
  paper?: IngestResponse['paper']
}

function toBreakdownField(
  label: string,
  rawField: unknown,
  defaultOrigin: ClaimOrigin = 'author_claim'
): BreakdownField {
  if (!rawField) {
    return {
      label,
      value: 'Not found in the paper',
      found: false,
      origin: defaultOrigin,
      page: null,
      section: null,
      supporting_excerpt: null,
      plain_language: null,
    }
  }
  if (typeof rawField === 'string') {
    const found = rawField.trim() !== '' && rawField.trim().toLowerCase() !== 'not found in the paper'
    return {
      label,
      value: found ? rawField : 'Not found in the paper',
      found,
      origin: defaultOrigin,
      page: 1,
      section: 'Title & Overview',
      supporting_excerpt: found ? rawField : null,
      plain_language: null,
    }
  }
  const f = rawField as Record<string, unknown>
  const val = String(f.value ?? f.content ?? f.claim_or_insight ?? 'Not found in the paper')
  const found =
    typeof f.found === 'boolean'
      ? f.found
      : val.trim() !== '' && val.trim().toLowerCase() !== 'not found in the paper'
  const rawOrigin = String(f.origin ?? f.source_type ?? defaultOrigin)
  const origin: ClaimOrigin =
    rawOrigin === 'app_interpretation' ? 'app_interpretation' : 'author_claim'
  return {
    label: String(f.label ?? label),
    value: val,
    found,
    origin,
    page: typeof f.page === 'number' ? f.page : null,
    section: f.section ? String(f.section) : null,
    supporting_excerpt: f.supporting_excerpt
      ? String(f.supporting_excerpt)
      : f.excerpt
      ? String(f.excerpt)
      : found
      ? val
      : null,
    plain_language: f.plain_language
      ? String(f.plain_language)
      : f.interpretation
      ? String(f.interpretation)
      : null,
  }
}

function toProvenance(raw: unknown, fallback: DiagramProvenance): DiagramProvenance {
  const s = String(raw ?? '').toLowerCase()
  if (s.includes('reconstructed')) return 'reconstructed_from_paper'
  if (s.includes('conceptual')) return 'conceptual_explanation'
  return fallback
}

function normalizePaperBreakdown(raw: Record<string, unknown> | null | undefined): PaperBreakdown | null {
  if (!raw) return null
  // If already in frontend shape (e.g. demoData), return as-is
  if (
    typeof raw.authors_and_affiliations === 'object' &&
    raw.authors_and_affiliations !== null &&
    'value' in (raw.authors_and_affiliations as Record<string, unknown>)
  ) {
    return raw as unknown as PaperBreakdown
  }

  const rawSteps = Array.isArray(raw.step_by_step_methodology) ? raw.step_by_step_methodology : []
  const rawTakeaways = Array.isArray(raw.key_takeaways) ? raw.key_takeaways : []
  const rawStory = Array.isArray(raw.story_map) ? raw.story_map : []
  const rawQuant = Array.isArray(raw.quantitative_results) ? raw.quantitative_results : []
  const rawGlossary = Array.isArray(raw.glossary) ? raw.glossary : []
  const rawSections = Array.isArray(raw.sections_index) ? raw.sections_index : []

  const rawAuthorsStr = String(raw.authors_and_affiliations ?? 'Not found in the paper')
  const authStatus = (raw.authors_status as PaperBreakdown['authors_status']) ??
    (rawAuthorsStr.toLowerCase().includes('could not') ? 'uncertain' : rawAuthorsStr.toLowerCase().includes('not found') ? 'not_found' : 'identified')

  const authorsField = toBreakdownField('Authors & Affiliations', raw.authors_and_affiliations, 'author_claim')
  if (authStatus !== 'identified') {
    authorsField.found = false
    if (raw.title_block_excerpt) {
      authorsField.supporting_excerpt = String(raw.title_block_excerpt)
    }
  }

  const whatField = toBreakdownField('What This Paper Does', raw.what_this_paper_does, 'author_claim')
  if (raw.what_this_paper_does_plain) {
    whatField.plain_language = String(raw.what_this_paper_does_plain)
    whatField.origin = 'app_interpretation'
  }

  return {
    extraction_status: (raw.extraction_status as PaperBreakdown['extraction_status']) ?? 'ok',
    extraction_notice: (raw.extraction_notice ?? raw.extraction_warning ?? null) as string | null,
    page_count: typeof raw.page_count === 'number' ? raw.page_count : 1,
    title: String(raw.title ?? 'Uploaded Research Paper'),
    title_status: (raw.title_status as PaperBreakdown['title_status']) ?? 'verified',
    authors_and_affiliations: authorsField,
    authors_status: authStatus,
    venue_and_year: toBreakdownField('Publication Venue & Year', raw.venue_and_year, 'author_claim'),
    title_block_excerpt: raw.title_block_excerpt ? String(raw.title_block_excerpt) : null,
    what_this_paper_does: whatField,
    abstract_summary: toBreakdownField('Abstract', raw.abstract_summary, 'author_claim'),
    problem_and_importance: toBreakdownField(
      'Problem Addressed & Why It Matters',
      raw.problem_and_importance ?? raw.problem_and_significance,
      'author_claim'
    ),
    research_objective: toBreakdownField('Research Objective / Question', raw.research_objective, 'author_claim'),
    background_prior_work: toBreakdownField(
      'Background & Prior Work',
      raw.background_prior_work ?? raw.background_and_prior_work,
      'author_claim'
    ),
    proposed_method: toBreakdownField('Proposed Method / Approach', raw.proposed_method, 'author_claim'),
    step_by_step_methodology: rawSteps.map((s: Record<string, unknown>, idx: number) => ({
      step_number: typeof s.step_number === 'number' ? s.step_number : idx + 1,
      node_id: String(s.node_id ?? `N${idx + 1}`),
      title: String(s.title ?? `Stage ${idx + 1}`),
      summary: String(s.summary ?? s.description ?? ''),
      plain_language: s.plain_language ? String(s.plain_language) : null,
      origin: s.origin === 'app_interpretation' || s.source_type === 'app_interpretation' ? 'app_interpretation' : 'author_claim',
      page: typeof s.page === 'number' ? s.page : 1,
      section: String(s.section ?? 'Methodology'),
      excerpt: String(s.excerpt ?? s.description ?? ''),
    })),
    data_setup_metrics: toBreakdownField(
      'Datasets, Experimental Setup & Evaluation Metrics',
      raw.data_setup_metrics ?? raw.data_setup_and_metrics,
      'author_claim'
    ),
    main_results: toBreakdownField('Main Results & What They Mean', raw.main_results, 'author_claim'),
    results_summary_note: raw.results_summary_note ? String(raw.results_summary_note) : null,
    contributions_novelty: toBreakdownField(
      'Contributions & What Is New',
      raw.contributions_novelty ?? raw.contributions,
      'author_claim'
    ),
    limitations_assumptions: toBreakdownField(
      'Limitations & Assumptions Stated by Authors',
      raw.limitations_assumptions ?? raw.limitations_and_assumptions,
      'author_claim'
    ),
    implications_future_work: toBreakdownField(
      'Practical Implications & Future Directions',
      raw.implications_future_work ?? raw.implications_and_future_work,
      'author_claim'
    ),
    key_takeaways: rawTakeaways.map((t: Record<string, unknown>, idx: number) =>
      toBreakdownField(String(t.label ?? `Takeaway ${idx + 1}`), t, 'author_claim')
    ),
    story_map: rawStory.map((st: Record<string, unknown>, idx: number) =>
      toBreakdownField(String(st.label ?? `Stage ${idx + 1}`), st, 'author_claim')
    ),
    story_map_provenance: toProvenance(raw.story_map_provenance, 'conceptual_explanation'),
    methodology_diagram_status: raw.methodology_diagram_status === 'fallback' ? 'fallback' : 'ok',
    methodology_diagram_note: raw.methodology_diagram_note ? String(raw.methodology_diagram_note) : null,
    methodology_diagram_provenance: toProvenance(
      raw.methodology_diagram_provenance ?? raw.diagram_provenance,
      'reconstructed_from_paper'
    ),
    quantitative_results: rawQuant.map((q: Record<string, unknown>) => {
      const propVal = typeof q.numeric_value === 'number'
        ? q.numeric_value
        : typeof q.proposed_value === 'number'
        ? q.proposed_value
        : null
      const baseVal = typeof q.baseline_value === 'number' ? q.baseline_value : null
      const unit = String(q.unit ?? '')
      const valDisplay = q.value_display
        ? String(q.value_display)
        : propVal !== null
        ? `${propVal}${unit}`
        : ''
      const baseCtx = q.baseline_or_context
        ? String(q.baseline_or_context)
        : baseVal !== null
        ? `vs. ${q.baseline_label ?? 'Baseline'}: ${baseVal}${unit}`
        : String(q.comparison_context ?? q.proposed_label ?? 'Reported metric')
      return {
        metric_label: String(q.metric_label ?? q.metric ?? 'Metric'),
        comparison_context: q.comparison_context ? String(q.comparison_context) : null,
        baseline_label: q.baseline_label ? String(q.baseline_label) : 'Baseline',
        baseline_value: baseVal,
        proposed_label: q.proposed_label ? String(q.proposed_label) : 'Proposed',
        proposed_value: propVal,
        value_display: valDisplay,
        numeric_value: propVal,
        unit,
        baseline_or_context: baseCtx,
        page: typeof q.page === 'number' ? q.page : 1,
        section: String(q.section ?? 'Results'),
        excerpt: String(q.excerpt ?? ''),
      }
    }),
    results_chart_provenance: 'reconstructed_from_paper',
    glossary: rawGlossary.map((g: Record<string, unknown>) => ({
      term: String(g.term ?? ''),
      definition: String(g.definition ?? ''),
      origin:
        g.origin === 'author_claim' || g.source_type === 'author_defined'
          ? 'author_claim'
          : 'app_interpretation',
      page: typeof g.page === 'number' ? g.page : 1,
      excerpt: String(g.excerpt ?? g.definition ?? ''),
    })),
    sections_index: rawSections.map((sec: Record<string, unknown>, idx: number) => ({
      section: String(sec.label ?? sec.section ?? `Section ${idx + 1}`),
      page: typeof sec.page === 'number' ? sec.page : 1,
      excerpt: String(sec.excerpt ?? sec.claim_or_insight ?? ''),
      node_id: sec.node_id ? String(sec.node_id) : `N${idx + 1}`,
      origin: sec.source_type === 'app_interpretation' ? 'app_interpretation' : 'author_claim',
    })),
  }
}

interface BackendVivaReport {
  session_id: string
  overall_score: number
  rubric_scores?: {
    clarity: number
    trade_offs: number
    edge_cases: number
    code_execution: number
    depth: number
  }
  rubric?: VivaReport['rubric']
  topic_depths?: { topic: string; max_depth_reached: number }[]
  topic_depth?: VivaReport['topic_depth']
  code_challenges?: { challenge_description: string; passed: boolean }[]
  challenges?: VivaReport['challenges']
  study_plan?: string[]
  fluency_weight?: number
}

function normalizeIngest(raw: BackendIngestResponse): IngestResponse {
  const nodeEntries = raw.paper_nodes ?? []
  const nodeMeta: Record<string, PaperNodeMeta> = Object.fromEntries(
    nodeEntries.map(n => [
      n.node_id,
      {
        node_id: n.node_id,
        label: n.label,
        summary: n.summary ?? null,
        section: n.section ?? null,
        page: n.page ?? 1,
        excerpt: n.excerpt,
      },
    ])
  )

  const breakdown = normalizePaperBreakdown(raw.paper_breakdown)
  const paper =
    raw.paper ??
    (raw.mermaid_graph !== undefined || breakdown
      ? {
          mermaid: raw.mermaid_graph ?? '',
          nodes: Object.fromEntries(nodeEntries.map(n => [n.node_id, n.excerpt])),
          node_meta: nodeMeta,
          breakdown,
        }
      : null)

  return {
    session_id: raw.session_id,
    mode: raw.mode,
    files: raw.files ?? [],
    authors: raw.authors ?? [],
    paper,
    first_turn: (raw.first_turn ?? raw.initial_turn) as TurnResponse,
  }
}

function normalizeReport(raw: BackendVivaReport): VivaReport {
  const rs = raw.rubric_scores
  const rubric = raw.rubric ?? {
    clarity: rs?.clarity ?? 0,
    tradeoffs: rs?.trade_offs ?? 0,
    edge_cases: rs?.edge_cases ?? 0,
    code_execution: rs?.code_execution ?? 0,
    depth: rs?.depth ?? 0,
  }
  const topic_depth =
    raw.topic_depth ??
    (raw.topic_depths ?? []).map(t => ({ topic: t.topic, level: t.max_depth_reached }))
  const challenges =
    raw.challenges ??
    (raw.code_challenges ?? []).map(c => ({
      description: c.challenge_description,
      passed: c.passed,
    }))

  return {
    session_id: raw.session_id,
    overall_score: raw.overall_score,
    rubric,
    topic_depth,
    challenges,
    study_plan: raw.study_plan ?? [],
    fluency_weight: raw.fluency_weight ?? 0,
  }
}

export function ingestRepo(github_url: string, author: string | null = null) {
  const body = { github_url, selected_author: null }
  return withFallback(
    async () => normalizeIngest(await request<BackendIngestResponse>('/ingest-repo', json(body))),
    () => mockIngestRepo(null),
  )
}

/** Pass null to load the pre-cached demo paper (backend/demo_cache/sample_paper.pdf). */
export function ingestPdf(file: File | null) {
  return withFallback(async () => {
    const fd = new FormData()
    if (file) fd.append('file', file); else fd.append('use_demo', 'true')
    return normalizeIngest(await request<BackendIngestResponse>('/ingest-pdf', { method: 'POST', body: fd }))
  }, () => mockIngestPdf())
}

export function submitTurn(req: TurnRequest) {
  return withFallback(() => request<TurnResponse>('/viva/turn', json(req)), () => mockTurn(req))
}

export function runCode(req: RunCodeRequest): Promise<RunCodeResponse> {
  // Always invoke live FastAPI sandbox verification endpoint
  return request<RunCodeResponse>('/run-code', json(req))
}

export function fetchReport(sessionId: string) {
  return withFallback(
    async () => normalizeReport(await request<BackendVivaReport>(`/report/${sessionId}`)),
    () => mockReport(sessionId),
  )
}

export function ingestLeetCode(
  username_or_url: string,
  num_easy = 1,
  num_medium = 2,
  num_hard = 2,
): Promise<IngestLeetCodeResponse> {
  const body: IngestLeetCodeRequest = {
    username_or_url,
    num_easy,
    num_medium,
    num_hard,
  }
  // Always invoke live FastAPI endpoint for dynamic Gemini question generation per LeetCode ID
  return request<IngestLeetCodeResponse>('/ingest-leetcode', json(body))
}

export async function terminateSession(
  session_id: string,
  reason = 'anti_plagiarism_fullscreen_exit',
): Promise<{ status: string; session_id: string }> {
  try {
    return await request<{ status: string; session_id: string }>(
      '/viva/terminate',
      json({ session_id, reason }),
    )
  } catch {
    return { status: 'terminated', session_id }
  }
}
