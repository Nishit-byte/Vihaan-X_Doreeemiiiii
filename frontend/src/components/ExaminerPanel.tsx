/**
 * M3 Voice Pipeline — ExaminerPanel Component (Task B6)
 *
 * Implements the complete autonomous viva voice and text turn-flow:
 * 1. initialTurn spoken once on mount (after unlockAudio, guarded against React 18 StrictMode double-speak)
 * 2. idle -> Push-to-Talk (Space or hold button) = listening -> release = thinking
 * 3. thinking: plays random filler audio instantly (fetched from fillersUrl, failed fetches ignored silently)
 *    and calls onSubmitAudio / onSubmitText
 * 4. on response: stops filler, appends to transcript history, calls onTurn once, speaks audio_base64
 *    (or browser TTS fallback if empty) = speaking, with word-by-word karaoke highlighting of ack + question
 *    synced to AudioPlayback.getProgress() -> returns to idle
 * 5. Barge-in: Space while speaking immediately halts playback and transitions to listening
 * 6. Cancellation: Esc cancels recording and ignores in-flight requests (requestIdRef)
 * 7. Error handling:
 *    - submission rejects -> inline error banner + 'Retry' resending the exact same recording or text
 *    - empty student_transcript or verdict no_answer -> "Didn't catch that — try again or type"
 *    - mic denied -> status badge and text fallback input becomes primary
 * 8. Done state: done=true displays DoneCard ('Viva complete' + 'View report')
 * 9. Live levelSource feeds recorder.getInputLevel() during listening, active playback.getLevel() during speaking, 0 otherwise
 * 10. select-none scoped strictly to buttons; question and transcript text remain fully selectable
 */

import React, { useCallback, useEffect, useId, useRef, useState } from 'react'
import type { TurnResponse, Verdict } from '../types/api'
import { submitTurn } from '../services/apiClient'
import { triggerFullscreen } from '../utils/fullscreen'
import {
  RecordedAudio,
  RecorderStatus,
  AudioPlayback,
  usePushToTalkRecorder,
  playBase64Audio,
  speakWithBrowserTTS,
  stopAllPlayback,
  unlockAudio,
} from '../services/audioRecorder'

export type ExaminerTurnLike = TurnResponse

export type PanelState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'done'

export interface VoiceOrbProps {
  state: PanelState
  levelSource?: () => number
  size?: number
  className?: string
}

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

  // Testing & dev-harness overrides
  forceState?: PanelState
  levelSource?: () => number
}

// Cognitive depth levels per Bloom's ladder
const DEPTH_LEVELS = [
  { level: 1, code: 'L1', name: 'Recall', desc: 'Facts & Definitions' },
  { level: 2, code: 'L2', name: 'Comprehend', desc: 'Semantics & Intent' },
  { level: 3, code: 'L3', name: 'Analyze', desc: 'Trade-offs & Scale' },
  { level: 4, code: 'L4', name: 'Evaluate', desc: 'Mutation & Live Fix' },
] as const

/**
 * Builds spoken text combining ack_text and question_text per CONTEXT §5.2
 */
export function buildSpokenText(
  ackText?: string | null,
  questionText?: string | null
): string {
  const ack = (ackText || '').trim()
  const q = (questionText || '').trim()
  if (!ack) return q
  if (!q) return ack
  const endsWithPunct = /[.!?]$/.test(ack)
  return `${ack}${endsWithPunct ? '' : '.'} ${q}`
}

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
    <header className="flex shrink-0 items-center justify-between pb-2 border-b border-steel-outline select-none">
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
 */
function DepthMeter({ currentDepth }: { currentDepth: number }) {
  const activeLevel = Math.max(1, Math.min(4, currentDepth))
  const activeLevelData = DEPTH_LEVELS[activeLevel - 1]

  return (
    <section
      className="shrink-0 flex flex-col gap-1.5 py-1 select-none"
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
              <div
                className={`h-1.5 rounded-full transition-all duration-300 ease-out ${
                  isActive
                    ? 'bg-nuxt-signal shadow-[0_0_8px_rgba(0,220,130,0.6)]'
                    : isCompleted
                    ? 'bg-nuxt-signal/50'
                    : 'bg-steel-outline'
                }`}
              />
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
 * 3. VoiceOrb (Task B5) Canvas Drawing Helpers
 */
function drawIdleOrb(
  ctx: CanvasRenderingContext2D,
  time: number,
  cx: number,
  cy: number,
  baseRadius: number,
  _size: number
) {
  const breath = Math.sin(time * 0.0018) * 0.06
  const r = baseRadius * (1 + breath)

  const halo = ctx.createRadialGradient(cx, cy, r * 0.6, cx, cy, r * 1.55)
  halo.addColorStop(0, 'rgba(99, 102, 241, 0.22)')
  halo.addColorStop(0.5, 'rgba(71, 85, 105, 0.12)')
  halo.addColorStop(1, 'rgba(15, 23, 42, 0)')
  ctx.fillStyle = halo
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.55, 0, Math.PI * 2)
  ctx.fill()

  ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.35, 0, Math.PI * 2)
  ctx.stroke()

  const core = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#6366f1')
  core.addColorStop(0.45, '#3730a3')
  core.addColorStop(1, '#0f172a')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  ctx.strokeStyle = 'rgba(129, 140, 248, 0.5)'
  ctx.lineWidth = 1.5
  ctx.stroke()

  ctx.beginPath()
  ctx.arc(cx - r * 0.28, cy - r * 0.28, r * 0.22, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.14)'
  ctx.fill()
}

