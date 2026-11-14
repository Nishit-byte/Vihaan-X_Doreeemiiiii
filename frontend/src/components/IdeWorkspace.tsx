import { useEffect, useMemo, useRef, useState } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import '../monacoSetup'
import {
  Check,
  ChevronDown,
  ChevronRight,
  FileCode2,
} from 'lucide-react'
import type { CodeHighlight, CodingChallenge, RepoFile, RunCodeResponse } from '../types/api'

interface Props {
  sessionId?: string
  files: RepoFile[]
  highlight: CodeHighlight | null | undefined
  incomingChallenge?: CodingChallenge | null | undefined
  onRunResult?: (res: RunCodeResponse) => void
  emptyHint?: string
  initialLanguage?: string
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

function getMonacoLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  switch (ext) {
    case 'py':
      return 'python'
    case 'ts':
    case 'tsx':
      return 'typescript'
    case 'js':
    case 'jsx':
      return 'javascript'
    case 'cpp':
    case 'cc':
    case 'cxx':
    case 'hpp':
    case 'h':
    case 'c':
      return 'cpp'
    case 'java':
      return 'java'
    case 'md':
      return 'markdown'
    case 'json':
      return 'json'
    case 'html':
      return 'html'
    case 'css':
      return 'css'
    case 'yaml':
    case 'yml':
      return 'yaml'
    case 'sh':
    case 'bash':
      return 'shell'
    case 'rs':
      return 'rust'
    case 'go':
      return 'go'
    case 'sql':
      return 'sql'
    default:
      return 'plaintext'
  }
}

export default function IdeWorkspace({
  files: initial,
  highlight,
  incomingChallenge,
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
  const [showBrief, setShowBrief] = useState(true)

  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null)
  const decoRef = useRef<{ clear: () => void } | null>(null)
  const challengeKey = useRef('')

  const tree = useMemo(() => buildTree(files.map(f => f.path)), [files])
  const file = files.find(f => f.path === active)
  const activeLang = file ? getMonacoLanguage(file.path) : 'plaintext'
  const editable = !!challenge && challenge.target_file === active

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
    setShowBrief(true)

    setFiles(prev => {
      const exists = prev.some(f => f.path === incomingChallenge.target_file)
      if (exists) return prev
      return [
        ...prev,
        {
          path: incomingChallenge.target_file,
          content: incomingChallenge.starter_code,
          language: getMonacoLanguage(incomingChallenge.target_file),
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

  return (
    <div className="card flex h-full min-h-0 flex-col overflow-hidden bg-paper-white shadow-card">
      {/* ── Top Bar: Active File Badge & Detected Language Badge Only (No language select dropdown, no timer) ── */}
      <div className="flex items-center justify-between border-b border-mist-border bg-paper-white px-3 py-2.5">
        <div className="flex items-center gap-2 min-w-0">
          {file ? (
            <span className="flex items-center gap-1.5 rounded-md bg-lilac-wash px-2.5 py-1 text-xs font-semibold text-iris-bolt truncate">
              <FileCode2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="truncate">{file.path}</span>
            </span>
          ) : (
            <span className="text-xs text-fog-mist">No file open</span>
          )}

          {file && (
            <span className="rounded bg-chalk-canvas border border-mist-border px-2 py-0.5 text-[11px] font-mono font-medium text-slate-veil uppercase">
              {activeLang}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] font-medium text-slate-veil">
            {editable ? 'Editable (Challenge Mode)' : 'Read-only view'}
          </span>
        </div>
      </div>

      {/* ── Main View: Collapsible File Tree + Monaco Code Viewer ── */}
      <div className="flex min-h-0 flex-1">
        {/* File tree */}
        <nav aria-label="Repository files" className="w-56 shrink-0 overflow-auto border-r border-mist-border bg-paper-white p-2">
          {files.length === 0 ? (
            <p className="p-2 text-sm text-fog-mist">No files in repository.</p>
          ) : (
            <Tree node={tree} depth={0} active={active} open={open} toggle={toggle} select={setActive} />
          )}
        </nav>

        {/* Editor + AST Highlight / Challenge Area */}
        <div className="flex min-w-0 flex-1 flex-col">
          {challenge && (
            <section aria-label="Coding challenge" className="shrink-0 border-b border-mist-border bg-lilac-wash/40 p-3">
              <button
                onClick={() => setShowBrief(v => !v)}
                aria-expanded={showBrief}
                className="flex w-full items-center gap-2 text-left text-sm font-semibold text-ink-charcoal"
              >
                {showBrief ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
                Coding Challenge
                <span className="rounded border border-mist-border bg-paper-white px-2 py-0.5 font-mono text-xs font-normal text-slate-veil">
                  {challenge.target_file}
                </span>
              </button>
              {showBrief && (
                <div className="mt-2 max-h-40 overflow-auto">
                  <p className="text-sm leading-6 text-slate-veil whitespace-pre-wrap">{challenge.description}</p>
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs font-semibold text-iris-bolt hover:underline">
                      View Pytest Suite
                    </summary>
                    <pre className="mt-2 overflow-auto rounded-md border border-mist-border bg-paper-white p-3 font-mono text-xs leading-5 text-ink-charcoal">
                      {challenge.test_code}
                    </pre>
                  </details>
                </div>
              )}
            </section>
          )}

          {/* Monaco Code Viewer */}
          <div className="min-h-0 flex-1 bg-paper-white">
            {file ? (
              <Editor
                height="100%"
                theme="vivavoce"
                path={file.path}
                language={activeLang}
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
    </div>
  )
}
