/**
 * LeetCodeWorkspace.tsx — Distraction-Free 2-Column Split-Screen OA Environment.
 * 
 * Complies with:
 * - FIX 2: No pre-written solutions; clean language boilerplate (#include & main()) only.
 *          Single active code file (main.cpp, main.py, Main.java, main.js) — zero file tree clutter.
 * - FIX 3: Dynamic per-question test cases & real multi-language sandbox execution (no hardcoded pass).
 * - FIX 4: Completely zero voice / audio / spoken examiner features (pure text-only AI hint).
 */
import { useEffect, useRef, useState } from 'react'
import Editor, { type OnMount } from '@monaco-editor/react'
import '../monacoSetup'
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Code2,
  FileCode2,
  HelpCircle,
  Lightbulb,
  Loader2,
  Maximize2,
  Pause,
  Play,
  RotateCcw,
  Terminal,
  X,
} from 'lucide-react'
import { runCode } from '../services/apiClient'
import type { OAQuestion, OATestCase, RunCodeRequest, RunCodeResponse, TestCaseResult } from '../types/api'
import { ProctorStatusPill, triggerFullscreen, useProctor } from '../context/ProctorContext'

export interface LanguageBoilerplate {
  id: string
  name: string
  monacoLang: string
  filename: string
  template: string
}

export const LEETCODE_LANGUAGES: LanguageBoilerplate[] = [
  {
    id: 'cpp',
    name: 'C++ (g++ 20)',
    monacoLang: 'cpp',
    filename: 'main.cpp',
    template: `class Solution {
public:
    // Write your solution here
};
`,
  },
  {
    id: 'python',
    name: 'Python 3',
    monacoLang: 'python',
    filename: 'main.py',
    template: `class Solution:
    # Write your solution here
    pass
`,
  },
  {
    id: 'java',
    name: 'Java (OpenJDK 21)',
    monacoLang: 'java',
    filename: 'Main.java',
    template: `class Solution {
    // Write your solution here
}
`,
  },
  {
    id: 'javascript',
    name: 'JavaScript (Node.js)',
    monacoLang: 'javascript',
    filename: 'main.js',
    template: `/**
 * @return {void}
 */
var solve = function() {
    // Write your solution here
};
`,
  },
]

export function getQuestionStarterTemplate(q: OAQuestion, langId: string): string {
  if (q.starter_templates && q.starter_templates[langId]) {
    return q.starter_templates[langId]
  }

  // Derive method name from question title (camelCase)
  const words = q.title.match(/[a-zA-Z0-9]+/g) || ['solve']
  const methodName = words
    .map((w, i) => (i === 0 ? w.toLowerCase() : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()))
    .join('')

  switch (langId) {
    case 'cpp':
      return `class Solution {\npublic:\n    // Write your solution here\n    void ${methodName}() {\n        \n    }\n};\n`
    case 'python':
      return `class Solution:\n    def ${methodName}(self):\n        # Write your solution here\n        pass\n`
    case 'java':
      return `class Solution {\n    public void ${methodName}() {\n        // Write your solution here\n    }\n}\n`
    case 'javascript':
      return `/**\n * @return {void}\n */\nvar ${methodName} = function() {\n    // Write your solution here\n};\n`
    default:
      return `class Solution:\n    def solve(self):\n        pass\n`
  }
}

interface Props {
  sessionId: string
  question: OAQuestion
  questionNumber: number
  totalQuestions: number
  onSolved?: (questionId: string) => void
  initialLanguage?: string
}

