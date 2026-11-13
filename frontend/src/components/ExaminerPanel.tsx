/**
 * M3 Voice Pipeline — ExaminerPanel Component (Task B4)
 *
 * Implements the visual panel layout per CONTEXT §5.9 & TASKS B4:
 * - Sub-components (all in this file):
 *     1. ExaminerHeader (title + reactive status pill)
 *     2. DepthMeter (L1 Recall, L2 Comprehension, L3 Analysis, L4 Evaluation with animated highlight)
 *     3. VoiceOrbPlaceholder (centered state-reactive orb with glow / ring effects)
 *     4. QuestionCard (topic chip, depth chip, muted ack_text, bold question_text, aria-live='polite')
 *     5. DoneCard ('Viva complete' + 'View report' button -> onRequestReport)
 *     6. TranscriptHistory (collapsible, question + student transcript + verdict badge)
 *     7. PushToTalkButton (press-and-hold with pointer events, 'Hold Space to answer' label)
 *     8. TextFallbackInput (Enter submits, Shift+Enter newline)
 *
 * Styling & Sizing:
 * - Tailwind CSS, dark slate theme (index.css design tokens)
 * - Fills the 35% column at full height (h-full flex flex-col min-h-0 overflow-hidden)
 * - Transcript history scrolls (overflow-y-auto), nothing else overflows.
 * - Retains full backward compatibility with M4 App.tsx props.
 */

import React, { useId, useMemo, useRef, useState } from 'react'
import type { TurnResponse, Verdict } from '../types/api'
import type { RecordedAudio } from '../services/audioRecorder'

export type ExaminerTurnLike = TurnResponse

export type PanelState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'done'

export interface ExaminerPanelProps {
  // CONTEXT §5.9 contract
  initialTurn?: ExaminerTurnLike | null
  onSubmitAudio?: (audio: RecordedAudio) => Promise<ExaminerTurnLike>
  onSubmitText?: (text: string) => Promise<ExaminerTurnLike>
  onTurn?: (turn: ExaminerTurnLike) => void
  onRequestReport?: () => void
  fillersUrl?: string
  disabled?: boolean

  // Compatibility props with M4 App.tsx
  sessionId?: string | null
  mode?: unknown
  turn?: ExaminerTurnLike | null
  history?: ExaminerTurnLike[]
  busy?: boolean
  onStartViva?: () => void

  // Testing & dev-harness state override
  forceState?: PanelState
}

// Cognitive depth levels per Bloom's ladder
const DEPTH_LEVELS = [
  { level: 1, code: 'L1', name: 'Recall', desc: 'Facts & Definitions' },
  { level: 2, code: 'L2', name: 'Comprehend', desc: 'Semantics & Intent' },
  { level: 3, code: 'L3', name: 'Analyze', desc: 'Trade-offs & Scale' },
  { level: 4, code: 'L4', name: 'Evaluate', desc: 'Mutation & Live Fix' },
] as const

/**
 * 1. Examiner Header with live status pill
 */
function ExaminerHeader({
  state,
  disabled,
}: {
  state: PanelState
  disabled: boolean
}) {
  return (
    <header className="flex shrink-0 items-center justify-between pb-2 border-b border-steel-outline">
      <div className="flex items-center gap-2">
        <span className="font-bold text-signal-white text-sm tracking-tight">
          Viva Examiner
        </span>
        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono text-muted-fog bg-deep-slate border border-steel-outline">
          M3 Voice
        </span>
      </div>

      {/* Status Pill */}
      <div className="flex items-center">
        {disabled ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-deep-slate text-muted-fog border border-steel-outline">
            <span className="h-1.5 w-1.5 rounded-full bg-muted-fog" />
            Disabled
          </span>
        ) : state === 'listening' ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-red-950/90 text-red-300 border border-red-500 animate-pulse">
            <span className="h-2 w-2 rounded-full bg-red-400 animate-ping" />
            Listening…
          </span>
        ) : state === 'thinking' ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-amber-950/80 text-amber-300 border border-amber-500 animate-pulse">
            <span className="h-2 w-2 rounded-full bg-amber-400" />
            Thinking…
          </span>
        ) : state === 'speaking' ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-indigo-950/80 text-indigo-300 border border-indigo-500 animate-pulse">
            <span className="h-2 w-2 rounded-full bg-indigo-400 animate-ping" />
            Speaking…
          </span>
        ) : state === 'done' ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-950/80 text-nuxt-signal border border-nuxt-signal/60">
            <span className="h-1.5 w-1.5 rounded-full bg-nuxt-signal" />
            Complete
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-deep-slate text-pale-frost border border-steel-outline">
            <span className="h-1.5 w-1.5 rounded-full bg-nuxt-signal animate-pulse" />
            Idle
          </span>
        )}
      </div>
    </header>
  )
}

