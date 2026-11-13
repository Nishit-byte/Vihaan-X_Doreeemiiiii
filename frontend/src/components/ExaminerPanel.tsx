/**
 * M3 Voice Pipeline — ExaminerPanel Component (Tasks B4 & B5)
 *
 * Implements the visual panel layout and real-time VoiceOrb animation:
 * - Sub-components (all in this file):
 *     1. ExaminerHeader (title + reactive status pill)
 *     2. DepthMeter (L1 Recall, L2 Comprehension, L3 Analysis, L4 Evaluation with animated highlight)
 *     3. VoiceOrb (Task B5: Canvas with devicePixelRatio scaling, requestAnimationFrame, smoothed scale, per-state visuals)
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

import React, { useId, useMemo, useRef, useState, useEffect } from 'react'
import type { TurnResponse, Verdict } from '../types/api'
import type { RecordedAudio } from '../services/audioRecorder'

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

  // Testing & dev-harness state overrides
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
 * 3. VoiceOrb (Task B5)
 * Real-time reactive voice visualization using HTML5 Canvas:
 * - High-DPI support with devicePixelRatio scaling
 * - Smoothed level scale: 1 + level * 0.35 (lerp)
 * - Per-state visuals:
 *     - idle: slow breathing slate/indigo
 *     - listening: emerald reacting to mic level
 *     - thinking: amber rotating dashed ring
 *     - speaking: indigo/violet ripples reacting to playback level
 *     - done: calm static emerald with checkmark
 * - Zero React state updates per frame (100% rAF canvas rendering)
 * - Loop cleanly cancelled on unmount
 * - Accessibility: prefers-reduced-motion renders static state orb with no rAF overhead
 */
