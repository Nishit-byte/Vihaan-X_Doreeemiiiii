import { useEffect, useMemo, useRef, useState } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import '../monacoSetup'
import { Check, ChevronDown, ChevronRight, FileCode2, Loader2, Play, X } from 'lucide-react'
import { runCode } from '../services/apiClient'
import type { CodeHighlight, CodingChallenge, RepoFile, RunCodeResponse } from '../types/api'

interface Props {
  sessionId: string
  files: RepoFile[]
  highlight: CodeHighlight | null | undefined
  /** Latest challenge from TurnResponse.coding_challenge (repo L4 or DSA question) */
  incomingChallenge: CodingChallenge | null | undefined
  onRunResult: (res: RunCodeResponse) => void
  emptyHint?: string
}

interface TreeNode {
  name: string
  path: string
  children: Map<string, TreeNode>
  isFile: boolean
}

function buildTree(paths: string[]): TreeNode {
  const root: TreeNode = { name: '', path: '', children: new Map(), isFile: false }
  for (const p of paths) {
    let node = root
    p.split('/').forEach((part, i, arr) => {
      const path = arr.slice(0, i + 1).join('/')
      if (!node.children.has(part))
        node.children.set(part, { name: part, path, children: new Map(), isFile: i === arr.length - 1 })
      node = node.children.get(part)!
    })
  }
  return root
}

const LANG: Record<string, string> = {
  py: 'python',
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  md: 'markdown',
  json: 'json',
}
const langOf = (f: RepoFile) => f.language || LANG[f.path.split('.').pop() ?? ''] || 'plaintext'