export default function LeetCodeWorkspace({
  sessionId,
  question,
  questionNumber,
  totalQuestions,
  onSolved,
  initialLanguage = 'cpp',
}: Props) {
  const { startProctoredSession, isFullscreen, terminatedDueToViolation } = useProctor()

  // Ensure proctored fullscreen session is actively running
  useEffect(() => {
    startProctoredSession(sessionId)
  }, [sessionId, startProctoredSession])

  // Language & Code State
  const [selectedLang, setSelectedLang] = useState<LanguageBoilerplate>(
    () => LEETCODE_LANGUAGES.find(l => l.id === initialLanguage) ?? LEETCODE_LANGUAGES[0]
  )
  const langBuffers = useRef<Record<string, string>>({})
  const [code, setCode] = useState<string>(() => getQuestionStarterTemplate(question, selectedLang.id))

  // Question Solved State
  const [isSolved, setIsSolved] = useState<boolean>(false)

  // AI Hint State (Text-only, Zero Audio)
  const [showHint, setShowHint] = useState<boolean>(false)

  // Assessment Timer State
  const [timerSeconds, setTimerSeconds] = useState<number>(45 * 60) // 45:00 default
  const [isTimerRunning, setIsTimerRunning] = useState<boolean>(true)
  const [isCountdown, setIsCountdown] = useState<boolean>(true)

  // Bottom Console Tabs State
  const [consoleTab, setConsoleTab] = useState<'testcase' | 'result'>('testcase')
  const [activeCaseIdx, setActiveCaseIdx] = useState<number>(0) // 0: Case 1, 1: Case 2, 2: Custom
  const [customInput, setCustomInput] = useState<string>('')

  // Execution State
  const [executing, setExecuting] = useState<boolean>(false)
  const [result, setResult] = useState<RunCodeResponse | null>(null)

  // Visible test cases for the problem
  const visibleCases = (question.test_cases || []).filter(tc => !tc.is_hidden)
  const sampleCases =
    visibleCases.length > 0
      ? visibleCases
      : (question.examples || []).map(ex => ({
          stdin: ex.input,
          expected_output: ex.output,
          is_hidden: false,
        }))

  // Sync when question changes
  useEffect(() => {
    langBuffers.current = {}
    setCode(getQuestionStarterTemplate(question, selectedLang.id))
    setIsSolved(false)
    setShowHint(false)
    setResult(null)
    setConsoleTab('testcase')
    setActiveCaseIdx(0)
    setCustomInput(sampleCases[0]?.stdin || '')
  }, [question.question_id])

  // Freeze assessment timer on anti-plagiarism termination
  useEffect(() => {
    if (terminatedDueToViolation) {
      setIsTimerRunning(false)
    }
  }, [terminatedDueToViolation])

  // Timer interval hook
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

  // Handle switching language
  const handleLanguageChange = (newLang: LanguageBoilerplate) => {
    // Save current code to buffer
    langBuffers.current[selectedLang.id] = code

    setSelectedLang(newLang)
    const existingCode = langBuffers.current[newLang.id] ?? getQuestionStarterTemplate(question, newLang.id)
    setCode(existingCode)
  }

  // Reset to empty starter template
  const handleResetCode = () => {
    const template = getQuestionStarterTemplate(question, selectedLang.id)
    if (window.confirm(`Reset code to empty ${selectedLang.name} starter template?`)) {
      setCode(template)
      langBuffers.current[selectedLang.id] = template
    }
  }

  // Execute visible sample test cases (Run)
  const handleRun = async () => {
    if (terminatedDueToViolation) return
    triggerFullscreen()
    setExecuting(true)
    setConsoleTab('result')
    setResult(null)

    const isCustom = activeCaseIdx === sampleCases.length
    const casesToSend = sampleCases.map(c => ({
      stdin: c.stdin,
      expected_output: c.expected_output,
      is_hidden: false,
    }))

    const req: RunCodeRequest = {
      session_id: sessionId,
      question_id: question.question_id,
      file_path: selectedLang.filename,
      source_code: code,
      language: selectedLang.id,
      test_cases: isCustom ? [] : casesToSend,
      run_hidden: false,
      custom_input: isCustom ? customInput : undefined,
      driver_code: question.driver_code?.[selectedLang.id],
    }

    try {
      const res = await runCode(req)
      setResult(res)
    } catch (e) {
      setResult({
        passed: false,
        verdict: 'Runtime Error',
        stdout: '',
        stderr: e instanceof Error ? e.message : 'Execution failed.',
        runtime_ms: 0,
      })
    } finally {
      setExecuting(false)
    }
  }

  // Execute all test cases (Submit / Run & Verify)
  const handleSubmit = async () => {
    if (terminatedDueToViolation) return
    triggerFullscreen()
    setExecuting(true)
    setConsoleTab('result')
    setResult(null)

    const allCases = (question.test_cases && question.test_cases.length > 0)
      ? question.test_cases
      : sampleCases

    const req: RunCodeRequest = {
      session_id: sessionId,
      question_id: question.question_id,
      file_path: selectedLang.filename,
      source_code: code,
      language: selectedLang.id,
      test_cases: allCases,
      run_hidden: true,
      driver_code: question.driver_code?.[selectedLang.id],
    }

    try {
      const res = await runCode(req)
      setResult(res)
      if (res.passed) {
        setIsSolved(true)
        onSolved?.(question.question_id)
      }
    } catch (e) {
      setResult({
        passed: false,
        verdict: 'Runtime Error',
        stdout: '',
        stderr: e instanceof Error ? e.message : 'Submission failed.',
        runtime_ms: 0,
      })
    } finally {
      setExecuting(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 w-full overflow-hidden bg-chalk-canvas">
      {/* ── LEFT PANE (40% width): Problem Description, Examples, Constraints, AI Hint ── */}
      <section
        style={{ flex: '0 0 40%' }}
        className="flex min-w-0 flex-col overflow-y-auto border-r border-mist-border bg-paper-white p-6 shadow-sm"
      >
        {/* Header Badges */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold text-iris-bolt px-2.5 py-1 rounded bg-lilac-wash">
              {question.question_id}
            </span>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                padding: '2px 10px',
                borderRadius: 200,
                background:
                  question.difficulty === 'Easy' ? '#dcfce7' : question.difficulty === 'Medium' ? '#fef3c7' : '#fee2e2',
                color:
                  question.difficulty === 'Easy' ? '#15803d' : question.difficulty === 'Medium' ? '#b45309' : '#b91c1c',
              }}
            >
              {question.difficulty}
            </span>
            {isSolved && (
              <span className="flex items-center gap-1 text-xs font-bold text-green-600 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full">
                <Check className="h-3 w-3" /> Solved
              </span>
            )}
          </div>
          <span className="text-xs text-slate-veil">
            Question {questionNumber} of {totalQuestions}
          </span>
        </div>

        {/* Title */}
        <h1 className="text-xl font-bold text-ink-charcoal mb-2 leading-tight">
          {question.title}
        </h1>

        {/* Topic Chips */}
        <div className="flex flex-wrap gap-1.5 mb-4">
          {question.topics.map(t => (
            <span
              key={t}
              className="text-[11px] font-semibold text-slate-veil bg-chalk-canvas border border-mist-border px-2.5 py-0.5 rounded-full"
            >
              {t}
            </span>
          ))}
        </div>

        {/* Selection Reason */}
        <div className="rounded-lg bg-lilac-wash/50 border border-mist-border p-3 text-xs text-deep-indigo mb-5 leading-relaxed">
          <strong className="text-iris-bolt">Why this problem:</strong> {question.selection_reason}
        </div>

        {/* Problem Statement Specification */}
        <div className="mb-6">
          <h2 className="text-sm font-bold text-ink-charcoal uppercase tracking-wider mb-2">Description</h2>
          <div className="text-sm text-slate-veil leading-relaxed whitespace-pre-wrap font-sans">
            {question.problem_statement}
          </div>
        </div>

        {/* Examples */}
        <div className="mb-6">
          <h2 className="text-sm font-bold text-ink-charcoal uppercase tracking-wider mb-2">Examples</h2>
          <div className="space-y-3">
            {question.examples.map((ex, idx) => (
              <div
                key={idx}
                className="rounded-lg border border-mist-border bg-chalk-canvas p-3 font-mono text-xs"
              >
                <div className="font-semibold text-ink-charcoal mb-1">Example {idx + 1}:</div>
                <div className="text-slate-veil mb-1">
                  <span className="font-bold text-ink-charcoal">Input:</span> {ex.input}
                </div>
                <div className="text-slate-veil mb-1">
                  <span className="font-bold text-ink-charcoal">Output:</span> {ex.output}
                </div>
                {ex.explanation && (
                  <div className="text-slate-veil font-sans text-xs mt-1 border-t border-mist-border pt-1">
                    <span className="font-semibold text-ink-charcoal">Explanation:</span> {ex.explanation}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Constraints */}
        <div className="mb-6">
          <h2 className="text-sm font-bold text-ink-charcoal uppercase tracking-wider mb-2">Constraints</h2>
          <ul className="list-disc pl-5 space-y-1 text-xs text-slate-veil font-mono">
            {question.constraints.map((c, idx) => (
              <li key={idx}>{c}</li>
            ))}
          </ul>
        </div>

        {/* AI Hint Section (Text-Only, Zero Voice / Zero Audio) */}
        <div className="mt-auto pt-4 border-t border-mist-border">
          <button
            onClick={() => setShowHint(v => !v)}
            className="flex items-center gap-2 text-xs font-semibold text-iris-bolt hover:underline"
          >
            <Lightbulb className="h-4 w-4" />
            {showHint ? 'Hide Algorithmic Hint' : 'Need an Algorithmic Hint?'}
          </button>
          {showHint && (
            <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 leading-relaxed animate-in fade-in duration-200">
              <strong className="block mb-1 font-bold">💡 Approach Hint:</strong>
              Consider the constraints carefully: an O(n log n) or O(n) solution is expected. Look for standard patterns like two-pointer sweeps, monotonic queues, or hash map frequency counting to avoid brute-force O(n²) loops.
            </div>
          )}
        </div>
      </section>

      {/* ── RIGHT PANE (60% width): Language Selector, Timer, Monaco Editor & Execution Console ── */}
      <section
        style={{ flex: '0 0 60%' }}
        className="flex min-w-0 flex-col overflow-hidden bg-paper-white"
      >
        {/* Editor Top Bar: Language Dropdown, Filename, Assessment Timer, Reset Button */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-mist-border bg-paper-white px-4 py-2.5 shadow-sm">
          {/* Left: Active File & Language Selector */}
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 rounded-md bg-lilac-wash px-2.5 py-1 text-xs font-semibold text-iris-bolt">
              <FileCode2 className="h-3.5 w-3.5" />
              {selectedLang.filename}
            </span>

            {/* Language Selector Dropdown (C++, Python, Java, JavaScript) */}
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

          {/* Right: Proctor Status, Assessment Timer & Reset */}
          <div className="flex items-center gap-2">
            <ProctorStatusPill />

            {/* Live Ticking Assessment Timer */}
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
              onClick={() => {
                setTimerSeconds(isCountdown ? 45 * 60 : 0)
                setIsTimerRunning(false)
              }}
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

            <div className="h-4 w-px bg-mist-border mx-1" />

            {/* Reset Code to Clean Boilerplate */}
            <button
              onClick={handleResetCode}
              title="Reset to empty starter boilerplate"
              className="flex items-center gap-1 text-xs text-slate-veil hover:text-ink-charcoal px-2 py-1 rounded hover:bg-chalk-canvas"
            >
              <RotateCcw className="h-3 w-3" /> Reset Code
            </button>
          </div>
        </div>

        {/* Monaco Code Editor (Clean Boilerplate, Always Editable) */}
        <div className="flex-1 min-h-0 bg-paper-white">
          <Editor
            height="100%"
            theme="vivavoce"
            path={selectedLang.filename}
            language={selectedLang.monacoLang}
            value={code}
            onChange={v => setCode(v ?? '')}
            options={{
              readOnly: false,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
              fontSize: 14,
              lineHeight: 24,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              padding: { top: 12 },
              automaticLayout: true,
              renderLineHighlight: 'line',
              tabSize: selectedLang.id === 'python' ? 4 : 2,
            }}
          />
        </div>

        {/* ── Bottom Execution Console (Testcase / Test Result Tabs) ── */}
        <div className="flex flex-col border-t border-mist-border bg-paper-white shrink-0">
          {/* Console Header Tabs & Actions */}
          <div className="flex items-center justify-between border-b border-mist-border px-4 py-2 bg-chalk-canvas/60">
            {/* Tabs */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setConsoleTab('testcase')}
                className={`rounded px-3 py-1 text-xs font-semibold transition ${
                  consoleTab === 'testcase'
                    ? 'bg-paper-white text-iris-bolt shadow-sm border border-mist-border'
                    : 'text-slate-veil hover:text-ink-charcoal'
                }`}
              >
                Testcase
              </button>
              <button
                onClick={() => setConsoleTab('result')}
                className={`flex items-center gap-1.5 rounded px-3 py-1 text-xs font-semibold transition ${
                  consoleTab === 'result'
                    ? 'bg-paper-white text-iris-bolt shadow-sm border border-mist-border'
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

            {/* Run & Submit Actions */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleRun}
                disabled={executing || terminatedDueToViolation}
                className="btn-outline flex items-center gap-1.5"
                style={{
                  padding: '6px 14px',
                  fontSize: 13,
                  opacity: terminatedDueToViolation ? 0.5 : 1,
                  cursor: terminatedDueToViolation ? 'not-allowed' : 'pointer',
                }}
              >
                {executing && consoleTab === 'testcase' ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Terminal className="h-3.5 w-3.5" />
                )}
                Run
              </button>

              <button
                onClick={handleSubmit}
                disabled={executing || isSolved || terminatedDueToViolation}
                className="btn-primary flex items-center gap-1.5"
                style={{
                  background: isSolved ? '#16a34a' : 'var(--color-iris-bolt)',
                  padding: '6px 18px',
                  fontSize: 13,
                  opacity: terminatedDueToViolation ? 0.5 : 1,
                  cursor: terminatedDueToViolation ? 'not-allowed' : 'pointer',
                }}
              >
                {executing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : isSolved ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <Play className="h-3.5 w-3.5" />
                )}
                {isSolved ? 'Accepted' : 'Run & Verify (Submit)'}
              </button>
            </div>
          </div>

          {/* Console Content: 140px fixed height */}
          <div className="h-44 overflow-y-auto bg-chalk-canvas p-3 font-mono text-xs">
            {/* Tab 1: Testcase */}
            {consoleTab === 'testcase' && (
              <div>
                {/* Case Selector Tabs */}
                <div className="flex items-center gap-2 mb-2">
                  {sampleCases.map((tc, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setActiveCaseIdx(idx)
                        setCustomInput(tc.stdin)
                      }}
                      className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                        activeCaseIdx === idx
                          ? 'bg-paper-white text-iris-bolt shadow-sm border border-mist-border'
                          : 'text-slate-veil hover:text-ink-charcoal'
                      }`}
                    >
                      Case {idx + 1}
                    </button>
                  ))}
                  <button
                    onClick={() => setActiveCaseIdx(sampleCases.length)}
                    className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                      activeCaseIdx === sampleCases.length
                        ? 'bg-paper-white text-iris-bolt shadow-sm border border-mist-border'
                        : 'text-slate-veil hover:text-ink-charcoal'
                    }`}
                  >
                    Custom Input
                  </button>
                </div>

                {/* Stdin Input Area */}
                <div>
                  <label className="block text-[10px] font-bold uppercase text-slate-veil mb-1">
                    Standard Input (stdin)
                  </label>
                  <textarea
                    value={
                      activeCaseIdx < sampleCases.length
                        ? sampleCases[activeCaseIdx]?.stdin || ''
                        : customInput
                    }
                    onChange={e => {
                      if (activeCaseIdx === sampleCases.length) {
                        setCustomInput(e.target.value)
                      }
                    }}
                    readOnly={activeCaseIdx < sampleCases.length}
                    rows={3}
                    placeholder="Enter standard input..."
                    className="w-full rounded border border-mist-border bg-paper-white p-2 text-ink-charcoal focus:border-iris-bolt focus:outline-none"
                  />
                  {activeCaseIdx < sampleCases.length && (
                    <div className="mt-1 text-[11px] text-slate-veil">
                      <strong>Expected Output:</strong>{' '}
                      <code>{sampleCases[activeCaseIdx]?.expected_output}</code>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Tab 2: Test Result */}
            {consoleTab === 'result' && (
              <div>
                {!result && !executing && (
                  <div className="flex h-32 items-center justify-center text-slate-veil">
                    Click "Run" or "Run &amp; Verify (Submit)" to execute your solution in the sandbox.
                  </div>
                )}

                {executing && (
                  <div className="flex h-32 items-center justify-center gap-2 text-slate-veil">
                    <Loader2 className="h-4 w-4 animate-spin text-iris-bolt" />
                    Compiling and running against test cases in sandbox…
                  </div>
                )}

                {result && !executing && (
                  <div className="space-y-3">
                    {/* Status Badge + Metrics */}
                    <div className="flex items-center gap-3">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-bold ${
                          result.passed
                            ? 'bg-green-100 text-green-700'
                            : 'bg-red-100 text-red-700'
                        }`}
                      >
                        {result.passed ? (
                          <Check className="h-3.5 w-3.5" />
                        ) : (
                          <AlertCircle className="h-3.5 w-3.5" />
                        )}
                        {result.verdict || (result.passed ? 'Accepted' : 'Wrong Answer')}
                      </span>

                      <span className="text-slate-veil text-xs">
                        Runtime: <strong>{result.runtime_ms} ms</strong>
                      </span>

                      {result.total_cases ? (
                        <span className="text-slate-veil text-xs">
                          Test Cases: <strong>{result.passed_cases} / {result.total_cases} passed</strong>
                        </span>
                      ) : null}
                    </div>

                    {/* Stderr / Compiler Output if failed */}
                    {result.stderr && (
                      <div className="rounded border border-red-200 bg-red-50 p-2 text-red-700">
                        <span className="block text-[10px] font-bold uppercase text-red-500 mb-1">
                          Compiler / Runtime Output:
                        </span>
                        <pre className="whitespace-pre-wrap">{result.stderr}</pre>
                      </div>
                    )}

                    {/* Per-Testcase Details */}
                    {result.test_results && result.test_results.length > 0 && (
                      <div className="space-y-2">
                        {result.test_results.map(tc => (
                          <div
                            key={tc.case_num}
                            className={`rounded border p-2 ${
                              tc.passed
                                ? 'border-green-200 bg-green-50/50'
                                : 'border-red-200 bg-red-50/50'
                            }`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-bold text-ink-charcoal">
                                Case {tc.case_num} {tc.is_hidden ? '(Hidden Testcase)' : ''}
                              </span>
                              <span
                                className={`text-[10px] font-bold uppercase ${
                                  tc.passed ? 'text-green-600' : 'text-red-600'
                                }`}
                              >
                                {tc.passed ? 'Passed' : 'Failed'}
                              </span>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                              <div>
                                <span className="text-slate-veil block font-sans">Input (stdin):</span>
                                <pre className="bg-paper-white p-1 rounded border border-mist-border overflow-x-auto">
                                  {tc.stdin || '(empty)'}
                                </pre>
                              </div>

                              <div>
                                <span className="text-slate-veil block font-sans">Your Output:</span>
                                <pre
                                  className={`p-1 rounded border overflow-x-auto ${
                                    tc.passed
                                      ? 'bg-paper-white border-mist-border text-ink-charcoal'
                                      : 'bg-red-50 border-red-200 text-red-700'
                                  }`}
                                >
                                  {tc.actual_output || '(empty)'}
                                </pre>
                              </div>
                            </div>

                            {tc.expected_output && !tc.passed && (
                              <div className="mt-1 text-[11px]">
                                <span className="text-slate-veil font-sans">Expected Output:</span>{' '}
                                <code className="text-green-700 font-bold">{tc.expected_output}</code>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Stdout if custom run */}
                    {result.stdout && (!result.test_results || result.test_results.length === 0) && (
                      <div className="rounded border border-mist-border bg-paper-white p-2">
                        <span className="block text-[10px] font-bold uppercase text-slate-veil mb-1">
                          Standard Output
                        </span>
                        <pre className="whitespace-pre-wrap text-ink-charcoal">{result.stdout}</pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