/**
 * 2. Depth Meter (L1 Recall, L2 Comprehension, L3 Analysis, L4 Evaluation)
 * Smooth animated highlighting on cognitive level transition.
 */
function DepthMeter({ currentDepth }: { currentDepth: number }) {
  const activeLevel = Math.max(1, Math.min(4, currentDepth))
  const activeLevelData = DEPTH_LEVELS[activeLevel - 1]

  return (
    <section
      className="shrink-0 flex flex-col gap-1.5 py-1"
      role="meter"
      aria-label="Cognitive depth level"
      aria-valuenow={activeLevel}
      aria-valuemin={1}
      aria-valuemax={4}
      aria-valuetext={`Level ${activeLevel}: ${activeLevelData.name} (${activeLevelData.desc})`}
    >
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-muted-fog font-medium">Cognitive Depth:</span>
        <span className="font-semibold text-signal-white text-xs">
          <strong className="text-nuxt-signal font-mono font-bold">
            {activeLevelData.code}
          </strong>{' '}
          — {activeLevelData.name}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-1.5">
        {DEPTH_LEVELS.map(({ level, code, name }) => {
          const isActive = level === activeLevel
          const isCompleted = level < activeLevel

          return (
            <div key={level} className="flex flex-col gap-1">
              {/* Segment Bar */}
              <div
                className={`h-1.5 rounded-full transition-all duration-300 ease-out ${
                  isActive
                    ? 'bg-nuxt-signal shadow-[0_0_8px_rgba(0,220,130,0.6)]'
                    : isCompleted
                    ? 'bg-nuxt-signal/50'
                    : 'bg-steel-outline'
                }`}
              />

              {/* Segment Label */}
              <div
                className={`text-[10px] text-center truncate transition-colors duration-300 ${
                  isActive
                    ? 'font-bold text-signal-white'
                    : isCompleted
                    ? 'text-pale-frost/80'
                    : 'text-muted-fog/60'
                }`}
                title={`Level ${level}: ${name}`}
              >
                {code} {name}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

/**
 * 3. Voice Orb Placeholder (Stub for B5)
 * Reactive visual styling according to panel state (idle, listening, thinking, speaking, done).
 */
function VoiceOrbPlaceholder({
  state,
  isListeningActive,
}: {
  state: PanelState
  isListeningActive: boolean
}) {
  const effectiveVisual = isListeningActive ? 'listening' : state

  return (
    <div className="shrink-0 flex flex-col items-center justify-center py-2">
      <div className="relative flex h-20 w-20 items-center justify-center">
        {/* Outer Halo / Ring depending on state */}
        <div
          className={`absolute inset-0 rounded-full transition-all duration-500 ease-out ${
            effectiveVisual === 'listening'
              ? 'bg-red-500/20 ring-2 ring-red-500 shadow-[0_0_24px_rgba(239,68,68,0.4)] animate-pulse'
              : effectiveVisual === 'thinking'
              ? 'bg-amber-500/15 ring-2 ring-amber-400 shadow-[0_0_18px_rgba(251,191,36,0.3)] animate-spin [animation-duration:8s]'
              : effectiveVisual === 'speaking'
              ? 'bg-indigo-500/25 ring-2 ring-indigo-400 shadow-[0_0_24px_rgba(129,140,248,0.4)] animate-pulse'
              : effectiveVisual === 'done'
              ? 'bg-emerald-500/20 ring-2 ring-nuxt-signal shadow-[0_0_20px_rgba(0,220,130,0.4)]'
              : 'bg-deep-slate ring-1 ring-steel-outline shadow-inner'
          }`}
        />

        {/* Inner Core */}
        <div
          className={`relative z-10 flex h-14 w-14 items-center justify-center rounded-full border transition-all duration-300 ${
            effectiveVisual === 'listening'
              ? 'bg-red-950 border-red-500 text-red-200'
              : effectiveVisual === 'thinking'
              ? 'bg-amber-950 border-amber-500 text-amber-200'
              : effectiveVisual === 'speaking'
              ? 'bg-indigo-950 border-indigo-400 text-indigo-200'
              : effectiveVisual === 'done'
              ? 'bg-emerald-950 border-nuxt-signal text-nuxt-signal'
              : 'bg-midnight-panel border-steel-outline text-muted-fog'
          }`}
        >
          {effectiveVisual === 'listening' ? (
            <span className="text-xl">🎙️</span>
          ) : effectiveVisual === 'thinking' ? (
            <span className="text-xl">⚙️</span>
          ) : effectiveVisual === 'speaking' ? (
            <span className="text-xl">🔊</span>
          ) : effectiveVisual === 'done' ? (
            <span className="text-xl font-bold">✓</span>
          ) : (
            <span className="text-xs font-mono font-semibold text-pale-frost">
              VOICE
            </span>
          )}
        </div>
      </div>

      {/* Status subtext */}
      <span className="mt-1 text-[11px] text-muted-fog">
        {effectiveVisual === 'listening'
          ? 'Listening to student response…'
          : effectiveVisual === 'thinking'
          ? 'Evaluating response against rubric…'
          : effectiveVisual === 'speaking'
          ? 'Examiner speaking…'
          : effectiveVisual === 'done'
          ? 'Viva complete'
          : 'Hold Space to answer'}
      </span>
    </div>
  )
}

/**
 * Verdict badge with color coding per spec:
 * strong green, partial amber, weak red, no_answer gray
 */
function VerdictBadge({ verdict }: { verdict: Verdict }) {
  switch (verdict) {
    case 'strong':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-600/70">
          Strong
        </span>
      )
    case 'partial':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-950/80 text-amber-300 border border-amber-600/70">
          Partial
        </span>
      )
    case 'weak':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-red-950/80 text-red-300 border border-red-600/70">
          Weak
        </span>
      )
    case 'no_answer':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-deep-slate text-muted-fog border border-steel-outline">
          No Answer
        </span>
      )
    case 'start':
    default:
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-deep-slate text-pale-frost border border-steel-outline">
          Start
        </span>
      )
  }
}

/**
 * 4. QuestionCard
 * Topic chip, depth chip, muted ack_text, bold large question_text, aria-live='polite'
 */
function QuestionCard({
  turn,
  onStartViva,
  busy,
  disabled,
}: {
  turn: ExaminerTurnLike | null
  onStartViva?: () => void
  busy: boolean
  disabled: boolean
}) {
  if (!turn) {
    if (onStartViva) {
      return (
        <div className="panel shrink-0 p-4 bg-midnight-panel border border-steel-outline rounded-lg flex flex-col items-center justify-center text-center gap-2.5">
          <p className="text-xs text-muted-fog">
            Workspace ready. Begin your technical viva examination.
          </p>
          <button
            type="button"
            onClick={onStartViva}
            disabled={busy || disabled}
            className="rounded-md bg-nuxt-signal px-4 py-1.5 text-xs font-semibold text-void-canvas hover:opacity-90 disabled:opacity-40 transition active:scale-95"
          >
            Start Viva (Question 1)
          </button>
        </div>
      )
    }

    return (
      <div className="panel shrink-0 p-4 bg-midnight-panel border border-steel-outline rounded-lg text-center text-xs text-muted-fog">
        No active question. Mount initialTurn or start viva.
      </div>
    )
  }

  return (
    <article
      className="panel shrink-0 p-3 bg-midnight-panel border border-steel-outline rounded-lg flex flex-col gap-2"
      aria-label="Current examiner question"
    >
      {/* Chips Header */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-deep-slate text-nuxt-signal border border-steel-outline truncate max-w-[200px]">
          {turn.topic}
        </span>
        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-steel-outline text-signal-white">
          L{turn.depth_level}
        </span>
        <span className="ml-auto">
          <VerdictBadge verdict={turn.verdict} />
        </span>
      </div>

      {/* Muted ack_text */}
      {turn.ack_text && (
        <p className="text-xs text-muted-fog italic border-l-2 border-nuxt-signal/50 pl-2.5 py-0.5 bg-void-canvas/30 rounded-r">
          "{turn.ack_text}"
        </p>
      )}

      {/* Bold Large question_text with aria-live="polite" */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="font-semibold text-sm sm:text-base text-signal-white leading-relaxed"
      >
        {turn.question_text}
      </div>

      {/* Extra grounding highlight pill if present */}
      {turn.highlight && (
        <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-fog bg-void-canvas/80 px-2 py-1 rounded border border-steel-outline/80 mt-0.5">
          <span className="text-nuxt-signal">📍</span>
          <span className="truncate">
            {turn.highlight.file_path}: Lines {turn.highlight.line_start}–
            {turn.highlight.line_end}
          </span>
        </div>
      )}
    </article>
  )
}

/**
 * 5. Done State Card
 * 'Viva complete' + 'View report' button -> onRequestReport
 */
function DoneCard({ onRequestReport }: { onRequestReport?: () => void }) {
  return (
    <article
      className="panel shrink-0 p-4 bg-midnight-panel border border-nuxt-signal/50 rounded-lg flex flex-col gap-2.5 text-center shadow-[0_0_16px_rgba(0,220,130,0.15)]"
      aria-label="Viva completion status"
    >
      <div className="flex items-center justify-center gap-2">
        <span className="text-xl text-nuxt-signal">🎉</span>
        <h3 className="font-bold text-signal-white text-base tracking-tight">
          Viva complete
        </h3>
      </div>
      <p className="text-xs text-muted-fog leading-relaxed">
        All cognitive depth levels have been evaluated. Accent and grammar
        received 0% weight.
      </p>

      {onRequestReport && (
        <button
          type="button"
          onClick={onRequestReport}
          className="mt-1 w-full py-2 px-3 rounded-md bg-nuxt-signal text-void-canvas font-bold text-xs hover:bg-vue-link active:scale-[0.98] transition shadow"
        >
          View report
        </button>
      )}
    </article>
  )
}

/**
 * 6. Collapsible TranscriptHistory
 * Question + student transcript + verdict badge
 */
function TranscriptHistory({
  history,
}: {
  history: ExaminerTurnLike[]
}) {
  const [isExpanded, setIsExpanded] = useState(true)

  if (history.length === 0) {
    return null
  }

  return (
    <section
      className="flex flex-1 min-h-0 flex-col overflow-hidden pt-1"
      aria-label="Transcript history"
    >
      {/* Accordion Toggle Header */}
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="flex shrink-0 w-full items-center justify-between py-1.5 px-2 rounded bg-deep-slate/70 hover:bg-deep-slate border border-steel-outline text-xs font-semibold text-pale-frost transition select-none"
        aria-expanded={isExpanded}
      >
        <span className="flex items-center gap-1.5">
          <span>📜</span>
          <span>Transcript History ({history.length})</span>
        </span>
        <span className="text-[10px] text-muted-fog font-mono">
          {isExpanded ? 'Hide ▲' : 'Show ▼'}
        </span>
      </button>

      {/* Scrollable Transcript List */}
      {isExpanded && (
        <div
          tabIndex={0}
          aria-label="Scrollable transcript history"
          className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1 pt-2 focus:outline-none focus:ring-1 focus:ring-steel-outline rounded"
        >
          {history.map((item, idx) => (
            <div
              key={`${item.session_id}-${idx}`}
              className="rounded bg-deep-slate/50 p-2.5 border border-steel-outline/80 text-xs flex flex-col gap-1.5"
            >
              {/* Item Header */}
              <div className="flex items-center justify-between gap-1 text-[11px]">
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-muted-fog font-semibold">
                    #{idx + 1}
                  </span>
                  <span className="px-1 py-0.5 rounded text-[10px] font-mono font-bold bg-steel-outline text-signal-white">
                    L{item.depth_level}
                  </span>
                  <span className="text-muted-fog truncate max-w-[140px]">
                    {item.topic}
                  </span>
                </div>
                <VerdictBadge verdict={item.verdict} />
              </div>

              {/* Question Text */}
              <p className="text-signal-white text-[11px] leading-relaxed">
                <span className="text-muted-fog font-mono font-semibold">
                  Q:{' '}
                </span>
                {item.question_text}
              </p>

              {/* Student Transcript */}
              {item.student_transcript ? (
                <p className="text-pale-frost text-[11px] leading-relaxed bg-void-canvas/50 p-1.5 rounded border border-steel-outline/50">
                  <span className="text-nuxt-signal font-mono font-semibold">
                    A:{' '}
                  </span>
                  "{item.student_transcript}"
                </p>
              ) : (
                <p className="text-muted-fog/60 italic text-[10px] pl-1">
                  (No spoken answer recorded)
                </p>
              )}

              {/* Ack text if present */}
              {item.ack_text && (
                <p className="text-muted-fog text-[10px] italic border-l border-steel-outline pl-1.5 mt-0.5">
                  Ack: {item.ack_text}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

/**
 * 7. PushToTalkButton
 * Press-and-hold with mouse / touch, label 'Hold Space to answer'
 */
function PushToTalkButton({
  isPressed,
  onPressStart,
  onPressEnd,
  disabled,
}: {
  isPressed: boolean
  onPressStart: () => void
  onPressEnd: () => void
  disabled: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onPointerDown={(e) => {
        e.preventDefault()
        if (!disabled) onPressStart()
      }}
      onPointerUp={(e) => {
        e.preventDefault()
        if (!disabled) onPressEnd()
      }}
      onPointerLeave={() => {
        if (isPressed) onPressEnd()
      }}
      className={`shrink-0 flex items-center justify-center gap-2 rounded-md py-2.5 px-3 text-xs font-semibold border transition select-none ${
        disabled
          ? 'opacity-40 cursor-not-allowed bg-deep-slate border-steel-outline text-muted-fog'
          : isPressed
          ? 'bg-red-600 text-white border-red-500 shadow-[0_0_16px_rgba(239,68,68,0.5)] scale-[0.99]'
          : 'bg-deep-slate text-pale-frost border-steel-outline hover:bg-steel-outline hover:text-signal-white active:bg-nuxt-signal active:text-void-canvas'
      }`}
    >
      <span className="text-sm">{isPressed ? '🔴' : '🎙️'}</span>
      <span>{isPressed ? 'Listening… Release to answer' : 'Hold Space to answer'}</span>
    </button>
  )
}

/**
 * 8. TextFallbackInput
 * Enter submits, Shift+Enter newline
 */
function TextFallbackInput({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string
  onChange: (val: string) => void
  onSubmit: () => void
  disabled: boolean
}) {
  const textareaId = useId()
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() && !disabled) {
        onSubmit()
      }
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (value.trim() && !disabled) onSubmit()
      }}
      className="shrink-0 flex gap-1.5 items-end"
    >
      <label htmlFor={textareaId} className="sr-only">
        Technical answer input
      </label>
      <textarea
        id={textareaId}
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Type answer (Enter to send, Shift+Enter newline)…"
        className="min-w-0 flex-1 resize-none rounded bg-void-canvas px-3 py-1.5 text-xs text-pale-frost border border-steel-outline placeholder:text-blue-steel focus:outline-none focus:border-nuxt-signal disabled:opacity-40 leading-normal max-h-20"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded px-3 py-1.5 text-xs font-semibold bg-deep-slate border border-steel-outline text-pale-frost hover:bg-steel-outline hover:text-signal-white disabled:opacity-40 transition active:scale-95"
      >
        Send
      </button>
    </form>
  )
}

/**
 * Main ExaminerPanel Component
 */
export default function ExaminerPanel({
  initialTurn,
  onSubmitAudio,
  onSubmitText,
  onTurn,
  onRequestReport,
  fillersUrl = '/api/voice/fillers',
  disabled = false,
  sessionId,
  mode,
  turn,
  history = [],
  busy = false,
  onStartViva,
  forceState,
}: ExaminerPanelProps) {
  // Active turn: supports both initialTurn (M3 harness) and turn (M4 App.tsx)
  const activeTurn = initialTurn ?? turn ?? null

  // Push-to-talk button press tracking
  const [isPressed, setIsPressed] = useState(false)
  const [typedInput, setTypedInput] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Compute effective panel state
  const panelState: PanelState = useMemo(() => {
    if (forceState) return forceState
    if (disabled) return 'idle'
    if (activeTurn?.done) return 'done'
    if (busy || isSubmitting) return 'thinking'
    if (isPressed) return 'listening'
    return 'idle'
  }, [forceState, disabled, activeTurn?.done, busy, isSubmitting, isPressed])

  const currentDepth = activeTurn?.depth_level ?? 1

  // Aggregate transcript history: use prop history if populated; fallback to activeTurn
  const historyList = useMemo(() => {
    if (history && history.length > 0) {
      return history
    }
    if (activeTurn) {
      return [activeTurn]
    }
    return []
  }, [history, activeTurn])

  // Text submit handler
  const handleTextSubmit = async () => {
    const text = typedInput.trim()
    if (!text || isSubmitting || disabled || busy || panelState === 'done') return

    setIsSubmitting(true)
    try {
      if (onSubmitText) {
        const nextTurn = await onSubmitText(text)
        onTurn?.(nextTurn)
      }
      setTypedInput('')
    } catch {
      // B6 adds inline error + Retry; keep typed text so nothing is lost
    } finally {
      setIsSubmitting(false)
    }
  }

  // Push to talk handlers for mouse/touch
  const handlePressStart = () => {
    if (disabled || busy || panelState === 'done') return
    setIsPressed(true)
  }

  const handlePressEnd = () => {
    if (!isPressed) return
    setIsPressed(false)
  }

  const isInputDisabled = disabled || busy || isSubmitting || panelState === 'done'

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-2 p-3 bg-midnight-panel text-pale-frost select-none overflow-hidden font-sans">
      {/* 1. Header (title + status pill) */}
      <ExaminerHeader state={panelState} disabled={disabled} />

      {/* 2. Depth Meter (L1..L4) */}
      <DepthMeter currentDepth={currentDepth} />

      {/* 3. Voice Orb Placeholder */}
      <VoiceOrbPlaceholder
        state={panelState}
        isListeningActive={isPressed}
      />

      {/* 4. QuestionCard OR DoneCard */}
      {panelState === 'done' || activeTurn?.done ? (
        <DoneCard onRequestReport={onRequestReport} />
      ) : (
        <QuestionCard
          turn={activeTurn}
          onStartViva={onStartViva}
          busy={busy}
          disabled={disabled}
        />
      )}

      {/* 5. Transcript History (Collapsible, SCROLLS!) */}
      <TranscriptHistory history={historyList} />

      {/* 6. Push-to-Talk Button & Text Fallback Input */}
      <div className="shrink-0 flex flex-col gap-1.5 pt-2 border-t border-steel-outline">
        <PushToTalkButton
          isPressed={isPressed}
          onPressStart={handlePressStart}
          onPressEnd={handlePressEnd}
          disabled={isInputDisabled}
        />

        <TextFallbackInput
          value={typedInput}
          onChange={setTypedInput}
          onSubmit={handleTextSubmit}
          disabled={isInputDisabled}
        />
      </div>
    </div>
  )
}
