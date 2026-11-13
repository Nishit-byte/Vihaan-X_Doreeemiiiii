// Right panel (35%). Layout follows the spec: voice orb, synced question card,
// collapsible transcript, L1-L4 depth meter, Spacebar push-to-talk + typed fallback.
// M3 owns this file: swap the recorder/playback internals for audioRecorder.ts
// if you prefer, but keep the ExaminerPanelProps contract (see types/api.ts).
import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Mic, RotateCcw, Send } from 'lucide-react'
import { submitTurn } from '../services/apiClient'
import type { ExaminerPanelProps } from '../types/api'

const LEVELS = [
  { l: 1, name: 'Recall' }, { l: 2, name: 'Why' }, { l: 3, name: 'Trade-offs' }, { l: 4, name: 'Mutation' },
]
type Phase = 'idle' | 'speaking' | 'listening' | 'thinking'

const toB64 = (blob: Blob) => new Promise<string>((res, rej) => {
  const r = new FileReader()
  r.onload = () => res(String(r.result).split(',')[1] ?? '')
  r.onerror = () => rej(r.error)
  r.readAsDataURL(blob)
})
const isTyping = (t: EventTarget | null) => {
  const el = t as HTMLElement | null
  return !!el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable)
}

export default function ExaminerPanel({ sessionId, turn, history, busy, onTurn }: ExaminerPanelProps) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [text, setText] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [showLog, setShowLog] = useState(false)

  const orbRef = useRef<HTMLDivElement>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const rafRef = useRef(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const recRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const logEndRef = useRef<HTMLDivElement>(null)

  const enabled = !!sessionId && !busy && phase !== 'thinking'

  // Orb amplitude from Web Audio analyser
  const startMeter = () => {
    cancelAnimationFrame(rafRef.current)
    const loop = () => {
      const a = analyserRef.current, el = orbRef.current
      if (!a || !el) return
      const d = new Uint8Array(a.fftSize); a.getByteTimeDomainData(d)
      let s = 0; for (const v of d) { const x = (v - 128) / 128; s += x * x }
      el.style.transform = `scale(${1 + Math.min(Math.sqrt(s / d.length) * 2.5, 0.6)})`
      rafRef.current = requestAnimationFrame(loop)
    }
    loop()
  }
  const stopMeter = () => { cancelAnimationFrame(rafRef.current); if (orbRef.current) orbRef.current.style.transform = 'scale(1)' }
  const ensureCtx = () => {
    const ctx = (ctxRef.current ??= new AudioContext())
    if (ctx.state === 'suspended') void ctx.resume()
    analyserRef.current ??= ctx.createAnalyser()
    return { ctx, analyser: analyserRef.current }
  }

  const speak = useCallback((b64: string) => {
    if (!b64) return
    audioRef.current?.pause()
    const el = new Audio('data:audio/mpeg;base64,' + b64)
    audioRef.current = el
    try {
      const { ctx, analyser } = ensureCtx()
      const src = ctx.createMediaElementSource(el)
      src.connect(analyser); analyser.connect(ctx.destination)
    } catch { /* analyser optional */ }
    el.onended = () => { setPhase(p => (p === 'speaking' ? 'idle' : p)); stopMeter() }
    el.play().then(() => { setPhase('speaking'); startMeter() }).catch(() => { /* autoplay blocked: Replay button */ })
  }, [])

  // Speak each new question
  useEffect(() => { if (turn?.audio_base64) speak(turn.audio_base64) }, [turn, speak])
  useEffect(() => { logEndRef.current?.scrollIntoView({ block: 'end' }) }, [history, showLog])
  useEffect(() => () => {
    audioRef.current?.pause(); streamRef.current?.getTracks().forEach(t => t.stop()); cancelAnimationFrame(rafRef.current)
  }, [])

  const send = useCallback(async (payload: { student_text?: string; audio_base64?: string }) => {
    if (!sessionId) return
    setPhase('thinking'); setErr(null)
    try { onTurn(await submitTurn({ session_id: sessionId, ...payload })) }
    catch (e) { setErr(e instanceof Error ? e.message : 'Could not send your answer') }
    finally { setPhase(p => (p === 'thinking' ? 'idle' : p)) }
  }, [sessionId, onTurn])

  const startRec = useCallback(async () => {
    if (recRef.current || !enabled) return
    audioRef.current?.pause(); stopMeter(); setErr(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const { ctx, analyser } = ensureCtx()
      ctx.createMediaStreamSource(stream).connect(analyser)
      const rec = new MediaRecorder(stream); chunksRef.current = []
      rec.ondataavailable = e => e.data.size && chunksRef.current.push(e.data)
      rec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop()); stopMeter(); recRef.current = null
        const blob = new Blob(chunksRef.current, { type: rec.mimeType })
        if (blob.size < 1500) { setPhase('idle'); setErr('That was too short. Hold the button while you speak.'); return }
        await send({ audio_base64: await toB64(blob) })
      }
      recRef.current = rec; rec.start(); setPhase('listening'); startMeter()
    } catch {
      setPhase('idle'); setErr('Microphone unavailable. Allow access or type your answer below.')
    }
  }, [enabled, send])

  const stopRec = useCallback(() => { if (recRef.current?.state === 'recording') recRef.current.stop() }, [])

  // Spacebar push-to-talk (ignored while typing in Monaco or inputs)
  useEffect(() => {
    const down = (e: KeyboardEvent) => { if (e.code === 'Space' && !e.repeat && !isTyping(e.target)) { e.preventDefault(); void startRec() } }
    const up = (e: KeyboardEvent) => { if (e.code === 'Space' && !isTyping(e.target)) { e.preventDefault(); stopRec() } }
    window.addEventListener('keydown', down); window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up) }
  }, [startRec, stopRec])

  const submitText = () => { const t = text.trim(); if (t && enabled) { setText(''); void send({ student_text: t }) } }
  const depth = turn?.depth_level ?? 0
  const status = { idle: 'Hold Space to answer', speaking: 'Examiner speaking', listening: 'Listening… release to send', thinking: 'Thinking…' }[phase]

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-3">
      {/* Cognitive depth meter */}
      <div role="meter" aria-label="Cognitive depth" aria-valuemin={1} aria-valuemax={4} aria-valuenow={depth || undefined}
        className="grid grid-cols-4 gap-1.5">
        {LEVELS.map(({ l, name }) => (
          <div key={l}>
            <div className={`h-1.5 rounded-full ${l <= depth ? 'bg-nuxt-signal' : 'bg-steel-outline'}`} />
            <div className={`mt-1 text-xs ${l === depth ? 'font-semibold text-signal-white' : 'text-muted-fog'}`}>L{l} {name}</div>
          </div>
        ))}
      </div>

      {/* Voice orb */}
      <div className="flex shrink-0 flex-col items-center gap-2 py-2">
        <div className="flex h-24 w-24 items-center justify-center rounded-full ring-1 ring-steel-outline">
          <div ref={orbRef}
            className={`h-14 w-14 rounded-full transition-colors ${phase === 'listening' ? 'bg-signal-white' : phase === 'idle' ? 'bg-blue-steel' : 'bg-nuxt-signal'}`} />
        </div>
        <span role="status" className="text-sm text-muted-fog">{status}</span>
      </div>

      {/* Question card */}
      <div className="panel min-h-0 flex-1 overflow-auto p-3">
        {turn ? (
          <>
            <div className="flex items-center gap-2 text-xs font-semibold text-nuxt-signal">
              <span>L{turn.depth_level}</span><span className="text-muted-fog">{turn.topic}</span>
              {turn.audio_base64 && (
                <button onClick={() => speak(turn.audio_base64)} aria-label="Replay question"
                  className="ml-auto rounded-md p-1 text-muted-fog hover:text-signal-white"><RotateCcw className="h-4 w-4" /></button>
              )}
            </div>
            {turn.ack_text && <p className="mt-2 text-sm text-muted-fog">{turn.ack_text}</p>}
            <p className="mt-2 text-lg font-medium leading-7 text-signal-white">{turn.question_text}</p>
            {turn.done && <p className="mt-3 text-sm text-muted-fog">Viva complete. Press Finish viva for your report.</p>}
          </>
        ) : (
          <p className="text-sm text-muted-fog">The examiner’s first question appears here once you start a viva.</p>
        )}
      </div>

      {err && <p role="alert" className="text-sm text-pale-frost">{err}</p>}

      {/* Controls */}
      <div className="flex shrink-0 flex-col gap-2">
        <button
          onPointerDown={() => void startRec()} onPointerUp={stopRec} onPointerLeave={stopRec}
          onKeyDown={e => { if (e.code === 'Space') e.preventDefault() }}
          disabled={!enabled}
          className={`flex items-center justify-center gap-2 rounded-md px-2.5 py-2 text-base font-medium ring-1 ring-inset disabled:cursor-not-allowed disabled:opacity-40 ${phase === 'listening' ? 'bg-signal-white text-deep-slate ring-signal-white' : 'text-pale-frost ring-blue-steel hover:bg-deep-slate'}`}>
          <Mic className="h-4 w-4" aria-hidden />{phase === 'listening' ? 'Listening…' : 'Hold to talk (Space)'}
        </button>
        <div className="flex gap-2">
          <input value={text} onChange={e => setText(e.target.value)} onKeyDown={e => e.key === 'Enter' && submitText()}
            disabled={!enabled} placeholder="Or type your answer" aria-label="Typed answer"
            className="min-w-0 flex-1 rounded-md bg-void-canvas px-3 py-2 text-sm text-pale-frost ring-1 ring-steel-outline placeholder:text-blue-steel focus:outline-none disabled:opacity-40" />
          <button onClick={submitText} disabled={!enabled || !text.trim()} aria-label="Send answer"
            className="rounded-md px-2.5 text-pale-frost ring-1 ring-inset ring-blue-steel hover:bg-deep-slate disabled:cursor-not-allowed disabled:opacity-40">
            <Send className="h-4 w-4" />
          </button>
        </div>

        {/* Transcript */}
        <div>
          <button onClick={() => setShowLog(v => !v)} aria-expanded={showLog}
            className="flex items-center gap-1 text-sm font-medium text-muted-fog hover:text-pale-frost">
            {showLog ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}Transcript ({history.length})
          </button>
          {showLog && (
            <ul className="mt-2 max-h-40 space-y-2 overflow-auto rounded-md bg-void-canvas p-3 text-sm ring-1 ring-steel-outline">
              {history.map((t, i) => (
                <li key={i}>
                  {t.student_transcript && <p className="text-pale-frost"><span className="text-muted-fog">You: </span>{t.student_transcript}</p>}
                  <p className="text-muted-fog"><span className="text-nuxt-signal">L{t.depth_level}</span> {t.question_text}</p>
                </li>
              ))}
              <div ref={logEndRef} />
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
