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

export function ingestRepo(github_url: string, author: string | null = null) {
  const body: IngestRepoRequest = { github_url, author }
  return withFallback(() => request<IngestResponse>('/ingest-repo', json(body)), () => mockIngestRepo(author))
}

/** Pass null to load the pre-cached demo paper (backend/demo_cache/sample_paper.pdf). */
export function ingestPdf(file: File | null) {
  return withFallback(() => {
    const fd = new FormData()
    if (file) fd.append('file', file); else fd.append('use_demo', 'true')
    return request<IngestResponse>('/ingest-pdf', { method: 'POST', body: fd })
  }, () => mockIngestPdf())
}

export function submitTurn(req: TurnRequest) {
  return withFallback(() => request<TurnResponse>('/viva/turn', json(req)), () => mockTurn(req))
}

export function runCode(req: RunCodeRequest) {
  return withFallback(() => request<RunCodeResponse>('/run-code', json(req)), () => mockRun(req))
}

export function fetchReport(sessionId: string) {
  return withFallback(() => request<VivaReport>(`/report/${sessionId}`), () => mockReport(sessionId))
}