function Tree({
  node,
  depth,
  active,
  open,
  toggle,
  select,
}: {
  node: TreeNode
  depth: number
  active: string
  open: Set<string>
  toggle: (p: string) => void
  select: (p: string) => void
}) {
  const items = [...node.children.values()].sort(
    (a, b) => Number(a.isFile) - Number(b.isFile) || a.name.localeCompare(b.name)
  )
  return (
    <ul>
      {items.map(n => {
        const pad = { paddingLeft: 8 + depth * 12 }
        if (n.isFile) {
          const on = n.path === active
          return (
            <li key={n.path}>
              <button
                onClick={() => select(n.path)}
                style={pad}
                className={`flex w-full items-center gap-2 rounded-md py-1.5 pr-2 text-left text-sm transition ${
                  on
                    ? 'bg-lilac-wash font-semibold text-iris-bolt'
                    : 'text-slate-veil hover:bg-chalk-canvas hover:text-ink-charcoal'
                }`}
              >
                <FileCode2 className="h-4 w-4 shrink-0" aria-hidden />
                <span className="truncate">{n.name}</span>
              </button>
            </li>
          )
        }
        const isOpen = open.has(n.path)
        return (
          <li key={n.path}>
            <button
              onClick={() => toggle(n.path)}
              style={pad}
              className="flex w-full items-center gap-1 py-1.5 pr-2 text-left text-sm font-medium text-ink-charcoal hover:bg-chalk-canvas"
            >
              {isOpen ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
              <span className="truncate">{n.name}</span>
            </button>
            {isOpen && <Tree node={n} depth={depth + 1} active={active} open={open} toggle={toggle} select={select} />}
          </li>
        )
      })}
    </ul>
  )
}

export default function IdeWorkspace({
  sessionId,
  files: initial,
  highlight,
  incomingChallenge,
  onRunResult,
  emptyHint,
}: Props) {
  const [files, setFiles] = useState(initial)
  const [buffers, setBuffers] = useState<Record<string, string>>({})
  const [active, setActive] = useState(
    () => initial.find(f => f.path.toLowerCase() === 'readme.md')?.path ?? initial[0]?.path ?? ''
  )
  const [open, setOpen] = useState<Set<string>>(
    () => new Set(initial.map(f => f.path.split('/').slice(0, -1).join('/')).filter(Boolean))
  )
  const [mounted, setMounted] = useState(false)
  const [challenge, setChallenge] = useState<CodingChallenge | null>(null)
  const [solved, setSolved] = useState(false)
  const [showBrief, setShowBrief] = useState(true)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<RunCodeResponse | null>(null)
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null)
  const decoRef = useRef<{ clear: () => void } | null>(null)
  const challengeKey = useRef('')

  const tree = useMemo(() => buildTree(files.map(f => f.path)), [files])
  const file = files.find(f => f.path === active)
  const editable = !!challenge && !solved && challenge.target_file === active

  const onMount: OnMount = (editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco
    setMounted(true)
  }

  // Examiner highlight: open file, centre line, decorate range
  useEffect(() => {
    if (!highlight) return
    if (files.some(f => f.path === highlight.file_path)) setActive(highlight.file_path)
    if (!mounted || !editorRef.current || !monacoRef.current) return
    if (file?.path !== highlight.file_path) return

    const monaco = monacoRef.current
    const ed = editorRef.current
    const range = new monaco.Range(highlight.line_start, 1, highlight.line_end, 1)
    const col = ed.createDecorationsCollection([
      {
        range,
        options: {
          isWholeLine: true,
          className: 'vv-line-highlight',
          linesDecorationsClassName: 'vv-line-gutter',
        },
      },
    ])
    ed.revealRangeInCenter(range)
    decoRef.current?.clear()
    decoRef.current = col
    return () => col.clear()
  }, [highlight, mounted, file?.path, files])

  // Challenge arriving from turn response
  useEffect(() => {
    if (!incomingChallenge) return
    const key = `${incomingChallenge.target_file}:${incomingChallenge.description}`
    if (key === challengeKey.current) return
    challengeKey.current = key

    setChallenge(incomingChallenge)
    setSolved(false)
    setShowBrief(true)
    setResult(null)

    setFiles(prev => {
      const exists = prev.some(f => f.path === incomingChallenge.target_file)
      if (exists) return prev
      return [
        ...prev,
        {
          path: incomingChallenge.target_file,
          content: incomingChallenge.starter_code,
          language: 'python',
        },
      ]
    })
    setBuffers(b => ({
      ...b,
      [incomingChallenge.target_file]: incomingChallenge.starter_code,
    }))
    setActive(incomingChallenge.target_file)
  }, [incomingChallenge])

  const toggle = (p: string) =>
    setOpen(s => {
      const n = new Set(s)
      n.has(p) ? n.delete(p) : n.add(p)
      return n
    })

  const run = async () => {
    if (!challenge) return
    setRunning(true)
    setResult(null)
    const code = buffers[challenge.target_file] ?? file?.content ?? ''
    try {
      const res = await runCode({
        session_id: sessionId,
        file_path: challenge.target_file,
        student_code: code,
        test_code: challenge.test_code,
      })
      setResult(res)
      if (res.passed) setSolved(true)
      onRunResult(res)
    } catch (e) {
      const errRes: RunCodeResponse = {
        passed: false,
        stdout: '',
        stderr: e instanceof Error ? e.message : 'Execution failed',
        runtime_ms: 0,
      }
      setResult(errRes)
      onRunResult(errRes)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="card flex h-full min-h-0 flex-col overflow-hidden bg-paper-white">
      {/* Tab bar */}
      <div className="flex items-center gap-2 border-b border-mist-border bg-paper-white p-2.5">
        {file ? (
          <span className="flex items-center gap-2 rounded-md bg-lilac-wash px-2.5 py-1 text-sm font-semibold text-iris-bolt">
            <FileCode2 className="h-4 w-4" aria-hidden />
            {file.path}
            {editable && <span className="text-xs font-normal text-slate-veil">(editable)</span>}
          </span>
        ) : (
          <span className="text-sm text-fog-mist">No file open</span>
        )}
        <span className="ml-auto text-xs text-slate-veil">{editable ? 'Live code challenge active' : 'Read-only view'}</span>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* File tree */}
        <nav aria-label="Files" className="w-56 shrink-0 overflow-auto border-r border-mist-border bg-paper-white p-2">
          {files.length === 0 ? (
            <p className="p-2 text-sm text-fog-mist">No files in workspace.</p>
          ) : (
            <Tree node={tree} depth={0} active={active} open={open} toggle={toggle} select={setActive} />
          )}
        </nav>

        {/* Editor + challenge area */}
        <div className="flex min-w-0 flex-1 flex-col">
          {challenge && (
            <section aria-label="Coding challenge" className="shrink-0 border-b border-mist-border bg-lilac-wash/50 p-3">
              <button
                onClick={() => setShowBrief(v => !v)}
                aria-expanded={showBrief}
                className="flex w-full items-center gap-2 text-left text-sm font-semibold text-ink-charcoal"
              >
                {showBrief ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
                Coding Challenge
                <span className="rounded bg-paper-white px-2 py-0.5 font-mono text-xs font-normal text-slate-veil border border-mist-border">
                  {challenge.target_file}
                </span>
                {solved && (
                  <span className="ml-auto flex items-center gap-1 text-xs font-semibold text-green-600">
                    <Check className="h-3.5 w-3.5" aria-hidden /> Verified
                  </span>
                )}
              </button>
              {showBrief && (
                <div className="mt-2 max-h-44 overflow-auto">
                  <p className="text-sm leading-6 text-slate-veil">{challenge.description}</p>
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-semibold text-iris-bolt hover:underline">
                      View test cases
                    </summary>
                    <pre className="mt-2 overflow-auto rounded-md border border-mist-border bg-paper-white p-3 font-mono text-xs leading-5 text-ink-charcoal">
                      {challenge.test_code}
                    </pre>
                  </details>
                </div>
              )}
            </section>
          )}

          <div className="min-h-0 flex-1 bg-paper-white">
            {file ? (
              <Editor
                height="100%"
                theme="vivavoce"
                path={file.path}
                language={langOf(file)}
                value={buffers[file.path] ?? file.content}
                onChange={v => setBuffers(b => ({ ...b, [file.path]: v ?? '' }))}
                onMount={onMount}
                options={{
                  readOnly: !editable,
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  fontSize: 14,
                  lineHeight: 24,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  padding: { top: 12 },
                  automaticLayout: true,
                  renderLineHighlight: editable ? 'line' : 'none',
                }}
              />
            ) : (
              <div className="flex h-full items-center justify-center p-6 text-center text-sm text-fog-mist">
                {emptyHint ?? 'Files open here when the examiner highlights code or sets a challenge.'}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Run bar + console */}
      <div className="border-t border-mist-border bg-paper-white">
        <div className="flex items-center gap-3 p-3">
          <p className="min-w-0 flex-1 truncate text-sm text-slate-veil">
            {!challenge
              ? 'Run & Verify unlocks when the examiner sets a coding challenge.'
              : solved
              ? 'Challenge verified! Answer the examiner to continue.'
              : 'Edit your code, then click Run & Verify.'}
          </p>
          <button
            onClick={run}
            disabled={!challenge || running || solved}
            className="btn-primary"
            style={{ padding: '8px 20px', fontSize: 14 }}
          >
            {running ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
            Run &amp; Verify
          </button>
        </div>
        <div
          role="log"
          aria-live="polite"
          className="h-32 overflow-auto border-t border-mist-border bg-chalk-canvas p-3 font-mono text-sm leading-6"
        >
          {!result && !running && <span className="text-fog-mist">Test output will appear here.</span>}
          {running && <span className="text-slate-veil">Running test suite…</span>}
          {result && !running && (
            <>
              <div className="mb-1 flex items-center gap-2 font-sans font-semibold text-ink-charcoal">
                {result.passed ? (
                  <Check className="h-4 w-4 text-green-600" aria-hidden />
                ) : (
                  <X className="h-4 w-4 text-red-600" aria-hidden />
                )}
                <span className={result.passed ? 'text-green-700' : 'text-red-700'}>
                  {result.passed ? 'All tests passed' : 'Tests failed'}
                </span>
                <span className="font-normal text-slate-veil text-xs">{result.runtime_ms} ms</span>
              </div>
              {result.stdout && <pre className="whitespace-pre-wrap text-ink-charcoal">{result.stdout}</pre>}
              {result.stderr && <pre className="whitespace-pre-wrap text-red-600">{result.stderr}</pre>}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
