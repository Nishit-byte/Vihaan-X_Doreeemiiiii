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

interface TreeNode { name: string; path: string; children: Map<string, TreeNode>; isFile: boolean }

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

const LANG: Record<string, string> = { py: 'python', ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript', md: 'markdown', json: 'json' }
const langOf = (f: RepoFile) => f.language || LANG[f.path.split('.').pop() ?? ''] || 'plaintext'

function Tree({ node, depth, active, open, toggle, select }: {
  node: TreeNode; depth: number; active: string; open: Set<string>
  toggle: (p: string) => void; select: (p: string) => void
}) {
  const items = [...node.children.values()].sort((a, b) => Number(a.isFile) - Number(b.isFile) || a.name.localeCompare(b.name))
  return (
    <ul>
      {items.map(n => {
        const pad = { paddingLeft: 8 + depth * 12 }
        if (n.isFile) {
          const on = n.path === active
          return (
            <li key={n.path}>
              <button onClick={() => select(n.path)} style={pad}
                className={`flex w-full items-center gap-2 rounded-md py-1 pr-2 text-left text-sm ${on ? 'bg-deep-slate text-signal-white' : 'text-muted-fog hover:text-pale-frost'}`}>
                <FileCode2 className="h-4 w-4 shrink-0" aria-hidden /><span className="truncate">{n.name}</span>
              </button>
            </li>
          )
        }
        const isOpen = open.has(n.path)
        return (
          <li key={n.path}>
            <button onClick={() => toggle(n.path)} style={pad}
              className="flex w-full items-center gap-1 py-1 pr-2 text-left text-sm text-pale-frost">
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

export default function IdeWorkspace({ sessionId, files: initial, highlight, incomingChallenge, onRunResult, emptyHint }: Props) {
  const [files, setFiles] = useState(initial)
  const [buffers, setBuffers] = useState<Record<string, string>>({})
  const [active, setActive] = useState(initial[0]?.path ?? '')
  const [open, setOpen] = useState<Set<string>>(() => new Set(initial.map(f => f.path.split('/').slice(0, -1).join('/')).filter(Boolean)))
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
    editorRef.current = editor; monacoRef.current = monaco; setMounted(true)
  }

  // Examiner highlight: open file, centre line, decorate range
  useEffect(() => {
    if (!highlight) return
    if (files.some(f => f.path === highlight.file_path)) setActive(highlight.file_path)
  }, [highlight, files])

  useEffect(() => {
    const editor = editorRef.current, monaco = monacoRef.current
    decoRef.current?.clear(); decoRef.current = null
    if (!mounted || !editor || !monaco || !highlight || highlight.file_path !== active) return
    const id = requestAnimationFrame(() => {
      decoRef.current = editor.createDecorationsCollection([{
        range: new monaco.Range(highlight.line_start, 1, highlight.line_end, 1),
        options: { isWholeLine: true, className: 'vv-line-highlight', linesDecorationsClassName: 'vv-line-gutter' },
      }])
      editor.revealLineInCenter(highlight.line_start)
    })
    return () => cancelAnimationFrame(id)
  }, [highlight, active, mounted])

  // New challenge (repo L4 or DSA question): load starter code. A resend of the
  // same challenge (e.g. after a failed run) keeps the student's code.
  useEffect(() => {
    if (!incomingChallenge) return
    const key = incomingChallenge.target_file + '\n' + incomingChallenge.description
    if (key === challengeKey.current) return
    challengeKey.current = key
    setChallenge(incomingChallenge); setSolved(false); setResult(null); setShowBrief(true)
    setFiles(fs => fs.some(f => f.path === incomingChallenge.target_file) ? fs
      : [...fs, { path: incomingChallenge.target_file, content: incomingChallenge.starter_code, language: '' }])
    setBuffers(b => ({ ...b, [incomingChallenge.target_file]: incomingChallenge.starter_code }))
    setActive(incomingChallenge.target_file)
  }, [incomingChallenge])

  async function run() {
    if (!challenge || running || solved) return
    setRunning(true)
    try {
      const res = await runCode({
        session_id: sessionId, file_path: challenge.target_file,
        student_code: buffers[challenge.target_file] ?? challenge.starter_code, test_code: challenge.test_code,
      })
      setResult(res); if (res.passed) setSolved(true)
      onRunResult(res)
    } catch (e) {
      setResult({ passed: false, stdout: '', stderr: e instanceof Error ? e.message : 'Run failed', runtime_ms: 0 })
    } finally { setRunning(false) }
  }

  const toggle = (p: string) => setOpen(s => { const n = new Set(s); n.has(p) ? n.delete(p) : n.add(p); return n })

  return (
    <div className="panel flex h-full min-h-0 flex-col overflow-hidden">
      {/* tab rail */}
      <div className="flex items-center gap-2 border-b border-steel-outline p-2">
        {file ? (
          <span className="flex items-center gap-2 rounded-md bg-deep-slate px-2.5 py-1.5 text-sm font-medium text-signal-white">
            <FileCode2 className="h-4 w-4 text-nuxt-signal" aria-hidden />{file.path}
          </span>
        ) : <span className="px-2.5 py-1.5 text-sm text-muted-fog">No file open</span>}
        <span className="ml-auto text-xs text-muted-fog">
          {editable ? 'Editable: write your solution' : solved ? 'Verified' : 'Read-only'}
        </span>
      </div>

      <div className="flex min-h-0 flex-1">
        <nav aria-label="Files" className="w-52 shrink-0 overflow-auto border-r border-steel-outline p-2">
          {files.length === 0
            ? <p className="p-2 text-sm text-muted-fog">No files yet.</p>
            : <Tree node={tree} depth={0} active={active} open={open} toggle={toggle} select={setActive} />}
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          {challenge && (
            <section aria-label="Coding challenge" className="shrink-0 border-b border-steel-outline p-3">
              <button onClick={() => setShowBrief(v => !v)} aria-expanded={showBrief}
                className="flex w-full items-center gap-2 text-left text-sm font-semibold text-pale-frost">
                {showBrief ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
                Coding challenge
                <span className="rounded-md bg-deep-slate px-2 py-0.5 font-mono text-xs font-normal text-muted-fog">{challenge.target_file}</span>
                {solved && <span className="ml-auto flex items-center gap-1 text-xs font-medium text-nuxt-signal"><Check className="h-3.5 w-3.5" aria-hidden />Verified</span>}
              </button>
              {showBrief && (
                <div className="mt-2 max-h-44 overflow-auto">
                  <p className="text-sm leading-6 text-muted-fog">{challenge.description}</p>
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-medium text-muted-fog hover:text-pale-frost">View tests</summary>
                    <pre className="mt-2 overflow-auto rounded-md bg-void-canvas p-3 font-mono text-xs leading-5 text-pale-frost">{challenge.test_code}</pre>
                  </details>
                </div>
              )}
            </section>
          )}

          <div className="min-h-0 flex-1">
            {file ? (
              <Editor
                height="100%" theme="vivavoce" path={file.path} language={langOf(file)}
                value={buffers[file.path] ?? file.content}
                onChange={v => setBuffers(b => ({ ...b, [file.path]: v ?? '' }))}
                onMount={onMount}
                options={{
                  readOnly: !editable, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  fontSize: 14, lineHeight: 24, minimap: { enabled: false }, scrollBeyondLastLine: false,
                  padding: { top: 12 }, automaticLayout: true, renderLineHighlight: editable ? 'line' : 'none',
                }}
              />
            ) : (
              <div className="flex h-full items-center justify-center p-6 text-center text-sm text-muted-fog">
                {emptyHint ?? 'Files open here when the examiner highlights code or sets a challenge.'}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* run bar + console */}
      <div className="border-t border-steel-outline">
        <div className="flex items-center gap-3 p-2">
          <p className="min-w-0 flex-1 truncate text-sm text-muted-fog">
            {!challenge ? 'Run & Verify unlocks when the examiner sets a coding challenge.'
              : solved ? 'Challenge verified. Answer the examiner to continue.'
              : 'Edit the file, then run the examiner’s tests.'}
          </p>
          <button onClick={run} disabled={!challenge || running || solved}
            className="inline-flex items-center gap-2 rounded-md bg-nuxt-signal px-3 py-2 text-sm font-medium text-deep-slate hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-40">
            {running ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
            Run &amp; Verify
          </button>
        </div>
        <div role="log" aria-live="polite" className="h-32 overflow-auto border-t border-steel-outline bg-void-canvas p-3 font-mono text-sm leading-6">
          {!result && !running && <span className="text-blue-steel">Test output appears here.</span>}
          {running && <span className="text-muted-fog">Running tests (4s limit)…</span>}
          {result && !running && (
            <>
              <div className="mb-1 flex items-center gap-2 font-sans font-semibold text-signal-white">
                {result.passed
                  ? <Check className="h-4 w-4 text-nuxt-signal" aria-hidden />
                  : <X className="h-4 w-4" aria-hidden />}
                {result.passed ? 'All tests passed' : 'Tests failed'}
                <span className="font-normal text-muted-fog">{result.runtime_ms} ms</span>
              </div>
              {result.stdout && <pre className="whitespace-pre-wrap text-pale-frost">{result.stdout}</pre>}
              {result.stderr && <pre className="whitespace-pre-wrap text-muted-fog">{result.stderr}</pre>}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
