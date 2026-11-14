// Mirrors backend/models/schemas.py (M1). TurnResponse is from the spec;
// the other shapes are proposed and must be confirmed against schemas.py.

export type Verdict = 'start' | 'strong' | 'partial' | 'weak' | 'no_answer'
export type VivaMode = 'repo' | 'paper'

export interface CodeHighlight {
  file_path: string
  line_start: number
  line_end: number
}

export interface CodingChallenge {
  description: string
  target_file: string
  starter_code: string
  test_code: string
}

export interface TurnResponse {
  session_id: string
  student_transcript: string
  verdict: Verdict
  ack_text: string
  question_text: string
  audio_base64: string
  topic: string
  depth_level: number // 1..4
  highlight?: CodeHighlight | null
  diagram_node_id?: string | null
  paper_excerpt?: string | null
  coding_challenge?: CodingChallenge | null
  done: boolean
}

export interface RepoFile {
  path: string
  content: string
  language: string
}

export type ClaimOrigin = 'author_claim' | 'app_interpretation'
export type DiagramProvenance = 'reconstructed_from_paper' | 'conceptual_explanation'

export interface EvidenceRef {
  section: string
  page: number
  excerpt: string
  node_id?: string | null
  origin?: ClaimOrigin
}

export interface BreakdownField {
  label: string
  value: string
  found: boolean
  origin: ClaimOrigin
  page?: number | null
  section?: string | null
  supporting_excerpt?: string | null
  plain_language?: string | null
}

export interface MethodologyStep {
  step_number: number
  node_id: string
  title: string
  summary: string
  plain_language?: string | null
  origin: ClaimOrigin
  page: number
  section: string
  excerpt: string
}

export interface ResultDataPoint {
  metric_label: string
  comparison_context?: string | null
  baseline_label?: string | null
  baseline_value?: number | null
  proposed_label?: string | null
  proposed_value?: number | null
  value_display: string
  numeric_value?: number | null
  unit: string
  baseline_or_context: string
  page: number
  section: string
  excerpt: string
}

export interface GlossaryItem {
  term: string
  definition: string
  origin: ClaimOrigin
  page: number
  excerpt: string
}

export interface PaperVivaQuestion {
  id: string
  category:
    | 'basic_understanding'
    | 'methodology_design'
    | 'results_evidence'
    | 'limitations_tradeoffs'
    | 'what_if'
  category_label: string
  depth_level: number
  question: string
  why_asked: string
  page: number
  section: string
  supporting_excerpt: string
  diagram_node_id?: string | null
}

export interface PaperNodeMeta {
  node_id: string
  label: string
  summary?: string | null
  section?: string | null
  page: number
  excerpt: string
}

export interface PaperBreakdown {
  extraction_status: 'ok' | 'scanned_or_empty' | 'partial'
  extraction_notice?: string | null
  page_count: number
  title: string
  title_status: 'verified' | 'uncertain'
  authors_and_affiliations: BreakdownField
  authors_status: 'identified' | 'uncertain' | 'not_found'
  venue_and_year: BreakdownField
  title_block_excerpt?: string | null
  what_this_paper_does: BreakdownField
  abstract_summary: BreakdownField
  problem_and_importance: BreakdownField
  research_objective: BreakdownField
  background_prior_work: BreakdownField
  proposed_method: BreakdownField
  step_by_step_methodology: MethodologyStep[]
  data_setup_metrics: BreakdownField
  main_results: BreakdownField
  results_summary_note?: string | null
  contributions_novelty: BreakdownField
  limitations_assumptions: BreakdownField
  implications_future_work: BreakdownField
  key_takeaways: BreakdownField[]
  story_map: BreakdownField[]
  story_map_provenance: DiagramProvenance
  methodology_diagram_status: 'ok' | 'fallback'
  methodology_diagram_note?: string | null
  methodology_diagram_provenance: DiagramProvenance
  quantitative_results: ResultDataPoint[]
  results_chart_provenance?: DiagramProvenance | null
  glossary: GlossaryItem[]
  sections_index: EvidenceRef[]
  viva_questions?: PaperVivaQuestion[]
}

export interface PaperIndex {
  mermaid: string // flowchart TD with node ids N1..N8
  nodes: Record<string, string> // node id -> excerpt
  node_meta?: Record<string, PaperNodeMeta>
  breakdown?: PaperBreakdown | null
}

export interface IngestRepoRequest {
  github_url: string
  author?: string | null
}

export interface IngestResponse {
  session_id: string
  mode: VivaMode
  files: RepoFile[]
  authors: string[]
  paper: PaperIndex | null
  first_turn: TurnResponse
}

export interface TurnRequest {
  session_id: string
  student_text?: string
  audio_base64?: string
  code_result?: RunCodeResponse
}

export interface RunCodeRequest {
  session_id: string
  file_path: string
  student_code: string
  test_code: string
}

export interface RunCodeResponse {
  passed: boolean
  stdout: string
  stderr: string
  runtime_ms: number
}

export interface VivaReport {
  session_id: string
  overall_score: number // 0..100
  rubric: {
    clarity: number // each 0..100
    tradeoffs: number
    edge_cases: number
    code_execution: number
    depth: number
  }
  topic_depth: { topic: string; level: number }[] // level 1..4
  challenges: { description: string; passed: boolean }[]
  study_plan: string[]
  fluency_weight: number // always 0
}

// Contract M3 implements in components/ExaminerPanel.tsx
export interface ExaminerPanelProps {
  sessionId: string | null
  mode: VivaMode | null
  turn: TurnResponse | null
  history: TurnResponse[]
  busy: boolean
  /** Call after every successful submitTurn() so the workspaces update. */
  onTurn: (turn: TurnResponse) => void
  /** Call when user clicks Start Viva to reveal Question 1. */
  onStartViva?: () => void
}
