/**
 * M3 Voice Pipeline — ExaminerPanel Component (Stub for Task B1)
 *
 * Implements the exact public interface from CONTEXT §5.9:
 * - ExaminerTurnLike (aliased to TurnResponse from types/api.ts)
 * - ExaminerPanelProps
 * - default export ExaminerPanel
 *
 * Full UI layout, orb animation, recorder hooks, and turn flow
 * will be incrementally implemented in B2 through B6.
 */

import React, { useState } from 'react'
import type { TurnResponse } from '../types/api'
import type { RecordedAudio } from '../services/audioRecorder'

export type ExaminerTurnLike = TurnResponse

export interface ExaminerPanelProps {
  initialTurn?: ExaminerTurnLike | null
  onSubmitAudio?: (audio: RecordedAudio) => Promise<ExaminerTurnLike>
  onSubmitText?: (text: string) => Promise<ExaminerTurnLike>
  onTurn?: (turn: ExaminerTurnLike) => void
  onRequestReport?: () => void
  fillersUrl?: string
  disabled?: boolean

  // Compatibility props with M4's App.tsx until integration
  sessionId?: string | null
  mode?: unknown
  turn?: ExaminerTurnLike | null
  history?: ExaminerTurnLike[]
  busy?: boolean
  onStartViva?: () => void
}