function drawListeningOrb(
  ctx: CanvasRenderingContext2D,
  smoothedLevel: number,
  scale: number,
  cx: number,
  cy: number,
  baseRadius: number,
  size: number
) {
  const r = baseRadius * scale
  const maxR = size / 2 - 3

  const wave1 = Math.min(maxR, baseRadius * (scale + 0.22 + smoothedLevel * 0.25))
  const a1 = Math.min(0.85, 0.25 + smoothedLevel * 0.55)
  ctx.strokeStyle = `rgba(0, 220, 130, ${a1})`
  ctx.lineWidth = 1.8 + smoothedLevel * 1.5
  ctx.beginPath()
  ctx.arc(cx, cy, wave1, 0, Math.PI * 2)
  ctx.stroke()

  if (smoothedLevel > 0.05) {
    const wave2 = Math.min(maxR, baseRadius * (scale + 0.48 + smoothedLevel * 0.3))
    const a2 = Math.min(0.6, 0.1 + smoothedLevel * 0.35)
    ctx.strokeStyle = `rgba(0, 220, 130, ${a2})`
    ctx.lineWidth = 1.2
    ctx.beginPath()
    ctx.arc(cx, cy, wave2, 0, Math.PI * 2)
    ctx.stroke()
  }

  const glow = ctx.createRadialGradient(cx, cy, r * 0.5, cx, cy, Math.min(maxR, r * 1.6))
  glow.addColorStop(0, `rgba(0, 220, 130, ${0.35 + smoothedLevel * 0.4})`)
  glow.addColorStop(0.7, `rgba(5, 150, 105, ${0.15 + smoothedLevel * 0.2})`)
  glow.addColorStop(1, 'rgba(6, 78, 59, 0)')
  ctx.fillStyle = glow
  ctx.beginPath()
  ctx.arc(cx, cy, Math.min(maxR, r * 1.6), 0, Math.PI * 2)
  ctx.fill()

  const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#34d399')
  core.addColorStop(0.5, '#059669')
  core.addColorStop(1, '#064e3b')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  ctx.strokeStyle = `rgba(52, 211, 153, ${0.7 + smoothedLevel * 0.3})`
  ctx.lineWidth = 2 + smoothedLevel * 1.5
  ctx.stroke()

  ctx.beginPath()
  ctx.arc(cx - r * 0.28, cy - r * 0.28, r * 0.22, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.22)'
  ctx.fill()
}

function drawThinkingOrb(
  ctx: CanvasRenderingContext2D,
  time: number,
  cx: number,
  cy: number,
  baseRadius: number,
  _size: number
) {
  const angle = (time * 0.0024) % (Math.PI * 2)
  const ring1R = baseRadius * 1.38

  ctx.save()
  ctx.translate(cx, cy)
  ctx.rotate(angle)
  ctx.setLineDash([8, 6])
  ctx.strokeStyle = '#f59e0b'
  ctx.lineWidth = 2.4
  ctx.beginPath()
  ctx.arc(0, 0, ring1R, 0, Math.PI * 2)
  ctx.stroke()
  ctx.restore()

  const ring2R = baseRadius * 1.18
  ctx.save()
  ctx.translate(cx, cy)
  ctx.rotate(-angle * 0.65)
  ctx.setLineDash([4, 6])
  ctx.strokeStyle = 'rgba(251, 191, 36, 0.45)'
  ctx.lineWidth = 1.4
  ctx.beginPath()
  ctx.arc(0, 0, ring2R, 0, Math.PI * 2)
  ctx.stroke()
  ctx.restore()

  const pulse = Math.sin(time * 0.004) * 0.035
  const r = baseRadius * (1 + pulse)

  const glow = ctx.createRadialGradient(cx, cy, r * 0.5, cx, cy, r * 1.5)
  glow.addColorStop(0, 'rgba(245, 158, 11, 0.28)')
  glow.addColorStop(0.6, 'rgba(217, 119, 6, 0.12)')
  glow.addColorStop(1, 'rgba(120, 53, 15, 0)')
  ctx.fillStyle = glow
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.5, 0, Math.PI * 2)
  ctx.fill()

  const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#fbbf24')
  core.addColorStop(0.5, '#d97706')
  core.addColorStop(1, '#78350f')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  ctx.strokeStyle = 'rgba(251, 191, 36, 0.85)'
  ctx.lineWidth = 1.8
  ctx.stroke()

  ctx.beginPath()
  ctx.arc(cx - r * 0.28, cy - r * 0.28, r * 0.22, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.18)'
  ctx.fill()
}

function drawSpeakingOrb(
  ctx: CanvasRenderingContext2D,
  time: number,
  smoothedLevel: number,
  scale: number,
  cx: number,
  cy: number,
  baseRadius: number,
  size: number
) {
  const r = baseRadius * scale
  const maxR = size / 2 - 3

  for (let w = 0; w < 3; w++) {
    const phase = (time * 0.0016 + w * 0.333) % 1.0
    const maxExpansion = maxR - r
    const rippleR = r + phase * maxExpansion
    const alpha = (1 - phase) * (0.35 + smoothedLevel * 0.55)
    ctx.strokeStyle = `rgba(139, 92, 246, ${Math.max(0, Math.min(1, alpha))})`
    ctx.lineWidth = 1.5 + smoothedLevel * 1.5
    ctx.beginPath()
    ctx.arc(cx, cy, rippleR, 0, Math.PI * 2)
    ctx.stroke()
  }

  const glow = ctx.createRadialGradient(cx, cy, r * 0.5, cx, cy, Math.min(maxR, r * 1.6))
  glow.addColorStop(0, `rgba(168, 85, 247, ${0.35 + smoothedLevel * 0.45})`)
  glow.addColorStop(0.5, `rgba(99, 102, 241, ${0.2 + smoothedLevel * 0.3})`)
  glow.addColorStop(1, 'rgba(49, 46, 129, 0)')
  ctx.fillStyle = glow
  ctx.beginPath()
  ctx.arc(cx, cy, Math.min(maxR, r * 1.6), 0, Math.PI * 2)
  ctx.fill()

  const core = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#c084fc')
  core.addColorStop(0.4, '#818cf8')
  core.addColorStop(0.8, '#4f46e5')
  core.addColorStop(1, '#312e81')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  ctx.strokeStyle = `rgba(192, 132, 252, ${0.75 + smoothedLevel * 0.25})`
  ctx.lineWidth = 2 + smoothedLevel * 1.5
  ctx.stroke()

  ctx.beginPath()
  ctx.arc(cx - r * 0.28, cy - r * 0.28, r * 0.22, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.22)'
  ctx.fill()
}

function drawDoneOrb(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  baseRadius: number,
  _size: number
) {
  const r = baseRadius

  const halo = ctx.createRadialGradient(cx, cy, r * 0.6, cx, cy, r * 1.35)
  halo.addColorStop(0, 'rgba(0, 220, 130, 0.25)')
  halo.addColorStop(0.6, 'rgba(5, 150, 105, 0.1)')
  halo.addColorStop(1, 'rgba(6, 78, 59, 0)')
  ctx.fillStyle = halo
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.35, 0, Math.PI * 2)
  ctx.fill()

  ctx.strokeStyle = 'rgba(0, 220, 130, 0.4)'
  ctx.lineWidth = 1.2
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.22, 0, Math.PI * 2)
  ctx.stroke()

  const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#34d399')
  core.addColorStop(0.5, '#059669')
  core.addColorStop(1, '#064e3b')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  ctx.strokeStyle = 'rgba(0, 220, 130, 0.8)'
  ctx.lineWidth = 2
  ctx.stroke()

  ctx.beginPath()
  ctx.moveTo(cx - r * 0.25, cy + r * 0.02)
  ctx.lineTo(cx - r * 0.04, cy + r * 0.23)
  ctx.lineTo(cx + r * 0.29, cy - r * 0.19)
  ctx.strokeStyle = '#ffffff'
  ctx.lineWidth = 2.4
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.stroke()
}

