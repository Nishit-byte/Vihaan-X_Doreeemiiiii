import type {
  IngestRepoRequest, IngestResponse, RunCodeRequest, RunCodeResponse,
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
  section?: string | null
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
  initial_turn?: TurnResponse
  first_turn?: TurnResponse
  paper?: IngestResponse['paper']
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
  const paper =
    raw.paper ??
    (raw.mermaid_graph
      ? {
          mermaid: raw.mermaid_graph,
          nodes: Object.fromEntries((raw.paper_nodes ?? []).map(n => [n.node_id, n.excerpt])),
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
  const body = { github_url, selected_author: author }
  return withFallback(
    async () => normalizeIngest(await request<BackendIngestResponse>('/ingest-repo', json(body))),
    () => mockIngestRepo(author),
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

export function runCode(req: RunCodeRequest) {
  return withFallback(() => request<RunCodeResponse>('/run-code', json(req)), () => mockRun(req))
}

export function fetchReport(sessionId: string) {
  return withFallback(
    async () => normalizeReport(await request<BackendVivaReport>(`/report/${sessionId}`)),
    () => mockReport(sessionId),
  )
}
