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

export interface PaperIndex {
  mermaid: string // flowchart TD with node ids N1..N8
  nodes: Record<string, string> // node id -> excerpt
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