function drawStaticOrb(
  ctx: CanvasRenderingContext2D,
  state: PanelState,
  cx: number,
  cy: number,
  baseRadius: number,
  size: number
) {
  const r = baseRadius

  switch (state) {
    case 'listening': {
      const ring = baseRadius * 1.25
      ctx.strokeStyle = 'rgba(0, 220, 130, 0.4)'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(cx, cy, ring, 0, Math.PI * 2)
      ctx.stroke()

      const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 0.1, cx, cy, r)
      core.addColorStop(0, '#34d399')
      core.addColorStop(0.5, '#059669')
      core.addColorStop(1, '#064e3b')
      ctx.fillStyle = core
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fill()

      ctx.strokeStyle = 'rgba(52, 211, 153, 0.8)'
      ctx.lineWidth = 2
      ctx.stroke()
      break
    }
    case 'thinking': {
      ctx.save()
      ctx.setLineDash([8, 6])
      ctx.strokeStyle = '#f59e0b'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(cx, cy, baseRadius * 1.35, 0, Math.PI * 2)
      ctx.stroke()
      ctx.restore()

      const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 0.1, cx, cy, r)
      core.addColorStop(0, '#fbbf24')
      core.addColorStop(0.5, '#d97706')
      core.addColorStop(1, '#78350f')
      ctx.fillStyle = core
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fill()

      ctx.strokeStyle = 'rgba(251, 191, 36, 0.85)'
      ctx.lineWidth = 2
      ctx.stroke()
      break
    }
    case 'speaking': {
      ctx.strokeStyle = 'rgba(139, 92, 246, 0.4)'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(cx, cy, baseRadius * 1.28, 0, Math.PI * 2)
      ctx.stroke()

      const core = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 0.1, cx, cy, r)
      core.addColorStop(0, '#c084fc')
      core.addColorStop(0.4, '#818cf8')
      core.addColorStop(0.8, '#4f46e5')
      core.addColorStop(1, '#312e81')
      ctx.fillStyle = core
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fill()

      ctx.strokeStyle = 'rgba(192, 132, 252, 0.8)'
      ctx.lineWidth = 2
      ctx.stroke()
      break
    }
    case 'done': {
      drawDoneOrb(ctx, cx, cy, baseRadius, size)
      break
    }
    case 'idle':
    default: {
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.3)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.arc(cx, cy, r * 1.25, 0, Math.PI * 2)
      ctx.stroke()

      const core = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 0.1, cx, cy, r)
      core.addColorStop(0, '#6366f1')
      core.addColorStop(0.45, '#3730a3')
      core.addColorStop(1, '#0f172a')
      ctx.fillStyle = core
      ctx.beginPath()
      ctx.arc(cx, cy, r, 0, Math.PI * 2)
      ctx.fill()

      ctx.strokeStyle = 'rgba(129, 140, 248, 0.5)'
      ctx.lineWidth = 1.5
      ctx.stroke()
      break
    }
  }
}

