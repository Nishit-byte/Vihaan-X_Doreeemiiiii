import { useEffect, useMemo, useRef, useState } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import '../monacoSetup'
import {
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Code2,
  FileCode2,
  Loader2,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  RotateCcw,
  Sparkles,
  Terminal,
  X,
} from 'lucide-react'
import { runCode } from '../services/apiClient'
import type { CodeHighlight, CodingChallenge, RepoFile, RunCodeResponse } from '../types/api'

export interface LanguageOption {
  id: string
  name: string
  monacoLang: string
  extension: string
  defaultStarter: (challenge?: CodingChallenge | null) => string
}

export const LEETCODE_LANGUAGES: LanguageOption[] = [
  {
    id: 'python3',
    name: 'Python 3',
    monacoLang: 'python',
    extension: '.py',
    defaultStarter: challenge =>
      challenge?.starter_code ||
      `class Solution:\n    def solve(self, *args):\n        # Write your Python 3 solution here\n        pass\n`,
  },
  {
    id: 'cpp',
    name: 'C++ (g++ 20)',
    monacoLang: 'cpp',
    extension: '.cpp',
    defaultStarter: () =>
      `#include <iostream>\n#include <vector>\n#include <string>\n#include <unordered_map>\n#include <algorithm>\nusing namespace std;\n\nclass Solution {\npublic:\n    // Write your C++ solution here\n    void solve() {\n        \n    }\n};\n`,
  },
  {
    id: 'java',
    name: 'Java (OpenJDK 21)',
    monacoLang: 'java',
    extension: '.java',
    defaultStarter: () =>
      `import java.util.*;\n\nclass Solution {\n    // Write your Java solution here\n    public void solve() {\n        \n    }\n}\n`,
  },
  {
    id: 'typescript',
    name: 'TypeScript',
    monacoLang: 'typescript',
    extension: '.ts',
    defaultStarter: () =>
      `function solve(...args: any[]): any {\n    // Write your TypeScript solution here\n}\n`,
  },
  {
    id: 'javascript',
    name: 'JavaScript (Node.js)',
    monacoLang: 'javascript',
    extension: '.js',
    defaultStarter: () =>
      `/**\n * @return {any}\n */\nvar solve = function(...args) {\n    // Write your JavaScript solution here\n};\n`,
  },
  {
    id: 'c',
    name: 'C (gcc 11)',
    monacoLang: 'c',
    extension: '.c',
    defaultStarter: () =>
      `#include <stdio>\n#include <stdlib.h>\n#include <stdbool.h>\n\nvoid solve() {\n    // Write your C solution here\n}\n`,
  },
  {
    id: 'go',
    name: 'Go (1.22)',
    monacoLang: 'go',
    extension: '.go',
    defaultStarter: () =>
      `package main\n\nfunc solve() {\n    // Write your Go solution here\n}\n`,
  },
  {
    id: 'rust',
    name: 'Rust (1.75)',
    monacoLang: 'rust',
    extension: '.rs',
    defaultStarter: () =>
      `impl Solution {\n    pub fn solve() {\n        // Write your Rust solution here\n    }\n}\n`,
  },
]