const DEPTH_LEVELS = [
  { level: 1, name: 'Recall' },
  { level: 2, name: 'Comprehend' },
  { level: 3, name: 'Analyze' },
  { level: 4, name: 'Evaluate' },
]

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
}: ExaminerPanelProps) {
  // Use either initialTurn (M3 harness) or turn (M4 App.tsx)
  const activeTurn = initialTurn ?? turn ?? null
  const [typedInput, setTypedInput] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const text = typedInput.trim()
    if (!text || isSubmitting || disabled || busy) return

    setIsSubmitting(true)
    try {
      if (onSubmitText) {
        const nextTurn = await onSubmitText(text)
        onTurn?.(nextTurn)
      }
      setTypedInput('')
    } finally {
      setIsSubmitting(false)
    }
  }

  const currentDepth = activeTurn?.depth_level ?? 1

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4 bg-midnight-panel text-pale-frost select-none">
      {/* 1. Header & Status Pill */}
      <div className="flex items-center justify-between pb-2 border-b border-steel-outline">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-signal-white text-sm">Examiner</span>
          <span className="text-xs text-muted-fog">M3 Voice Pipeline</span>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-deep-slate border border-steel-outline text-xs text-nuxt-signal">
          <span className="h-2 w-2 rounded-full bg-nuxt-signal animate-pulse" />
          <span>{disabled ? 'Disabled' : busy || isSubmitting ? 'Thinking…' : 'Idle'}</span>
        </div>
      </div>

      {/* 2. Depth Meter (L1..L4) */}
      <div
        className="grid grid-cols-4 gap-1.5"
        role="meter"
        aria-label="Cognitive depth"
        aria-valuenow={currentDepth}
      >
        {DEPTH_LEVELS.map(({ level, name }) => (
          <div key={level}>
            <div
              className={`h-1.5 rounded-full transition-all duration-300 ${
                level <= currentDepth ? 'bg-nuxt-signal' : 'bg-steel-outline'
              }`}
            />
            <div
              className={`mt-1 text-[11px] ${
                level === currentDepth
                  ? 'font-semibold text-signal-white'
                  : 'text-muted-fog'
              }`}
            >
              L{level} {name}
            </div>
          </div>
        ))}
      </div>

      {/* 3. Voice Orb Placeholder (Stub for B5) */}
      <div className="flex shrink-0 flex-col items-center justify-center py-3">
        <div className="relative flex h-24 w-24 items-center justify-center rounded-full ring-1 ring-steel-outline bg-deep-slate shadow-inner">
          <div className="h-14 w-14 rounded-full bg-blue-steel flex items-center justify-center text-xs text-signal-white font-mono border border-steel-outline">
            Orb
          </div>
        </div>
        <span className="mt-2 text-xs text-muted-fog">
          Hold Space to speak (B2 push-to-talk)
        </span>
      </div>

      {/* 4. Question Card (Stub for B4) */}
      <div className="panel min-h-0 flex-1 overflow-auto p-4 flex flex-col justify-between">
        {activeTurn ? (
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-nuxt-signal">
              <span className="px-1.5 py-0.5 rounded bg-deep-slate border border-steel-outline">
                L{activeTurn.depth_level}
              </span>
              <span className="text-muted-fog">{activeTurn.topic}</span>
              <span className="ml-auto text-[10px] uppercase tracking-wider text-muted-fog px-1.5 py-0.5 rounded bg-deep-slate">
                {activeTurn.verdict}
              </span>
            </div>

            {activeTurn.ack_text && (
              <p className="mt-2 text-xs text-muted-fog italic border-l-2 border-steel-outline pl-2">
                "{activeTurn.ack_text}"
              </p>
            )}

            <p className="mt-3 text-base font-medium leading-relaxed text-signal-white">
              {activeTurn.question_text}
            </p>

            {activeTurn.done && (
              <div className="mt-4 p-3 rounded bg-deep-slate border border-nuxt-signal/40 text-xs text-signal-white">
                <span className="font-semibold text-nuxt-signal">Viva Complete!</span>{' '}
                All questions answered.
                {onRequestReport && (
                  <button
                    type="button"
                    onClick={onRequestReport}
                    className="mt-2 block w-full py-1 text-center bg-nuxt-signal text-void-canvas font-semibold rounded text-xs hover:opacity-90 transition"
                  >
                    View Viva Report
                  </button>
                )}
              </div>
            )}
          </div>
        ) : onStartViva ? (
          <div className="flex h-full flex-col items-center justify-center text-center gap-3">
            <p className="text-xs text-muted-fog">
              Workspace ready. Begin your technical viva.
            </p>
            <button
              type="button"
              onClick={onStartViva}
              disabled={busy || disabled}
              className="rounded-md bg-nuxt-signal px-3.5 py-1.5 text-xs font-semibold text-void-canvas hover:opacity-90 disabled:opacity-40"
            >
              Start Viva (Question 1)
            </button>
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-center text-xs text-muted-fog">
            No active question. Mount initialTurn or start viva.
          </div>
        )}

        {/* Collapsible Transcript History count */}
        {history.length > 0 && (
          <div className="mt-3 pt-2 border-t border-steel-outline text-xs text-muted-fog">
            Transcript: {history.length} turn{history.length > 1 ? 's' : ''} in history
          </div>
        )}
      </div>

      {/* 5. Push-to-Talk Button & Text Fallback (Stub for B2/B4) */}
      <div className="flex shrink-0 flex-col gap-2 pt-2 border-t border-steel-outline">
        <button
          type="button"
          disabled={disabled || busy || isSubmitting}
          className="flex items-center justify-center gap-2 rounded-md py-2 px-3 text-sm font-medium bg-deep-slate ring-1 ring-blue-steel text-pale-frost hover:bg-steel-outline disabled:opacity-40 transition"
        >
          <span>🎙️</span>
          <span>Hold Space to answer (B2 Stub)</span>
        </button>

        <form onSubmit={handleTextSubmit} className="flex gap-1.5">
          <input
            type="text"
            value={typedInput}
            onChange={(e) => setTypedInput(e.target.value)}
            disabled={disabled || busy || isSubmitting}
            placeholder="Or type technical answer (Enter to send)..."
            className="min-w-0 flex-1 rounded bg-void-canvas px-3 py-1.5 text-xs text-pale-frost ring-1 ring-steel-outline placeholder:text-blue-steel focus:outline-none"
          />
          <button
            type="submit"
            disabled={disabled || busy || isSubmitting || !typedInput.trim()}
            className="rounded px-3 py-1.5 text-xs font-semibold bg-deep-slate ring-1 ring-blue-steel text-pale-frost hover:bg-steel-outline disabled:opacity-40"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  )
}