function drawIdleOrb(
  ctx: CanvasRenderingContext2D,
  time: number,
  cx: number,
  cy: number,
  baseRadius: number,
  size: number
) {
  // Slow breathing slate / indigo: period ~3.5s
  const breath = Math.sin(time * 0.0018) * 0.06
  const r = baseRadius * (1 + breath)

  // Soft ambient outer halo
  const halo = ctx.createRadialGradient(cx, cy, r * 0.6, cx, cy, r * 1.55)
  halo.addColorStop(0, 'rgba(99, 102, 241, 0.22)')
  halo.addColorStop(0.5, 'rgba(71, 85, 105, 0.12)')
  halo.addColorStop(1, 'rgba(15, 23, 42, 0)')
  ctx.fillStyle = halo
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.55, 0, Math.PI * 2)
  ctx.fill()

  // Faint orbital ring
  ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.35, 0, Math.PI * 2)
  ctx.stroke()

  // Core gradient: slate & indigo
  const core = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#6366f1') // indigo-500
  core.addColorStop(0.45, '#3730a3') // indigo-800
  core.addColorStop(1, '#0f172a') // slate-900
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  // Core border
  ctx.strokeStyle = 'rgba(129, 140, 248, 0.5)'
  ctx.lineWidth = 1.5
  ctx.stroke()

  // Soft specular highlight
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
  // Emerald reacting to mic level
  const r = baseRadius * scale
  const maxR = size / 2 - 3

  // Dynamic outer reactive shockwaves
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

  // Ambient emerald glow
  const glow = ctx.createRadialGradient(cx, cy, r * 0.5, cx, cy, Math.min(maxR, r * 1.6))
  glow.addColorStop(0, `rgba(0, 220, 130, ${0.35 + smoothedLevel * 0.4})`)
  glow.addColorStop(0.7, `rgba(5, 150, 105, ${0.15 + smoothedLevel * 0.2})`)
  glow.addColorStop(1, 'rgba(6, 78, 59, 0)')
  ctx.fillStyle = glow
  ctx.beginPath()
  ctx.arc(cx, cy, Math.min(maxR, r * 1.6), 0, Math.PI * 2)
  ctx.fill()

  // Core gradient: emerald
  const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#34d399') // emerald-400
  core.addColorStop(0.5, '#059669') // emerald-600
  core.addColorStop(1, '#064e3b') // emerald-900
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  // Core border
  ctx.strokeStyle = `rgba(52, 211, 153, ${0.7 + smoothedLevel * 0.3})`
  ctx.lineWidth = 2 + smoothedLevel * 1.5
  ctx.stroke()

  // Specular highlight
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
  size: number
) {
  // Amber rotating dashed ring
  const angle = (time * 0.0024) % (Math.PI * 2)
  const ring1R = baseRadius * 1.38

  // Outer primary rotating dashed ring
  ctx.save()
  ctx.translate(cx, cy)
  ctx.rotate(angle)
  ctx.setLineDash([8, 6])
  ctx.strokeStyle = '#f59e0b' // amber-500
  ctx.lineWidth = 2.4
  ctx.beginPath()
  ctx.arc(0, 0, ring1R, 0, Math.PI * 2)
  ctx.stroke()
  ctx.restore()

  // Inner counter-rotating dashed accent
  const ring2R = baseRadius * 1.18
  ctx.save()
  ctx.translate(cx, cy)
  ctx.rotate(-angle * 0.65)
  ctx.setLineDash([4, 6])
  ctx.strokeStyle = 'rgba(251, 191, 36, 0.45)' // amber-400
  ctx.lineWidth = 1.4
  ctx.beginPath()
  ctx.arc(0, 0, ring2R, 0, Math.PI * 2)
  ctx.stroke()
  ctx.restore()

  // Core subtle pulse
  const pulse = Math.sin(time * 0.004) * 0.035
  const r = baseRadius * (1 + pulse)

  // Ambient glow
  const glow = ctx.createRadialGradient(cx, cy, r * 0.5, cx, cy, r * 1.5)
  glow.addColorStop(0, 'rgba(245, 158, 11, 0.28)')
  glow.addColorStop(0.6, 'rgba(217, 119, 6, 0.12)')
  glow.addColorStop(1, 'rgba(120, 53, 15, 0)')
  ctx.fillStyle = glow
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.5, 0, Math.PI * 2)
  ctx.fill()

  // Core gradient: amber
  const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#fbbf24') // amber-400
  core.addColorStop(0.5, '#d97706') // amber-600
  core.addColorStop(1, '#78350f') // amber-900
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  // Core border
  ctx.strokeStyle = 'rgba(251, 191, 36, 0.85)'
  ctx.lineWidth = 1.8
  ctx.stroke()

  // Specular highlight
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
  // Indigo / violet ripples reacting to playback level
  const r = baseRadius * scale
  const maxR = size / 2 - 3

  // Concentric ripples expanding outward
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

  // Ambient violet/indigo glow
  const glow = ctx.createRadialGradient(cx, cy, r * 0.5, cx, cy, Math.min(maxR, r * 1.6))
  glow.addColorStop(0, `rgba(168, 85, 247, ${0.35 + smoothedLevel * 0.45})`)
  glow.addColorStop(0.5, `rgba(99, 102, 241, ${0.2 + smoothedLevel * 0.3})`)
  glow.addColorStop(1, 'rgba(49, 46, 129, 0)')
  ctx.fillStyle = glow
  ctx.beginPath()
  ctx.arc(cx, cy, Math.min(maxR, r * 1.6), 0, Math.PI * 2)
  ctx.fill()

  // Core gradient: violet/indigo
  const core = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#c084fc') // purple-400
  core.addColorStop(0.4, '#818cf8') // indigo-400
  core.addColorStop(0.8, '#4f46e5') // indigo-600
  core.addColorStop(1, '#312e81') // indigo-900
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  // Core border
  ctx.strokeStyle = `rgba(192, 132, 252, ${0.75 + smoothedLevel * 0.25})`
  ctx.lineWidth = 2 + smoothedLevel * 1.5
  ctx.stroke()

  // Specular highlight
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
  size: number
) {
  // Calm static emerald orb
  const r = baseRadius

  // Outer serene halo
  const halo = ctx.createRadialGradient(cx, cy, r * 0.6, cx, cy, r * 1.35)
  halo.addColorStop(0, 'rgba(0, 220, 130, 0.25)')
  halo.addColorStop(0.6, 'rgba(5, 150, 105, 0.1)')
  halo.addColorStop(1, 'rgba(6, 78, 59, 0)')
  ctx.fillStyle = halo
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.35, 0, Math.PI * 2)
  ctx.fill()

  // Calm border ring
  ctx.strokeStyle = 'rgba(0, 220, 130, 0.4)'
  ctx.lineWidth = 1.2
  ctx.beginPath()
  ctx.arc(cx, cy, r * 1.22, 0, Math.PI * 2)
  ctx.stroke()

  // Core gradient: emerald
  const core = ctx.createRadialGradient(cx - r * 0.2, cy - r * 0.2, r * 0.1, cx, cy, r)
  core.addColorStop(0, '#34d399')
  core.addColorStop(0.5, '#059669')
  core.addColorStop(1, '#064e3b')
  ctx.fillStyle = core
  ctx.beginPath()
  ctx.arc(cx, cy, r, 0, Math.PI * 2)
  ctx.fill()

  // Core border
  ctx.strokeStyle = 'rgba(0, 220, 130, 0.8)'
  ctx.lineWidth = 2
  ctx.stroke()

  // Calm white checkmark
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
      // Static emerald
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
      // Static amber with static dashed ring
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
      // Static indigo / violet with static outer ring
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
      // Static slate / indigo
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

  // Track prefers-reduced-motion
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

      // Smoothed scale per spec: 1 + level * 0.35 (lerp factor ~0.18)
      smoothedLevel += (targetLevel - smoothedLevel) * 0.18
      const scale = 1 + smoothedLevel * 0.35

      const cx = size / 2
      const cy = size / 2
      const baseRadius = size * 0.26

      if (isReducedMotion) {
        // Static rendering for prefers-reduced-motion
        drawStaticOrb(ctx, currentState, cx, cy, baseRadius, size)
      } else {
        // Dynamic per-state animations
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
      // Draw single static frame without animation loop (done orb is static)
      drawFrame(0)
    } else {
      // Run continuous rAF loop
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
  levelSource,
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

      {/* 3. Voice Orb */}
      <div className="shrink-0 flex flex-col items-center justify-center py-1">
        <VoiceOrb
          state={panelState}
          levelSource={levelSource ?? (isPressed ? () => 0.6 : () => 0)}
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