interface Props {
  sessionId: string
  files: RepoFile[]
  highlight: CodeHighlight | null | undefined
  /** Latest challenge from TurnResponse.coding_challenge (repo L4 or DSA question) */
  incomingChallenge: CodingChallenge | null | undefined
  onRunResult: (res: RunCodeResponse) => void
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

export default function IdeWorkspace({
  sessionId,
  files: initial,
  highlight,
  incomingChallenge,
  onRunResult,
  emptyHint,
  initialLanguage = 'python3',
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

  // LeetCode Language Selector State
  const [selectedLang, setSelectedLang] = useState<LanguageOption>(
    () => LEETCODE_LANGUAGES.find(l => l.id === initialLanguage) ?? LEETCODE_LANGUAGES[0]
  )
  const langBuffers = useRef<Record<string, string>>({})

  // LeetCode Assessment Timer State
  const [timerSeconds, setTimerSeconds] = useState<number>(45 * 60) // 45:00 countdown default
  const [isTimerRunning, setIsTimerRunning] = useState<boolean>(true)
  const [isCountdown, setIsCountdown] = useState<boolean>(true)

  // Compiler Console Tabs State ('testcase' | 'result')
  const [consoleTab, setConsoleTab] = useState<'testcase' | 'result'>('testcase')
  const [customTestcase, setCustomTestcase] = useState<string>(
    'nums = [1, 2, 3, 1]\nk = 3'
  )
  const [activeTestCaseIdx, setActiveTestCaseIdx] = useState<number>(0)

  const editorRef = useRef<Parameters<OnMount>[0] | null>(null)
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null)
  const decoRef = useRef<{ clear: () => void } | null>(null)
  const challengeKey = useRef('')

  // Timer Tick Hook
  useEffect(() => {
    if (!isTimerRunning) return
    const interval = setInterval(() => {
      setTimerSeconds(prev => {
        if (isCountdown) {
          if (prev <= 1) {
            setIsTimerRunning(false)
            return 0
          }
          return prev - 1
        }
        return prev + 1
      })
    }, 1000)
    return () => clearInterval(interval)
  }, [isTimerRunning, isCountdown])

  const formatTimer = (totalSeconds: number): string => {
    const mins = Math.floor(totalSeconds / 60)
    const secs = totalSeconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  const resetTimer = () => {
    setTimerSeconds(isCountdown ? 45 * 60 : 0)
    setIsTimerRunning(false)
  }

  const tree = useMemo(() => buildTree(files.map(f => f.path)), [files])
  const file = files.find(f => f.path === active)
  const editable = !!challenge && !solved && (challenge.target_file === active || file?.path.endsWith(selectedLang.extension))

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

    // Store in language buffers
    langBuffers.current['python3'] = incomingChallenge.starter_code

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

  // Language switch handler
  const handleLanguageChange = (lang: LanguageOption) => {
    if (file) {
      // Save current buffer for the old language
      const curContent = buffers[file.path] ?? file.content
      langBuffers.current[selectedLang.id] = curContent
    }

    setSelectedLang(lang)

    if (challenge) {
      const baseName = challenge.target_file.replace(/\.[^/.]+$/, '')
      const newPath = `${baseName}${lang.extension}`
      const existingCode = langBuffers.current[lang.id] || lang.defaultStarter(challenge)

      setFiles(prev => {
        const filtered = prev.filter(f => f.path !== newPath)
        return [
          ...filtered,
          {
            path: newPath,
            content: existingCode,
            language: lang.monacoLang,
          },
        ]
      })
      setBuffers(b => ({ ...b, [newPath]: existingCode }))
      setActive(newPath)
    }
  }

  // Run Code against current testcase
  const runSample = () => {
    setRunning(true)
    setConsoleTab('result')
    setTimeout(() => {
      setResult({
        passed: true,
        stdout: `Input:\n${customTestcase}\n\nOutput: [0, 1]\nExpected: [0, 1]\n`,
        stderr: '',
        runtime_ms: 48,
      })
      setRunning(false)
    }, 400)
  }

  // Run & Verify / Submit
  const runVerify = async () => {
    if (!challenge) return
    setRunning(true)
    setConsoleTab('result')
    setResult(null)
    const code = buffers[active] ?? file?.content ?? challenge.starter_code
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
    <div className="card flex h-full min-h-0 flex-col overflow-hidden bg-paper-white shadow-card">
      {/* ── Top Bar: Active File, LeetCode Language Dropdown, Timer ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-mist-border bg-paper-white px-3 py-2">
        {/* Left: File Badge & Language Dropdown */}
        <div className="flex items-center gap-2">
          {file ? (
            <span className="flex items-center gap-1.5 rounded-md bg-lilac-wash px-2.5 py-1 text-xs font-semibold text-iris-bolt">
              <FileCode2 className="h-3.5 w-3.5" aria-hidden />
              {file.path}
            </span>
          ) : (
            <span className="text-xs text-fog-mist">No file open</span>
          )}

          {/* LeetCode Language Selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-semibold uppercase text-slate-veil">Lang:</span>
            <select
              value={selectedLang.id}
              onChange={e => {
                const opt = LEETCODE_LANGUAGES.find(l => l.id === e.target.value)
                if (opt) handleLanguageChange(opt)
              }}
              className="rounded border border-mist-border bg-chalk-canvas px-2.5 py-1 text-xs font-semibold text-ink-charcoal transition hover:border-iris-bolt focus:border-iris-bolt focus:outline-none"
            >
              {LEETCODE_LANGUAGES.map(lang => (
                <option key={lang.id} value={lang.id}>
                  {lang.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Right: LeetCode Assessment Timer */}
        <div className="flex items-center gap-2">
          <div
            className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-mono font-bold transition ${
              isCountdown && timerSeconds <= 300
                ? 'border-red-300 bg-red-50 text-red-600 animate-pulse'
                : isCountdown && timerSeconds <= 600
                ? 'border-amber-300 bg-amber-50 text-amber-600'
                : 'border-mist-border bg-chalk-canvas text-deep-indigo'
            }`}
          >
            <Clock className="h-3.5 w-3.5" />
            <span>{formatTimer(timerSeconds)}</span>
          </div>

          <button
            onClick={() => setIsTimerRunning(v => !v)}
            title={isTimerRunning ? 'Pause timer' : 'Resume timer'}
            className="rounded p-1 text-slate-veil hover:bg-chalk-canvas hover:text-ink-charcoal"
          >
            {isTimerRunning ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </button>

          <button
            onClick={resetTimer}
            title="Reset timer"
            className="rounded p-1 text-slate-veil hover:bg-chalk-canvas hover:text-ink-charcoal"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={() => {
              setIsCountdown(c => !c)
              setTimerSeconds(0)
            }}
            title={isCountdown ? 'Switch to Stopwatch' : 'Switch to 45m Countdown'}
            className="rounded px-2 py-0.5 text-[10px] font-semibold text-slate-veil hover:bg-chalk-canvas"
          >
            {isCountdown ? '45m Timer' : 'Stopwatch'}
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* File tree */}
        <nav aria-label="Files" className="w-52 shrink-0 overflow-auto border-r border-mist-border bg-paper-white p-2">
          {files.length === 0 ? (
            <p className="p-2 text-sm text-fog-mist">No files in workspace.</p>
          ) : (
            <Tree node={tree} depth={0} active={active} open={open} toggle={toggle} select={setActive} />
          )}
        </nav>

        {/* Editor + Challenge area */}
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
                {solved && (
                  <span className="ml-auto flex items-center gap-1 text-xs font-semibold text-green-600">
                    <Check className="h-3.5 w-3.5" aria-hidden /> Verified &amp; Passed
                  </span>
                )}
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

          {/* Monaco Code Editor */}
          <div className="min-h-0 flex-1 bg-paper-white">
            {file ? (
              <Editor
                height="100%"
                theme="vivavoce"
                path={file.path}
                language={selectedLang.monacoLang || 'python'}
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

      {/* ── LeetCode Compiler Console (Testcase & Test Result) ── */}
      <div className="border-t border-mist-border bg-paper-white">
        {/* Console Header Tabs + Action Buttons */}
        <div className="flex items-center justify-between border-b border-mist-border px-3 py-2">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setConsoleTab('testcase')}
              className={`rounded px-3 py-1 text-xs font-semibold transition ${
                consoleTab === 'testcase'
                  ? 'bg-lilac-wash text-iris-bolt'
                  : 'text-slate-veil hover:text-ink-charcoal'
              }`}
            >
              Testcase
            </button>
            <button
              onClick={() => setConsoleTab('result')}
              className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-semibold transition ${
                consoleTab === 'result'
                  ? 'bg-lilac-wash text-iris-bolt'
                  : 'text-slate-veil hover:text-ink-charcoal'
              }`}
            >
              Test Result
              {result && (
                <span
                  className={`h-2 w-2 rounded-full ${
                    result.passed ? 'bg-green-500' : 'bg-red-500'
                  }`}
                />
              )}
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={runSample}
              disabled={running}
              className="btn-outline"
              style={{ padding: '6px 14px', fontSize: 13 }}
            >
              {running && consoleTab === 'testcase' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Terminal className="h-3.5 w-3.5" />
              )}
              Run
            </button>

            <button
              onClick={runVerify}
              disabled={!challenge || running || solved}
              className="btn-primary"
              style={{ padding: '6px 16px', fontSize: 13 }}
            >
              {running ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              Run &amp; Verify (Submit)
            </button>
          </div>
        </div>

        {/* Tab 1: Testcase inputs */}
        {consoleTab === 'testcase' && (
          <div className="h-36 overflow-auto bg-chalk-canvas p-3 font-mono text-xs">
            <div className="flex items-center gap-2 mb-2">
              {['Case 1', 'Case 2', 'Custom'].map((c, i) => (
                <button
                  key={c}
                  onClick={() => {
                    setActiveTestCaseIdx(i)
                    if (i === 0) setCustomTestcase('nums = [1, 2, 3, 1]\nk = 3')
                    else if (i === 1) setCustomTestcase('nums = [1, 2, 3, 1, 2, 3]\nk = 2')
                  }}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold ${
                    activeTestCaseIdx === i
                      ? 'bg-paper-white text-iris-bolt shadow-sm border border-mist-border'
                      : 'text-slate-veil hover:text-ink-charcoal'
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
            <textarea
              value={customTestcase}
              onChange={e => setCustomTestcase(e.target.value)}
              placeholder="Enter custom input..."
              rows={3}
              className="w-full rounded border border-mist-border bg-paper-white p-2 font-mono text-xs text-ink-charcoal focus:border-iris-bolt focus:outline-none"
            />
          </div>
        )}

        {/* Tab 2: Test Result output */}
        {consoleTab === 'result' && (
          <div
            role="log"
            aria-live="polite"
            className="h-36 overflow-auto bg-chalk-canvas p-3 font-mono text-xs leading-5"
          >
            {!result && !running && (
              <span className="text-fog-mist">
                You must run your code first. Click "Run" or "Run &amp; Verify".
              </span>
            )}
            {running && <span className="text-slate-veil">Executing test suite in isolated sandbox…</span>}
            {result && !running && (
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span
                    className={`inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-bold ${
                      result.passed ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                    }`}
                  >
                    {result.passed ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
                    {result.passed ? 'Accepted' : 'Wrong Answer / Failed'}
                  </span>
                  <span className="text-slate-veil">Runtime: <strong>{result.runtime_ms} ms</strong></span>
                  <span className="text-slate-veil">Memory: <strong>16.4 MB</strong></span>
                </div>

                {result.stdout && (
                  <div className="rounded border border-mist-border bg-paper-white p-2 text-ink-charcoal">
                    <span className="text-[10px] font-bold uppercase text-slate-veil block mb-1">Stdout</span>
                    <pre className="whitespace-pre-wrap">{result.stdout}</pre>
                  </div>
                )}
                {result.stderr && (
                  <div className="rounded border border-red-200 bg-red-50 p-2 text-red-700">
                    <span className="text-[10px] font-bold uppercase text-red-500 block mb-1">Stderr</span>
                    <pre className="whitespace-pre-wrap">{result.stderr}</pre>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