export function VoiceOrb({
  state,
  levelSource,
  size = 120,
  className = '',
}: VoiceOrbProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const stateRef = useRef(state)
  stateRef.current = state
  const levelSourceRef = useRef(levelSource)
  levelSourceRef.current = levelSource

  const [isReducedMotion, setIsReducedMotion] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    const handleChange = (e: MediaQueryListEvent) => {
      setIsReducedMotion(e.matches)
    }
    mediaQuery.addEventListener('change', handleChange)
    return () => {
      mediaQuery.removeEventListener('change', handleChange)
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1
    canvas.width = Math.round(size * dpr)
    canvas.height = Math.round(size * dpr)
    canvas.style.width = `${size}px`
    canvas.style.height = `${size}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number
    let smoothedLevel = 0

    const drawFrame = (time: number) => {
      ctx.save()
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, size, size)

      const currentState = stateRef.current
      const rawLevel = levelSourceRef.current ? levelSourceRef.current() : 0
      const targetLevel = Math.max(0, Math.min(1, isNaN(rawLevel) ? 0 : rawLevel))

      smoothedLevel += (targetLevel - smoothedLevel) * 0.18
      const scale = 1 + smoothedLevel * 0.35

      const cx = size / 2
      const cy = size / 2
      const baseRadius = size * 0.26

      if (isReducedMotion) {
        drawStaticOrb(ctx, currentState, cx, cy, baseRadius, size)
      } else {
        switch (currentState) {
          case 'idle':
            drawIdleOrb(ctx, time, cx, cy, baseRadius, size)
            break
          case 'listening':
            drawListeningOrb(ctx, smoothedLevel, scale, cx, cy, baseRadius, size)
            break
          case 'thinking':
            drawThinkingOrb(ctx, time, cx, cy, baseRadius, size)
            break
          case 'speaking':
            drawSpeakingOrb(ctx, time, smoothedLevel, scale, cx, cy, baseRadius, size)
            break
          case 'done':
            drawDoneOrb(ctx, cx, cy, baseRadius, size)
            break
        }
      }

      ctx.restore()
    }

    if (isReducedMotion || state === 'done') {
      drawFrame(0)
    } else {
      let isMounted = true
      const loop = (time: number) => {
        if (!isMounted) return
        drawFrame(time)
        animId = requestAnimationFrame(loop)
      }
      animId = requestAnimationFrame(loop)

      return () => {
        isMounted = false
        if (animId) cancelAnimationFrame(animId)
      }
    }
  }, [state, size, isReducedMotion])

  return (
    <div
      className={`relative flex items-center justify-center shrink-0 ${className}`}
      style={{ width: size, height: size }}
    >
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={`Examiner voice orb (${state})`}
        className="block"
      />
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
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-600/70 select-none">
          Strong
        </span>
      )
    case 'partial':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-950/80 text-amber-300 border border-amber-600/70 select-none">
          Partial
        </span>
      )
    case 'weak':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-red-950/80 text-red-300 border border-red-600/70 select-none">
          Weak
        </span>
      )
    case 'no_answer':
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-deep-slate text-muted-fog border border-steel-outline select-none">
          No Answer
        </span>
      )
    case 'start':
    default:
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-deep-slate text-pale-frost border border-steel-outline select-none">
          Start
        </span>
      )
  }
}

/**
 * Helper to render word-by-word karaoke highlighting
 */
function renderKaraokeSpans(
  text: string,
  startWordOffset: number,
  activeWordIdx: number,
  isSpeaking: boolean,
  baseClassName: string
) {
  if (!text) return null
  if (!isSpeaking) {
    return <span className={baseClassName}>{text}</span>
  }

  // Preserve spacing and punctuation
  const tokens = text.split(/(\s+)/)
  let wordCount = 0

  return (
    <span className={baseClassName}>
      {tokens.map((token, i) => {
        if (/^\s+$/.test(token)) {
          return <React.Fragment key={i}>{token}</React.Fragment>
        }
        const currentGlobalWord = startWordOffset + wordCount
        wordCount++
        const isSpoken = currentGlobalWord <= activeWordIdx
        const isCurrent = currentGlobalWord === activeWordIdx

        return (
          <span
            key={i}
            className={`transition-colors duration-100 ${
              isCurrent
                ? 'font-extrabold text-nuxt-signal bg-nuxt-signal/20 px-0.5 rounded shadow-sm'
                : isSpoken
                ? 'font-bold text-signal-white'
                : 'text-pale-frost/50 font-normal'
            }`}
          >
            {token}
          </span>
        )
      })}
    </span>
  )
}

/**
 * 4. QuestionCard with word-by-word karaoke bolding
 */
function QuestionCard({
  turn,
  onStartViva,
  busy,
  disabled,
  panelState,
  karaokeProgress,
}: {
  turn: ExaminerTurnLike | null
  onStartViva?: () => void
  busy: boolean
  disabled: boolean
  panelState: PanelState
  karaokeProgress: number
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
            onClick={() => {
              triggerFullscreen()
              onStartViva?.()
            }}
            disabled={busy || disabled}
            className="rounded-md bg-nuxt-signal px-4 py-1.5 text-xs font-semibold text-void-canvas hover:opacity-90 disabled:opacity-40 transition active:scale-95 select-none"
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

  const isSpeaking = panelState === 'speaking'

  // Calculate word counts for sequential karaoke progression across ack_text then question_text
  // (plain values, not hooks: this runs after the early return above)
  const ackWords = turn.ack_text ? turn.ack_text.trim().split(/\s+/).filter(Boolean) : []
  const questionWords = turn.question_text ? turn.question_text.trim().split(/\s+/).filter(Boolean) : []
  const totalWords = ackWords.length + questionWords.length

  const activeWordIdx =
    isSpeaking && totalWords > 0
      ? Math.min(totalWords - 1, Math.floor(karaokeProgress * totalWords))
      : -1

  return (
    <article
      className="panel shrink-0 p-3 bg-midnight-panel border border-steel-outline rounded-lg flex flex-col gap-2"
      aria-label="Current examiner question"
    >
      {/* Chips Header */}
      <div className="flex items-center gap-1.5 flex-wrap select-none">
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

      {/* Muted ack_text with karaoke bolding */}
      {turn.ack_text && (
        <p className="text-xs text-muted-fog italic border-l-2 border-nuxt-signal/50 pl-2.5 py-0.5 bg-void-canvas/30 rounded-r">
          "{renderKaraokeSpans(turn.ack_text, 0, activeWordIdx, isSpeaking, 'leading-relaxed')}"
        </p>
      )}

      {/* Bold Large question_text with aria-live="polite" and karaoke bolding */}
      <div
        aria-live="polite"
        aria-atomic="true"
        className="font-semibold text-sm sm:text-base text-signal-white leading-relaxed"
      >
        {renderKaraokeSpans(
          turn.question_text,
          ackWords.length,
          activeWordIdx,
          isSpeaking,
          'leading-relaxed'
        )}
      </div>

      {/* Code grounding highlight pill if present */}
      {turn.highlight && (
        <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-fog bg-void-canvas/80 px-2 py-1 rounded border border-steel-outline/80 mt-0.5">
          <span className="text-nuxt-signal select-none">📍</span>
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
 */
function DoneCard({ onRequestReport }: { onRequestReport?: () => void }) {
  return (
    <article
      className="panel shrink-0 p-4 bg-midnight-panel border border-nuxt-signal/50 rounded-lg flex flex-col gap-2.5 text-center shadow-[0_0_16px_rgba(0,220,130,0.15)]"
      aria-label="Viva completion status"
    >
      <div className="flex items-center justify-center gap-2">
        <span className="text-xl text-nuxt-signal select-none">🎉</span>
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
          className="mt-1 w-full py-2 px-3 rounded-md bg-nuxt-signal text-void-canvas font-bold text-xs hover:bg-vue-link active:scale-[0.98] transition shadow select-none"
        >
          View report
        </button>
      )}
    </article>
  )
}

/**
 * 6. Collapsible TranscriptHistory (Text remains fully selectable)
 */
function TranscriptHistory({ history }: { history: ExaminerTurnLike[] }) {
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
              <div className="flex items-center justify-between gap-1 text-[11px] select-none">
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

              {/* Question Text (Selectable) */}
              <p className="text-signal-white text-[11px] leading-relaxed">
                <span className="text-muted-fog font-mono font-semibold select-none">
                  Q:{' '}
                </span>
                {item.question_text}
              </p>

              {/* Student Transcript (Selectable) */}
              {item.student_transcript ? (
                <p className="text-pale-frost text-[11px] leading-relaxed bg-void-canvas/50 p-1.5 rounded border border-steel-outline/50">
                  <span className="text-nuxt-signal font-mono font-semibold select-none">
                    A:{' '}
                  </span>
                  "{item.student_transcript}"
                </p>
              ) : (
                <p className="text-muted-fog/60 italic text-[10px] pl-1">
                  (No spoken answer recorded)
                </p>
              )}

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
 */
function PushToTalkButton({
  isPressed,
  status,
  panelState,
  onPressStart,
  onPressEnd,
  disabled,
}: {
  isPressed: boolean
  status: RecorderStatus
  panelState: PanelState
  onPressStart: () => void
  onPressEnd: () => void
  disabled: boolean
}) {
  const isDenied = status === 'denied'
  const isThinking = panelState === 'thinking'
  const isSpeaking = panelState === 'speaking'

  return (
    <button
      type="button"
      disabled={disabled || isDenied || isThinking}
      onPointerDown={(e) => {
        e.preventDefault()
        if (!disabled && !isDenied && !isThinking) onPressStart()
      }}
      onPointerUp={(e) => {
        e.preventDefault()
        if (!disabled && !isDenied && !isThinking) onPressEnd()
      }}
      onPointerLeave={() => {
        if (isPressed) onPressEnd()
      }}
      className={`shrink-0 flex items-center justify-center gap-2 rounded-md py-2.5 px-3 text-xs font-semibold border transition select-none ${
        disabled || isDenied || isThinking
          ? 'opacity-40 cursor-not-allowed bg-deep-slate border-steel-outline text-muted-fog'
          : isPressed || panelState === 'listening'
          ? 'bg-red-600 text-white border-red-500 shadow-[0_0_16px_rgba(239,68,68,0.5)] scale-[0.99]'
          : isSpeaking
          ? 'bg-deep-slate text-indigo-300 border-indigo-500/70 hover:bg-steel-outline'
          : 'bg-deep-slate text-pale-frost border-steel-outline hover:bg-steel-outline hover:text-signal-white active:bg-nuxt-signal active:text-void-canvas'
      }`}
    >
      <span className="text-sm">
        {isDenied ? '❌' : isPressed || panelState === 'listening' ? '🔴' : isThinking ? '⏳' : isSpeaking ? '🎙️' : '🎙️'}
      </span>
      <span>
        {isDenied
          ? 'Microphone access denied'
          : isPressed || panelState === 'listening'
          ? 'Listening… Release to answer'
          : isThinking
          ? 'Evaluating response…'
          : isSpeaking
          ? 'Hold Space to barge in & answer'
          : 'Hold Space to answer'}
      </span>
    </button>
  )
}

/**
 * 8. TextFallbackInput (Enter submits, Shift+Enter newline)
 */
function TextFallbackInput({
  value,
  onChange,
  onSubmit,
  disabled,
  isPrimary,
}: {
  value: string
  onChange: (val: string) => void
  onSubmit: () => void
  disabled: boolean
  isPrimary?: boolean
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
        placeholder={
          isPrimary
            ? 'Type your answer here (Enter to submit, Shift+Enter newline)…'
            : 'Type answer (Enter to send, Shift+Enter newline)…'
        }
        className={`min-w-0 flex-1 resize-none rounded bg-void-canvas px-3 py-1.5 text-xs text-pale-frost border placeholder:text-blue-steel focus:outline-none disabled:opacity-40 leading-normal max-h-20 ${
          isPrimary
            ? 'border-nuxt-signal focus:border-nuxt-signal ring-1 ring-nuxt-signal/40'
            : 'border-steel-outline focus:border-nuxt-signal'
        }`}
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="rounded px-3 py-1.5 text-xs font-semibold bg-deep-slate border border-steel-outline text-pale-frost hover:bg-steel-outline hover:text-signal-white disabled:opacity-40 transition active:scale-95 select-none"
      >
        Send
      </button>
    </form>
  )
}

/**
 * Main ExaminerPanel Component per CONTEXT §5.9
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
  mode: _mode,
  turn,
  history,
  busy = false,
  onStartViva,
  forceState,
  levelSource: externalLevelSource,
}: ExaminerPanelProps) {
  // Current active turn state
  const [activeTurn, setActiveTurn] = useState<ExaminerTurnLike | null>(
    () => initialTurn ?? turn ?? null
  )

  // Internal transcript history
  const [internalHistory, setInternalHistory] = useState<ExaminerTurnLike[]>(() => {
    if (history && history.length > 0) return history
    const first = initialTurn ?? turn
    return first ? [first] : []
  })
  const internalHistoryRef = useRef(internalHistory)
  internalHistoryRef.current = internalHistory

  // Error and notice state: named error / setError per escalation spec
  const [error, setError] = useState<string | null>(null)
  const inlineError = error
  const setInlineError = setError

  // Synchronize external props into state when updated by parent and clear error on new turn
  useEffect(() => {
    const next = initialTurn ?? turn ?? null
    if (next) {
      setActiveTurn(next)
      setError(null)
    }
  }, [initialTurn, turn])

  // Clear error inside any useEffect that processes a successful new turn
  useEffect(() => {
    if (activeTurn) {
      setError(null)
    }
  }, [activeTurn])

  useEffect(() => {
    if (history && history.length > 0) {
      setInternalHistory(history)
    }
  }, [history])

  // Turn-flow state: 'idle' | 'listening' | 'thinking' | 'speaking' | 'done'
  const [panelState, setPanelState] = useState<PanelState>(() => {
    if (forceState) return forceState
    const initial = initialTurn ?? turn
    if (initial?.done) return 'done'
    return 'idle'
  })

  // Synchronize forceState for dev testing if provided
  useEffect(() => {
    if (forceState) {
      setPanelState(forceState)
    }
  }, [forceState])

  // Word-by-word karaoke tracking
  const [karaokeProgress, setKaraokeProgress] = useState(0)

  // Inputs and UI states
  const [typedInput, setTypedInput] = useState('')
  const [inlineWarning, setInlineWarning] = useState<string | null>(null)

  // Callback refs updated on every render so ExaminerPanel never invokes stale closures from mount
  const onSubmitAudioRef = useRef(onSubmitAudio)
  onSubmitAudioRef.current = onSubmitAudio
  const onSubmitTextRef = useRef(onSubmitText)
  onSubmitTextRef.current = onSubmitText
  const onTurnRef = useRef(onTurn)
  onTurnRef.current = onTurn
  const sessionIdRef = useRef(sessionId)
  sessionIdRef.current = sessionId

  // State & props refs for keyboard and event listeners
  const panelStateRef = useRef(panelState)
  panelStateRef.current = panelState
  const disabledRef = useRef(disabled)
  disabledRef.current = disabled
  const busyRef = useRef(busy)
  busyRef.current = busy
  const recorderRef = useRef<ReturnType<typeof usePushToTalkRecorder> | null>(null)

  // Submissions and late response guard
  type LastSubmission =
    | { type: 'audio'; audio: RecordedAudio }
    | { type: 'text'; text: string }

  const lastSubmissionRef = useRef<LastSubmission | null>(null)
  const requestIdRef = useRef(0)
  const isMountedRef = useRef(true)
  const isCancelledRef = useRef(false)
  const isSubmittingRef = useRef(false)

  // Active audio playback references
  const activePlaybackRef = useRef<AudioPlayback | null>(null)
  const activeFillerRef = useRef<AudioPlayback | null>(null)
  const karaokeRafRef = useRef<number | null>(null)

  // Pre-cached filler clips fetched once on mount
  const fillersRef = useRef<Array<{ id: string; text: string; audio_base64: string }>>([])

  // StrictMode double-speak guard on initialTurn mount
  const initialTurnSpokenRef = useRef(false)

  // Fetch fillers once from fillersUrl; failure ignored silently per spec
  useEffect(() => {
    let mounted = true
    if (typeof window !== 'undefined' && typeof window.fetch === 'function') {
      fetch(fillersUrl)
        .then((res) => (res.ok ? res.json() : []))
        .then((data: unknown) => {
          if (mounted && Array.isArray(data)) {
            fillersRef.current = data
          }
        })
        .catch(() => {
          // Failure ignored silently per CONTEXT §5.9 / TASKS B6
        })
    }
    return () => {
      mounted = false
    }
  }, [fillersUrl])

  // Cleanup helper for all playback and animation frames
  const stopCurrentPlayback = useCallback(() => {
    if (karaokeRafRef.current) {
      cancelAnimationFrame(karaokeRafRef.current)
      karaokeRafRef.current = null
    }
    if (activePlaybackRef.current) {
      try {
        activePlaybackRef.current.stop()
      } catch {}
      activePlaybackRef.current = null
    }
    if (activeFillerRef.current) {
      try {
        activeFillerRef.current.stop()
      } catch {}
      activeFillerRef.current = null
    }
    stopAllPlayback()
  }, [])

  // Mount lifecycle: mount tracking and unmount cleanup
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      requestIdRef.current++
      stopCurrentPlayback()
    }
  }, [stopCurrentPlayback])

  /**
   * Speaks a turn with audio_base64 or browser TTS fallback, syncing word karaoke
   */
  const speakTurn = useCallback(
    (turnToSpeak: ExaminerTurnLike, isDoneTurn = false) => {
      stopCurrentPlayback()
      unlockAudio()

      setPanelState(isDoneTurn ? 'done' : 'speaking')
      setKaraokeProgress(0)

      const spokenText = buildSpokenText(turnToSpeak.ack_text, turnToSpeak.question_text)
      const pb =
        turnToSpeak.audio_base64 && turnToSpeak.audio_base64.trim()
          ? playBase64Audio(turnToSpeak.audio_base64)
          : speakWithBrowserTTS(spokenText)

      activePlaybackRef.current = pb

      // Synchronize word-by-word karaoke progress at 60fps
      const syncKaraoke = () => {
        if (!isMountedRef.current) return
        if (activePlaybackRef.current === pb) {
          const p = pb.getProgress()
          setKaraokeProgress(p)
          karaokeRafRef.current = requestAnimationFrame(syncKaraoke)
        }
      }
      karaokeRafRef.current = requestAnimationFrame(syncKaraoke)

      pb.done.then(() => {
        if (!isMountedRef.current) return
        if (karaokeRafRef.current) {
          cancelAnimationFrame(karaokeRafRef.current)
          karaokeRafRef.current = null
        }
        setKaraokeProgress(1)
        if (activePlaybackRef.current === pb) {
          activePlaybackRef.current = null
          if (!isDoneTurn) {
            setPanelState('idle')
          }
        }
      })
    },
    [stopCurrentPlayback]
  )

  // Flow: initialTurn spoken once on mount (after unlockAudio; guard against StrictMode double-speak) -> idle
  useEffect(() => {
    const turnToSpeak = initialTurn ?? turn
    if (!turnToSpeak || initialTurnSpokenRef.current) return

    initialTurnSpokenRef.current = true
    unlockAudio()
    speakTurn(turnToSpeak, Boolean(turnToSpeak.done))
    const spokenPlayback = activePlaybackRef.current

    return () => {
      // In React 18 StrictMode, mount runs -> unmount cleanup runs immediately -> remount runs.
      // Halting playback and resetting flag lets the true remount speak cleanly without double-speak.
      // Only stop our own playback: a newer turn's speech must survive the parent's prop update.
      if (activePlaybackRef.current === spokenPlayback) stopCurrentPlayback()
      if (internalHistoryRef.current.length <= 1) {
        initialTurnSpokenRef.current = false
      }
    }
  }, [initialTurn, turn, speakTurn, stopCurrentPlayback])

  /**
   * Plays a random latency-hiding filler immediately when entering thinking state
   */
  const playRandomFiller = useCallback(() => {
    if (activeFillerRef.current) {
      return
    }

    const available = fillersRef.current.filter((f) => f && f.audio_base64)
    if (available.length > 0) {
      const chosen = available[Math.floor(Math.random() * available.length)]
      if (chosen.audio_base64) {
        unlockAudio()
        activeFillerRef.current = playBase64Audio(chosen.audio_base64)
      }
    }
  }, [])

  /**
   * Processes an incoming response turn
   */
  const handleTurnResponse = useCallback(
    (nextTurn: ExaminerTurnLike) => {
      // Clear any failure banner cleanly on successful response
      setError(null)

      // Check verdict and transcript for "Didn't catch that" warning
      if (
        nextTurn.verdict === 'no_answer' ||
        !nextTurn.student_transcript ||
        !nextTurn.student_transcript.trim()
      ) {
        setInlineWarning("Didn't catch that — try again or type")
      } else {
        setInlineWarning(null)
      }

      // Push to history
      setInternalHistory((prev) => [...prev, nextTurn])

      // Set active turn
      setActiveTurn(nextTurn)

      // Call onTurn once per spec via ref
      onTurnRef.current?.(nextTurn)

      // Handle done state or speak response
      if (nextTurn.done) {
        setPanelState('done')
        speakTurn(nextTurn, true)
      } else {
        speakTurn(nextTurn, false)
      }
    },
    [speakTurn]
  )

  /**
   * Handles audio answer submission via push-to-talk recording
   */
  const handleAudioSubmit = useCallback(
    async (rec: RecordedAudio) => {
      if (isSubmittingRef.current) return
      isSubmittingRef.current = true

      // Explicitly call setError(null) immediately inside handleAudioSubmit before awaiting parent props
      setError(null)
      setInlineWarning(null)
      setPanelState('thinking')

      playRandomFiller()
      lastSubmissionRef.current = { type: 'audio', audio: rec }
      const currentReqId = ++requestIdRef.current

      try {
        let nextTurn: ExaminerTurnLike
        if (onSubmitAudioRef.current) {
          nextTurn = await onSubmitAudioRef.current(rec)
        } else if (sessionIdRef.current) {
          const res = await submitTurn({
            session_id: sessionIdRef.current,
            audio_base64: rec.base64,
            audio_mime: rec.mimeType,
          })
          nextTurn = res as ExaminerTurnLike
        } else {
          throw new Error('No session ID or onSubmitAudio handler provided to ExaminerPanel')
        }

        // Ignore late responses arriving after cancellation or unmount
        if (!isMountedRef.current || requestIdRef.current !== currentReqId) return

        if (activeFillerRef.current) {
          activeFillerRef.current.stop()
          activeFillerRef.current = null
        }

        // Cleanly clear error banner on successful receipt
        setError(null)
        handleTurnResponse(nextTurn)
      } catch (err: unknown) {
        if (!isMountedRef.current || requestIdRef.current !== currentReqId) return

        if (activeFillerRef.current) {
          activeFillerRef.current.stop()
          activeFillerRef.current = null
        }

        setPanelState('idle')
        const errMsg = err instanceof Error ? err.message : 'Submission failed. Please try again.'
        setError(errMsg)
      } finally {
        isSubmittingRef.current = false
      }
    },
    [playRandomFiller, handleTurnResponse]
  )
  const handleAudioRecorded = handleAudioSubmit

  /**
   * Handles typed text answer submission
   */
  const handleTextSubmit = useCallback(async () => {
    const text = typedInput.trim()
    if (
      !text ||
      isSubmittingRef.current ||
      panelStateRef.current === 'thinking' ||
      disabledRef.current ||
      busyRef.current ||
      panelStateRef.current === 'done'
    ) {
      return
    }

    isSubmittingRef.current = true
    // Explicitly call setError(null) immediately inside handleTextSubmit before awaiting parent props
    setError(null)
    setInlineWarning(null)
    stopCurrentPlayback()
    setPanelState('thinking')
    setTypedInput('')

    playRandomFiller()
    lastSubmissionRef.current = { type: 'text', text }
    const currentReqId = ++requestIdRef.current

    try {
      let nextTurn: ExaminerTurnLike
      if (onSubmitTextRef.current) {
        nextTurn = await onSubmitTextRef.current(text)
      } else if (sessionIdRef.current) {
        const res = await submitTurn({
          session_id: sessionIdRef.current,
          student_text: text,
        })
        nextTurn = res as ExaminerTurnLike
      } else {
        throw new Error('No session ID or onSubmitText handler provided to ExaminerPanel')
      }

      if (!isMountedRef.current || requestIdRef.current !== currentReqId) return

      if (activeFillerRef.current) {
        activeFillerRef.current.stop()
        activeFillerRef.current = null
      }

      // Cleanly clear error banner on successful receipt
      setError(null)
      handleTurnResponse(nextTurn)
    } catch (err: unknown) {
      if (!isMountedRef.current || requestIdRef.current !== currentReqId) return

      if (activeFillerRef.current) {
        activeFillerRef.current.stop()
        activeFillerRef.current = null
      }

      setPanelState('idle')
      const errMsg = err instanceof Error ? err.message : 'Submission failed. Please try again.'
      setError(errMsg)
    } finally {
      isSubmittingRef.current = false
    }
  }, [
    typedInput,
    stopCurrentPlayback,
    playRandomFiller,
    handleTurnResponse,
  ])

  /**
   * Retries the same last recording or typed text
   */
  const handleRetry = useCallback(() => {
    const lastSub = lastSubmissionRef.current
    if (!lastSub || isSubmittingRef.current || panelStateRef.current === 'thinking') return

    // Explicitly call setError(null) immediately inside handleRetry before awaiting parent props
    setError(null)
    setInlineWarning(null)

    if (lastSub.type === 'audio') {
      void handleAudioSubmit(lastSub.audio)
    } else {
      void (async () => {
        isSubmittingRef.current = true
        // Explicitly call setError(null) immediately inside handleRetry before awaiting parent props
        setError(null)
        setInlineWarning(null)
        stopCurrentPlayback()
        setPanelState('thinking')
        playRandomFiller()
        const currentReqId = ++requestIdRef.current
        try {
          let nextTurn: ExaminerTurnLike
          if (onSubmitTextRef.current) {
            nextTurn = await onSubmitTextRef.current(lastSub.text)
          } else if (sessionIdRef.current) {
            const res = await submitTurn({
              session_id: sessionIdRef.current,
              student_text: lastSub.text,
            })
            nextTurn = res as ExaminerTurnLike
          } else {
            throw new Error('No session ID or onSubmitText handler provided to ExaminerPanel')
          }
          if (!isMountedRef.current || requestIdRef.current !== currentReqId) return
          if (activeFillerRef.current) {
            activeFillerRef.current.stop()
            activeFillerRef.current = null
          }
          // Cleanly clear error banner on successful receipt
          setError(null)
          handleTurnResponse(nextTurn)
        } catch (err: unknown) {
          if (!isMountedRef.current || requestIdRef.current !== currentReqId) return
          if (activeFillerRef.current) {
            activeFillerRef.current.stop()
            activeFillerRef.current = null
          }
          setPanelState('idle')
          const errMsg = err instanceof Error ? err.message : 'Submission failed'
          setError(errMsg)
        } finally {
          isSubmittingRef.current = false
        }
      })()
    }
  }, [handleAudioSubmit, stopCurrentPlayback, playRandomFiller, handleTurnResponse])

  // Hook instance under test (Task B2 & B6)
  const isHookEnabled = !disabled && panelState !== 'done'
  const isSpacebarEnabled = isHookEnabled && panelState !== 'thinking'

  const recorder = usePushToTalkRecorder({
    enabled: isHookEnabled,
    bindSpacebar: isSpacebarEnabled,
    minDurationMs: 300,
    maxDurationMs: 60000,
    onRecordingComplete: (rec) => {
      void handleAudioRecorded(rec)
    },
    onTooShort: () => {
      setInlineWarning("Didn't catch that — try again or type")
      if (activeFillerRef.current) {
        activeFillerRef.current.stop()
        activeFillerRef.current = null
      }
      if (panelStateRef.current === 'listening' || panelStateRef.current === 'thinking') {
        setPanelState('idle')
      }
    },
  })
  recorderRef.current = recorder

  // Push-to-talk recording state tracking & barge-in
  useEffect(() => {
    if (recorder.isRecording) {
      stopCurrentPlayback()
      isCancelledRef.current = false
      setPanelState('listening')
    } else if (panelState === 'listening' && !recorder.isRecording) {
      // disabled mid-hold: the hook cancels the clip, so no submit will follow — don't enter thinking
      if (isCancelledRef.current || disabledRef.current) {
        isCancelledRef.current = false
        setPanelState('idle')
      } else {
        // PTT released: smooth transition cleanly into thinking while encoding audio (no idle flicker)
        setPanelState('thinking')
        playRandomFiller()
      }
    }
  }, [recorder.isRecording, panelState, stopCurrentPlayback, playRandomFiller])

  // Escape key handler to cancel in-flight submission or recording
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (panelState === 'thinking') {
          // Cancel in-flight request
          requestIdRef.current++
          if (activeFillerRef.current) {
            activeFillerRef.current.stop()
            activeFillerRef.current = null
          }
          setPanelState('idle')
        } else if (panelState === 'listening') {
          isCancelledRef.current = true
          recorderRef.current?.cancelRecording()
          setPanelState('idle')
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [panelState])

  // Push-to-talk mouse/touch handlers with barge-in support
  const [isMousePressed, setIsMousePressed] = useState(false)

  const handlePressStart = useCallback(() => {
    if (disabled || busy || panelState === 'thinking' || panelState === 'done') return

    // Barge-in if speaking
    if (panelState === 'speaking') {
      stopCurrentPlayback()
    }

    setIsMousePressed(true)
    recorder.startRecording()
  }, [disabled, busy, panelState, stopCurrentPlayback, recorder])

  const handlePressEnd = useCallback(() => {
    if (!isMousePressed && !recorder.isRecording) return
    setIsMousePressed(false)
    recorder.stopRecording()
  }, [isMousePressed, recorder])

  // Pass live audio levels to VoiceOrb per B5 review note:
  // return recorder.getInputLevel() while listening, active playback.getLevel() while speaking, 0 otherwise
  const defaultLevelSource = useCallback((): number => {
    if (panelState === 'listening') {
      return recorder.getInputLevel()
    }
    if (panelState === 'speaking' && activePlaybackRef.current) {
      return activePlaybackRef.current.getLevel()
    }
    return 0
  }, [panelState, recorder])

  const effectiveLevelSource = externalLevelSource ?? defaultLevelSource

  const currentDepth = activeTurn?.depth_level ?? 1
  const isInputDisabled =
    disabled || busy || panelState === 'thinking' || panelState === 'done'
  const isMicDenied = recorder.status === 'denied'

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-2 p-3 bg-midnight-panel text-pale-frost overflow-hidden font-sans">
      {/* 1. Header (title + status pill) */}
      <ExaminerHeader state={panelState} disabled={disabled} />

      {/* 2. Depth Meter (L1..L4) */}
      <DepthMeter currentDepth={currentDepth} />

      {/* 3. Voice Orb */}
      <div className="shrink-0 flex flex-col items-center justify-center py-1 select-none">
        <VoiceOrb
          state={panelState}
          levelSource={effectiveLevelSource}
          size={120}
        />
        <span className="mt-0.5 text-[11px] text-muted-fog">
          {panelState === 'listening'
            ? 'Listening to student response…'
            : panelState === 'thinking'
            ? 'Evaluating response against rubric…'
            : panelState === 'speaking'
            ? 'Examiner speaking…'
            : panelState === 'done'
            ? 'Viva complete'
            : isMicDenied
            ? 'Type answer below'
            : 'Hold Space to answer'}
        </span>
      </div>

      {/* 4. QuestionCard OR DoneCard */}
      {panelState === 'done' || activeTurn?.done ? (
        <DoneCard onRequestReport={onRequestReport} />
      ) : (
        <QuestionCard
          turn={activeTurn}
          onStartViva={onStartViva}
          busy={busy}
          disabled={disabled}
          panelState={panelState}
          karaokeProgress={karaokeProgress}
        />
      )}

      {/* 5. Transcript History (Collapsible, SCROLLS!) */}
      <TranscriptHistory history={internalHistory} />

      {/* 6. Inline Error & Warning Banners */}
      {error && (
        <div className="shrink-0 flex items-center justify-between gap-2 p-2 rounded bg-red-950/90 border border-red-600/80 text-xs text-red-200">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-red-400 select-none">⚠️</span>
            <span className="truncate">{error}</span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={handleRetry}
              className="px-2 py-0.5 rounded bg-red-600 hover:bg-red-500 text-white font-semibold text-[11px] transition active:scale-95 select-none"
            >
              Retry
            </button>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-200 text-xs px-1 font-mono select-none"
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {inlineWarning && (
        <div className="shrink-0 flex items-center justify-between gap-2 p-2 rounded bg-amber-950/80 border border-amber-600/70 text-xs text-amber-200">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-amber-400 select-none">🤔</span>
            <span>{inlineWarning}</span>
          </div>
          <button
            type="button"
            onClick={() => setInlineWarning(null)}
            className="text-amber-400/80 hover:text-amber-200 text-xs px-1 font-mono select-none"
            aria-label="Dismiss notice"
          >
            ✕
          </button>
        </div>
      )}

      {isMicDenied && (
        <div className="shrink-0 flex items-center gap-1.5 p-2 rounded bg-deep-slate border border-steel-outline text-xs text-pale-frost select-none">
          <span className="text-amber-400">🎙️❌</span>
          <span>Microphone access denied. Text input is primary.</span>
        </div>
      )}

      {/* 7. Push-to-Talk Button & Text Fallback Input */}
      <div className="shrink-0 flex flex-col gap-1.5 pt-2 border-t border-steel-outline">
        <PushToTalkButton
          isPressed={isMousePressed || recorder.isRecording}
          status={recorder.status}
          panelState={panelState}
          onPressStart={handlePressStart}
          onPressEnd={handlePressEnd}
          disabled={isInputDisabled}
        />

        <TextFallbackInput
          value={typedInput}
          onChange={setTypedInput}
          onSubmit={handleTextSubmit}
          disabled={isInputDisabled}
          isPrimary={isMicDenied}
        />
      </div>
    </div>
  )
}
