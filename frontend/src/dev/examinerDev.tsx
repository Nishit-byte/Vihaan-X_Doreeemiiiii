/**
 * M3 Voice Pipeline — Examiner Dev Harness Page (Task B2)
 *
 * Standalone harness running at http://localhost:5173/examiner-dev.html
 * - 65% left placeholder ('Workspace — M4') with code preview of utils/similarity.py
 * - 35% right column mounting ExaminerPanel
 * - Collapsible debug drawer with:
 *     1. 🎙️ Task B2: Recorder Debug box (status, live level bar, last clip metadata,
 *        play-back button via object URL, and Space inside input test)
 *     2. Mock turn stepping & viva flow simulation
 *     3. Turn JSON inspector and event action logs
 */

import React, { useCallback, useEffect, useRef, useState, useTransition } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import ExaminerPanel, { PanelState, VoiceOrb } from '../components/ExaminerPanel'
import { MOCK_TURNS } from './mockTurns'
import type { TurnResponse } from '../types/api'
import {
  RecordedAudio,
  RecorderStatus,
  AudioPlayback,
  usePushToTalkRecorder,
  playBase64Audio,
  speakWithBrowserTTS,
  stopAllPlayback,
  unlockAudio,
  blobToBase64,
  getPreferredTTSVoice,
} from '../services/audioRecorder'

// Mock code for utils/similarity.py to illustrate M4 workspace sync
const SIMILARITY_PY_CODE = `"""Vector similarity computation utilities."""
import math
from typing import Sequence, Dict

def dot_product(u: Sequence[float], v: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(u, v))

def l2_norm(vec: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in vec))

def cosine_similarity(u: Sequence[float], v: Sequence[float]) -> float:
    """Computes standard cosine similarity between two dense vectors."""
    norm_u = l2_norm(u)
    norm_v = l2_norm(v)
    if norm_u < 1e-12 or norm_v < 1e-12:
        return 0.0
    return dot_product(u, v) / (norm_u * norm_v)

def normalize_vector(vec: Sequence[float]) -> list[float]:
    """L2-normalizes vector to unit length with zero-division safeguard."""
    norm = l2_norm(vec)
    if norm < 1e-12:
        return [0.0] * len(vec)
    return [x / norm for x in vec]

def batch_cosine_similarity(
    query: Sequence[float],
    corpus: Sequence[Sequence[float]],
    streaming: bool = False
) -> list[float]:
    """Computes similarity for a query against a large embedding matrix.
    
    Trade-off: In-memory matrix vs chunked streaming for 50k+ vectors.
    """
    if streaming:
        return [cosine_similarity(query, doc) for doc in corpus]
    q_norm = normalize_vector(query)
    return [dot_product(q_norm, normalize_vector(doc)) for doc in corpus]

def dot_product_fp16(u: Sequence[float], v: Sequence[float]) -> float:
    """Accumulates half-precision float16 products into float32."""
    acc = 0.0
    for a, b in zip(u, v):
        acc += float(a) * float(b)
    return float(acc)

def sparse_cosine_similarity(
    vec_a: Dict[int, float],
    vec_b: Dict[int, float]
) -> float:
    """Calculates cosine similarity over sparse dictionary embeddings."""
    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not common_keys:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common_keys)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return dot / (norm_a * norm_b)
`

/**
 * Real-time audio level bar driven by AnalyserNode without React re-render overhead
 */
function LiveLevelBar({ getInputLevel }: { getInputLevel: () => number }) {
  const barRef = useRef<HTMLDivElement>(null)
  const pctRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    let animId: number
    const update = () => {
      const level = getInputLevel()
      const pct = Math.min(100, Math.max(0, Math.round(level * 100)))
      if (barRef.current) {
        barRef.current.style.width = `${pct}%`
        barRef.current.className = `h-full rounded-full transition-all duration-75 ${
          pct > 50 ? 'bg-amber-400' : 'bg-nuxt-signal'
        }`
      }
      if (pctRef.current) {
        pctRef.current.textContent = `${pct}%`
      }
      animId = requestAnimationFrame(update)
    }
    animId = requestAnimationFrame(update)
    return () => cancelAnimationFrame(animId)
  }, [getInputLevel])

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-3.5 bg-void-canvas rounded-full overflow-hidden border border-steel-outline p-0.5">
        <div
          ref={barRef}
          className="h-full bg-nuxt-signal rounded-full transition-all duration-75"
          style={{ width: '0%' }}
        />
      </div>
      <span ref={pctRef} className="font-mono text-[11px] text-muted-fog w-9 text-right font-semibold">
        0%
      </span>
    </div>
  )
}

/**
 * Real-time level meter specifically for Task B5 Voice Orb displaying amplitude & numeric readout
 */
function LiveOrbLevelMeter({
  getLevel,
  mode,
}: {
  getLevel: () => number
  mode: 'fake' | 'mic' | 'playback'
}) {
  const barRef = useRef<HTMLDivElement>(null)
  const pctRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    let animId: number
    const update = () => {
      const level = getLevel()
      const pct = Math.min(100, Math.max(0, Math.round(level * 100)))
      if (barRef.current) {
        barRef.current.style.width = `${pct}%`
        barRef.current.className = `h-full rounded-full transition-all duration-75 ${
          mode === 'playback'
            ? 'bg-gradient-to-r from-indigo-500 to-purple-400'
            : mode === 'mic'
            ? 'bg-emerald-400'
            : 'bg-nuxt-signal'
        }`
      }
      if (pctRef.current) {
        pctRef.current.textContent = `${pct}% (${level.toFixed(2)})`
      }
      animId = requestAnimationFrame(update)
    }
    animId = requestAnimationFrame(update)
    return () => cancelAnimationFrame(animId)
  }, [getLevel, mode])

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-3.5 bg-void-canvas rounded-full overflow-hidden border border-steel-outline p-0.5">
        <div
          ref={barRef}
          className="h-full bg-nuxt-signal rounded-full transition-all duration-75"
          style={{ width: '0%' }}
        />
      </div>
      <span ref={pctRef} className="font-mono text-[11px] text-muted-fog w-20 text-right font-semibold">
        0% (0.00)
      </span>
    </div>
  )
}

/**
 * Status indicator pill for the recorder
 */
function RecorderStatusPill({ status }: { status: RecorderStatus }) {
  switch (status) {
    case 'idle':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-deep-slate text-pale-frost border border-steel-outline">
          <span className="h-2 w-2 rounded-full bg-blue-steel" />
          Idle (Ready)
        </span>
      )
    case 'requesting-permission':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-amber-950 text-amber-300 border border-amber-600 animate-pulse">
          <span className="h-2 w-2 rounded-full bg-amber-400" />
          Requesting Mic…
        </span>
      )
    case 'recording':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-red-950 text-red-300 border border-red-600 animate-pulse">
          <span className="h-2 w-2 rounded-full bg-red-500 animate-ping" />
          Recording (Space held)
        </span>
      )
    case 'denied':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-red-950 text-red-300 border border-red-600">
          <span className="h-2 w-2 rounded-full bg-red-600" />
          Mic Denied
        </span>
      )
    case 'unsupported':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-purple-950 text-purple-300 border border-purple-600">
          <span className="h-2 w-2 rounded-full bg-purple-400" />
          Unsupported
        </span>
      )
    case 'error':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-red-950 text-red-300 border border-red-600">
          <span className="h-2 w-2 rounded-full bg-red-600" />
          Error
        </span>
      )
  }
}

/**
 * Generates an in-memory 1.0s WAV audio chime (PCM 16-bit 22.05kHz) as clean base64
 * for instant one-click playback testing.
 */
function getTestChimeBase64(): string {
  const sampleRate = 22050
  const duration = 1.0
  const numSamples = Math.floor(sampleRate * duration)
  const buffer = new ArrayBuffer(44 + numSamples * 2)
  const view = new DataView(buffer)

  function writeString(offset: number, str: string) {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i))
    }
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + numSamples * 2, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, numSamples * 2, true)

  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate
    const env = Math.exp(-2.5 * t)
    const sample =
      (0.5 * Math.sin(2 * Math.PI * 440 * t) +
        0.3 * Math.sin(2 * Math.PI * 554.37 * t) +
        0.2 * Math.sin(2 * Math.PI * 659.25 * t)) *
      env
    const intSample = Math.max(-32768, Math.min(32767, Math.floor(sample * 24000)))
    view.setInt16(44 + i * 2, intSample, true)
  }

  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

/**
 * Real-time playback amplitude level bar (0..1 RMS) driven by AudioPlayback.getLevel()
 */
function LivePlaybackLevelBar({
  getPlaybackLevel,
  isTTS,
}: {
  getPlaybackLevel: () => number
  isTTS: boolean
}) {
  const barRef = useRef<HTMLDivElement>(null)
  const pctRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    let animId: number
    const update = () => {
      const level = getPlaybackLevel()
      const pct = Math.min(100, Math.max(0, Math.round(level * 100)))
      if (barRef.current) {
        barRef.current.style.width = `${pct}%`
        barRef.current.className = `h-full rounded-full transition-all duration-75 ${
          isTTS
            ? 'bg-gradient-to-r from-indigo-500 to-purple-400'
            : pct > 50
            ? 'bg-amber-400'
            : 'bg-nuxt-signal'
        }`
      }
      if (pctRef.current) {
        pctRef.current.textContent = `${pct}%`
      }
      animId = requestAnimationFrame(update)
    }
    animId = requestAnimationFrame(update)
    return () => cancelAnimationFrame(animId)
  }, [getPlaybackLevel, isTTS])

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-3.5 bg-void-canvas rounded-full overflow-hidden border border-steel-outline p-0.5">
        <div
          ref={barRef}
          className="h-full bg-nuxt-signal rounded-full transition-all duration-75"
          style={{ width: '0%' }}
        />
      </div>
      <span ref={pctRef} className="font-mono text-[11px] text-muted-fog w-9 text-right font-semibold">
        0%
      </span>
    </div>
  )
}

/**
 * Real-time playback progress bar (0..1) driven by AudioPlayback.getProgress()
 */
function LivePlaybackProgressBar({
  getPlaybackProgress,
  isPlaying,
}: {
  getPlaybackProgress: () => number
  isPlaying: boolean
}) {
  const barRef = useRef<HTMLDivElement>(null)
  const pctRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    let animId: number
    const update = () => {
      const progress = getPlaybackProgress()
      const pct = Math.min(100, Math.max(0, Math.round(progress * 100)))
      if (barRef.current) {
        barRef.current.style.width = `${pct}%`
        barRef.current.className = `h-full rounded-full transition-all duration-75 ${
          isPlaying ? 'bg-nuxt-signal' : 'bg-steel-outline'
        }`
      }
      if (pctRef.current) {
        pctRef.current.textContent = `${pct}%`
      }
      animId = requestAnimationFrame(update)
    }
    animId = requestAnimationFrame(update)
    return () => cancelAnimationFrame(animId)
  }, [getPlaybackProgress, isPlaying])

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-3.5 bg-void-canvas rounded-full overflow-hidden border border-steel-outline p-0.5">
        <div
          ref={barRef}
          className="h-full bg-nuxt-signal rounded-full transition-all duration-75"
          style={{ width: '0%' }}
        />
      </div>
      <span ref={pctRef} className="font-mono text-[11px] text-muted-fog w-9 text-right font-semibold">
        0%
      </span>
    </div>
  )
}

/**
 * Status indicator pill for active audio playback / browser TTS
 */
function PlaybackStatusPill({
  state,
}: {
  state: 'idle' | 'playing-audio' | 'speaking-tts'
}) {
  switch (state) {
    case 'idle':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-deep-slate text-pale-frost border border-steel-outline">
          <span className="h-2 w-2 rounded-full bg-blue-steel" />
          Idle (No Playback)
        </span>
      )
    case 'playing-audio':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-emerald-950 text-emerald-300 border border-emerald-600 animate-pulse">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
          Playing MP3 / Web Audio
        </span>
      )
    case 'speaking-tts':
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-indigo-950 text-indigo-300 border border-indigo-600 animate-pulse">
          <span className="h-2 w-2 rounded-full bg-indigo-400 animate-ping" />
          Speaking (Browser TTS)
        </span>
      )
  }
}

function ExaminerDevHarness() {
  const queryParams = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null
  const paramTurn = queryParams?.get('turn')
    ? Math.max(0, Math.min(Number(queryParams.get('turn')), MOCK_TURNS.length - 1))
    : 0
  const paramState = queryParams?.get('state') as PanelState | null

  const [turnIndex, setTurnIndex] = useState(paramTurn)
  const turnIndexRef = useRef(turnIndex)
  turnIndexRef.current = turnIndex

  const [currentTurn, setCurrentTurn] = useState<TurnResponse>(MOCK_TURNS[paramTurn])
  const [history, setHistory] = useState<TurnResponse[]>(MOCK_TURNS.slice(0, paramTurn + 1))
  const [forcedState, setForcedState] = useState<PanelState | undefined>(paramState ?? undefined)
  const [simulatedDelayMs, setSimulatedDelayMs] = useState(900)
  const simulatedDelayMsRef = useRef(simulatedDelayMs)
  simulatedDelayMsRef.current = simulatedDelayMs

  // Mode: Live Backend (port 8000) vs Offline Mock (defaults to Live Backend)
  const [backendMode, setBackendMode] = useState<'live' | 'mock'>('live')
  const backendModeRef = useRef<'live' | 'mock'>('live')
  backendModeRef.current = backendMode

  const [backendError, setBackendError] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string>(() => `dev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`)
  const sessionIdRef = useRef(sessionId)
  sessionIdRef.current = sessionId

  // Single unified failure simulation state & ref (single source of truth)
  const [simulateFailure, setSimulateFailure] = useState(false)
  const simulateFailureRef = useRef(false)
  simulateFailureRef.current = simulateFailure

  const handleToggleFailure = useCallback((checked: boolean) => {
    simulateFailureRef.current = checked
    setSimulateFailure(checked)
    logAction(`Simulate failure set to: ${checked ? 'ON' : 'OFF'}`)
  }, [])
  const [debugDrawerOpen, setDebugDrawerOpen] = useState(false)
  const [actionLog, setActionLog] = useState<string[]>([
    'Dev harness mounted. Mode: Live Backend (port 8000).',
    'Task B6 autonomous turn-flow wired to ExaminerPanel.',
  ])
  const [, startTransition] = useTransition()

  // B2 Recorder debug state
  const [lastClip, setLastClip] = useState<RecordedAudio | null>(null)
  const [lastAudioUrl, setLastAudioUrl] = useState<string | null>(null)
  const [tooShortNotice, setTooShortNotice] = useState(false)
  const [testInputText, setTestInputText] = useState('')
  const [autoSubmitViva, setAutoSubmitViva] = useState(false)

  // B3 Playback & Browser TTS debug state
  const [playbackState, setPlaybackState] = useState<'idle' | 'playing-audio' | 'speaking-tts'>('idle')
  const [playbackSource, setPlaybackSource] = useState('')
  const [ttsInputText, setTtsInputText] = useState(
    'Good point on cosine similarity. How does your implementation handle sparse embeddings?'
  )
  const [selectedAudioFile, setSelectedAudioFile] = useState<{
    name: string
    size: number
    mimeType: string
    base64: string
  } | null>(null)
  const [detectedVoiceLabel, setDetectedVoiceLabel] = useState('Detecting voice...')
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const activePlaybackRef = useRef<AudioPlayback | null>(null)

  // B5 Voice Orb level source & fake level state
  const [orbLevelMode, setOrbLevelMode] = useState<'fake' | 'mic' | 'playback'>('fake')
  const [fakeOrbLevel, setFakeOrbLevel] = useState<number>(0.45)
  const orbLevelModeRef = useRef(orbLevelMode)
  orbLevelModeRef.current = orbLevelMode
  const fakeOrbLevelRef = useRef(fakeOrbLevel)
  fakeOrbLevelRef.current = fakeOrbLevel

  // Detect preferred TTS voice on load and voice change
  useEffect(() => {
    const updateVoiceLabel = () => {
      const v = getPreferredTTSVoice()
      if (v) {
        setDetectedVoiceLabel(`${v.name} (${v.lang})`)
      } else {
        setDetectedVoiceLabel('Browser Default (en-US fallback)')
      }
    }
    updateVoiceLabel()
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.addEventListener('voiceschanged', updateVoiceLabel)
      return () => {
        window.speechSynthesis.removeEventListener('voiceschanged', updateVoiceLabel)
      }
    }
  }, [])

  // Clean up any active playback on harness unmount
  useEffect(() => {
    return () => {
      stopAllPlayback()
    }
  }, [])

  const logAction = (msg: string) => {
    setActionLog((prev) => [
      `[${new Date().toLocaleTimeString()}] ${msg}`,
      ...prev.slice(0, 19),
    ])
  }

  // Hook instance under test (Task B2 debug box)
  // IMPORTANT (from B2 review & B6 spec): bindSpacebar: false so pressing Space does not start two recordings!
  const recorder = usePushToTalkRecorder({
    enabled: true,
    bindSpacebar: false,
    minDurationMs: 300,
    maxDurationMs: 60000,
    onRecordingComplete: (rec) => {
      setLastClip(rec)
      const url = URL.createObjectURL(rec.blob)
      setLastAudioUrl(url)
      logAction(
        `🎙️ Clip captured: ${rec.durationMs}ms, ${(rec.blob.size / 1024).toFixed(1)}KB, ${rec.mimeType}, b64 len=${rec.base64.length}`
      )
      if (autoSubmitViva) {
        void handleMockAudioSubmit(rec)
      }
    },
    onTooShort: () => {
      setTooShortNotice(true)
      logAction('⚠️ Discarded: clip shorter than 300ms (onTooShort)')
      setTimeout(() => setTooShortNotice(false), 2500)
    },
  })

  // Reactive level source for VoiceOrb (Task B5)
  const getActiveOrbLevel = useCallback((): number => {
    if (orbLevelModeRef.current === 'mic') {
      return recorder.getInputLevel()
    }
    if (orbLevelModeRef.current === 'playback') {
      return activePlaybackRef.current ? activePlaybackRef.current.getLevel() : 0
    }
    return fakeOrbLevelRef.current
  }, [recorder])

  // Revoke the previous clip URL on replace and on unmount
  useEffect(() => {
    return () => {
      if (lastAudioUrl) URL.revokeObjectURL(lastAudioUrl)
    }
  }, [lastAudioUrl])

  const goToTurn = (index: number) => {
    const clamped = Math.max(0, Math.min(index, MOCK_TURNS.length - 1))
    turnIndexRef.current = clamped
    setTurnIndex(clamped)
    setCurrentTurn(MOCK_TURNS[clamped])
    setHistory(MOCK_TURNS.slice(0, clamped + 1))
    logAction(
      `Jumped to Turn ${clamped + 1}: L${MOCK_TURNS[clamped].depth_level} (${MOCK_TURNS[clamped].verdict})`
    )
  }

  const handleNextTurn = () => {
    goToTurn(turnIndex + 1)
  }

  const handlePrevTurn = () => {
    goToTurn(turnIndex - 1)
  }

  // Task B3 Playback & Browser TTS Handlers
  const handleSelectAudioFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const base64 = await blobToBase64(file)
      setSelectedAudioFile({
        name: file.name,
        size: file.size,
        mimeType: file.type || 'audio/mpeg',
        base64,
      })
      logAction(`📁 Loaded audio file: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`)
    } catch (err) {
      logAction(`❌ Failed to read audio file: ${err}`)
    }
  }

  const handlePlaySelectedFile = () => {
    if (!selectedAudioFile) return
    unlockAudio()
    setPlaybackState('playing-audio')
    setPlaybackSource(selectedAudioFile.name)
    logAction(`🔊 Starting Web Audio playback for "${selectedAudioFile.name}"...`)
    const pb = playBase64Audio(selectedAudioFile.base64, selectedAudioFile.mimeType)
    activePlaybackRef.current = pb
    pb.done.then(() => {
      logAction(`🔊 Web Audio playback completed for "${selectedAudioFile.name}"`)
      setPlaybackState('idle')
      setPlaybackSource('')
    })
  }

  const handlePlaySampleChime = () => {
    unlockAudio()
    const b64 = getTestChimeBase64()
    setPlaybackState('playing-audio')
    setPlaybackSource('Sample Chord Chime (1.0s WAV)')
    logAction('🎵 Playing sample chord chime (1.0s WAV) via Web Audio API...')
    const pb = playBase64Audio(b64, 'audio/wav')
    activePlaybackRef.current = pb
    pb.done.then(() => {
      logAction('🎵 Sample chord chime playback completed')
      setPlaybackState('idle')
      setPlaybackSource('')
    })
  }

  const handleSpeakTTS = (textToSpeak?: string) => {
    const text = textToSpeak || ttsInputText
    if (!text.trim()) return
    unlockAudio()
    setPlaybackState('speaking-tts')
    setPlaybackSource(`TTS: "${text.slice(0, 35)}..."`)
    logAction(`🗣️ Started Browser TTS speaking: "${text.slice(0, 50)}..."`)
    const pb = speakWithBrowserTTS(text)
    activePlaybackRef.current = pb
    pb.done.then(() => {
      logAction('🗣️ Browser TTS speaking completed')
      setPlaybackState('idle')
      setPlaybackSource('')
    })
  }

  const handleStopPlayback = () => {
    logAction('⏹️ Stop playback called — stopping all active audio and TTS')
    stopAllPlayback()
    activePlaybackRef.current = null
    setPlaybackState('idle')
    setPlaybackSource('')
  }

  const handleTestMidPlayStop = () => {
    logAction('🧪 Running test: Mid-play stop() after 500ms...')
    handlePlaySampleChime()
    setTimeout(() => {
      logAction('🧪 Triggering stop() mid-play at 500ms...')
      handleStopPlayback()
    }, 500)
  }

  const handleTestOverlap = () => {
    logAction('🧪 Running test: Starting audio then TTS immediately (second stops first)...')
    handlePlaySampleChime()
    setTimeout(() => {
      logAction('🧪 Starting TTS while audio is playing (must stop audio)...')
      handleSpeakTTS('Second playback successfully stopped the first audio!')
    }, 200)
  }

  // Live Backend (port 8000) Start Turn Fetcher
  const fetchLiveStartTurn = useCallback(async (sid?: string) => {
    const targetSid = sid || `dev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
    setSessionId(targetSid)
    sessionIdRef.current = targetSid
    setBackendError(null)
    logAction(`📡 Fetching start turn from http://localhost:8000/api/dev/start?session_id=${targetSid}...`)
    try {
      const res = await fetch(`http://localhost:8000/api/dev/start?session_id=${encodeURIComponent(targetSid)}`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const data: TurnResponse = await res.json()
      setCurrentTurn(data)
      setHistory([data])
      setTurnIndex(0)
      turnIndexRef.current = 0
      setBackendError(null)
      logAction(`✅ Connected to Live Backend (port 8000). Loaded Q1: ${data.topic}`)
      return data
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      const friendlyMsg = `Cannot connect to Live Backend at http://localhost:8000 (${msg}). Make sure dev_server is running on port 8000 or switch to Offline Mock.`
      setBackendError(friendlyMsg)
      logAction(`⚠️ ${friendlyMsg}`)
      setCurrentTurn(MOCK_TURNS[0])
      setHistory([MOCK_TURNS[0]])
      setTurnIndex(0)
      turnIndexRef.current = 0
      return null
    }
  }, [])

  // Auto-fetch start turn in live mode on mount
  useEffect(() => {
    if (backendModeRef.current === 'live') {
      void fetchLiveStartTurn(sessionIdRef.current)
    }
  }, [fetchLiveStartTurn])

  const handleSwitchMode = useCallback((mode: 'live' | 'mock') => {
    setBackendMode(mode)
    backendModeRef.current = mode
    if (mode === 'live') {
      logAction('Mode switched to: Live Backend (port 8000)')
      void fetchLiveStartTurn()
    } else {
      setBackendError(null)
      setCurrentTurn(MOCK_TURNS[0])
      setHistory([MOCK_TURNS[0]])
      setTurnIndex(0)
      turnIndexRef.current = 0
      logAction('Mode switched to: Offline Mock')
    }
  }, [fetchLiveStartTurn])

  const handleRestartSession = useCallback(() => {
    if (backendModeRef.current === 'live') {
      const newSid = `dev-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
      logAction(`🔄 Restarting Live Backend session (${newSid})...`)
      void fetchLiveStartTurn(newSid)
    } else {
      logAction('🔄 Restarting Offline Mock session (Turn 1)...')
      setTurnIndex(0)
      turnIndexRef.current = 0
      setCurrentTurn(MOCK_TURNS[0])
      setHistory([MOCK_TURNS[0]])
    }
  }, [fetchLiveStartTurn])

  // ExaminerPanel callbacks supporting Live Backend (port 8000) and Offline Mock fallback
  // Wrapped in useCallback with stable references; reads simulateFailureRef & turnIndexRef via refs
  const handleMockAudioSubmit = useCallback(async (
    rec: RecordedAudio
  ): Promise<TurnResponse> => {
    const startTime = performance.now()
    logAction(`onSubmitAudio: ${rec.durationMs}ms, ${rec.mimeType}, size=${rec.base64.length}b64`)

    if (simulateFailureRef.current) {
      logAction('❌ Simulated submission failure triggered (500 Error)')
      throw new Error('Simulated network error: POST /api/viva/turn failed (500)')
    }

    if (backendModeRef.current === 'live') {
      const sid = sessionIdRef.current
      logAction(`📡 POST http://localhost:8000/api/viva/turn (audio, session ${sid})...`)
      let res: Response
      try {
        res = await fetch('http://localhost:8000/api/viva/turn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sid,
            audio_base64: rec.base64,
            audio_mime: rec.mimeType,
          }),
        })
      } catch (netErr: unknown) {
        const netMsg = netErr instanceof Error ? netErr.message : String(netErr)
        throw new Error(`Network error connecting to port 8000: ${netMsg}`)
      }

      if (!res.ok) {
        const errDetail = await res.json().catch(() => ({ detail: res.statusText }))
        const detailStr =
          typeof errDetail.detail === 'string'
            ? errDetail.detail
            : JSON.stringify(errDetail.detail || res.statusText)
        logAction(`❌ Backend returned HTTP ${res.status}: ${detailStr}`)
        throw new Error(`HTTP ${res.status}: ${detailStr}`)
      }

      const turnData: TurnResponse = await res.json()
      const latencyMs = Math.round(performance.now() - startTime)
      logAction(`✅ Audio turn response received in ${latencyMs}ms! Verdict: ${turnData.verdict}, Depth: L${turnData.depth_level}`)
      console.log(`[Release -> Response Latency: ${latencyMs}ms] Verdict: ${turnData.verdict}`)

      startTransition(() => {
        setCurrentTurn(turnData)
        setHistory((prev) => [...prev, turnData])
        const nextIdx = turnIndexRef.current + 1
        turnIndexRef.current = nextIdx
        setTurnIndex(nextIdx)
      })
      return turnData
    } else {
      const delay = simulatedDelayMsRef.current
      if (delay > 0) {
        await new Promise((resolve) => setTimeout(resolve, delay))
      }
      const currentIdx = turnIndexRef.current
      const nextIdx = Math.min(currentIdx + 1, MOCK_TURNS.length - 1)
      const next = MOCK_TURNS[nextIdx]
      turnIndexRef.current = nextIdx
      startTransition(() => {
        setTurnIndex(nextIdx)
        setCurrentTurn(next)
        setHistory(MOCK_TURNS.slice(0, nextIdx + 1))
      })
      return next
    }
  }, [])

  const handleMockTextSubmit = useCallback(async (
    text: string
  ): Promise<TurnResponse> => {
    const startTime = performance.now()
    logAction(`onSubmitText: "${text}"`)

    if (simulateFailureRef.current) {
      logAction('❌ Simulated submission failure triggered (500 Error)')
      throw new Error('Simulated network error: POST /api/viva/turn failed (500)')
    }

    if (backendModeRef.current === 'live') {
      const sid = sessionIdRef.current
      logAction(`📡 POST http://localhost:8000/api/viva/turn (text, session ${sid})...`)
      let res: Response
      try {
        res = await fetch('http://localhost:8000/api/viva/turn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sid,
            student_text: text,
          }),
        })
      } catch (netErr: unknown) {
        const netMsg = netErr instanceof Error ? netErr.message : String(netErr)
        throw new Error(`Network error connecting to port 8000: ${netMsg}`)
      }

      if (!res.ok) {
        const errDetail = await res.json().catch(() => ({ detail: res.statusText }))
        const detailStr =
          typeof errDetail.detail === 'string'
            ? errDetail.detail
            : JSON.stringify(errDetail.detail || res.statusText)
        logAction(`❌ Backend returned HTTP ${res.status}: ${detailStr}`)
        throw new Error(`HTTP ${res.status}: ${detailStr}`)
      }

      const turnData: TurnResponse = await res.json()
      const latencyMs = Math.round(performance.now() - startTime)
      logAction(`✅ Text turn response received in ${latencyMs}ms! Verdict: ${turnData.verdict}, Depth: L${turnData.depth_level}`)

      startTransition(() => {
        setCurrentTurn(turnData)
        setHistory((prev) => [...prev, turnData])
        const nextIdx = turnIndexRef.current + 1
        turnIndexRef.current = nextIdx
        setTurnIndex(nextIdx)
      })
      return turnData
    } else {
      const delay = simulatedDelayMsRef.current
      if (delay > 0) {
        await new Promise((resolve) => setTimeout(resolve, delay))
      }
      const currentIdx = turnIndexRef.current
      const nextIdx = Math.min(currentIdx + 1, MOCK_TURNS.length - 1)
      const next = MOCK_TURNS[nextIdx]
      turnIndexRef.current = nextIdx
      startTransition(() => {
        setTurnIndex(nextIdx)
        setCurrentTurn(next)
        setHistory(MOCK_TURNS.slice(0, nextIdx + 1))
      })
      return next
    }
  }, [])

  const handleTurnUpdate = (turn: TurnResponse) => {
    logAction(`onTurn callback: L${turn.depth_level} - ${turn.topic}`)
    setCurrentTurn(turn)
    if (backendModeRef.current === 'mock') {
      const idx = MOCK_TURNS.findIndex(
        (t) => t.topic === turn.topic && t.depth_level === turn.depth_level
      )
      if (idx !== -1) {
        turnIndexRef.current = idx
        setTurnIndex(idx)
        setHistory(MOCK_TURNS.slice(0, idx + 1))
      }
    }
  }

  const handleRequestReport = () => {
    logAction('onRequestReport invoked! (Viva completed)')
    alert('Viva Report Requested! In full app, M4 opens ReportModal.')
  }

  // Highlight lines calculation for mock workspace
  const codeLines = SIMILARITY_PY_CODE.split('\n')
  const highlightStart = currentTurn.highlight?.line_start ?? -1
  const highlightEnd = currentTurn.highlight?.line_end ?? -1

  return (
    <div
      className="flex flex-col min-h-screen w-full bg-void-canvas text-pale-frost font-sans overflow-x-hidden"
      onPointerDown={() => unlockAudio()}
    >
      {/* Dev Harness Navigation Bar (Sticky with Quick Controls) */}
      <header className="sticky top-0 z-30 flex shrink-0 items-center justify-between border-b border-steel-outline bg-midnight-panel/95 backdrop-blur px-4 py-2 text-xs flex-wrap gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="font-bold text-signal-white text-sm tracking-wide">
            VivaVoce
          </span>
          <span className="rounded bg-deep-slate px-2 py-0.5 font-mono text-[11px] text-nuxt-signal border border-steel-outline">
            examiner-dev.html (M3)
          </span>

          {/* Mode Switcher: Live Backend (port 8000) vs Offline Mock */}
          <div className="flex items-center gap-0.5 bg-void-canvas p-0.5 rounded border border-steel-outline text-xs">
            <button
              type="button"
              onClick={() => handleSwitchMode('live')}
              className={`rounded px-2.5 py-1 text-[11px] font-medium transition ${
                backendMode === 'live'
                  ? 'bg-emerald-600 text-white font-bold shadow-sm'
                  : 'text-muted-fog hover:text-pale-frost hover:bg-deep-slate'
              }`}
            >
              Live Backend (port 8000)
            </button>
            <button
              type="button"
              onClick={() => handleSwitchMode('mock')}
              className={`rounded px-2.5 py-1 text-[11px] font-medium transition ${
                backendMode === 'mock'
                  ? 'bg-nuxt-signal text-void-canvas font-bold shadow-sm'
                  : 'text-muted-fog hover:text-pale-frost hover:bg-deep-slate'
              }`}
            >
              Offline Mock
            </button>
          </div>

          {/* New Session / Restart Button */}
          <button
            type="button"
            onClick={handleRestartSession}
            className="rounded bg-deep-slate hover:bg-steel-outline text-signal-white border border-steel-outline px-2.5 py-1 text-[11px] font-medium transition flex items-center gap-1.5 active:scale-95"
            title="Reset and start a new viva session"
          >
            <span>🔄</span>
            <span>New Session / Restart</span>
          </button>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          {/* Quick Simulate Failure Toggle */}
          <div className="flex items-center gap-1.5 text-[11px] text-red-300 font-medium bg-red-950/60 px-2 py-0.5 rounded border border-red-700/60 select-none">
            <input
              id="header-simulate-failure-checkbox"
              type="checkbox"
              checked={simulateFailure}
              onChange={(e) => {
                const checked = e.target.checked
                handleToggleFailure(checked)
                e.currentTarget.blur()
              }}
              className="accent-red-500 rounded cursor-pointer"
            />
            <label htmlFor="header-simulate-failure-checkbox" className="cursor-pointer">
              Simulate Failure
            </label>
          </div>
          {/* Quick B5 Orb State Switcher */}
          <div className="flex items-center gap-1 bg-void-canvas px-2 py-0.5 rounded border border-steel-outline text-xs">
            <span className="text-muted-fog text-[10px] font-semibold uppercase tracking-wider">Orb State:</span>
            {(['auto', 'idle', 'listening', 'thinking', 'speaking', 'done'] as const).map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => {
                  const target = st === 'auto' ? undefined : st
                  setForcedState(target)
                  logAction(`Panel state forced to: ${st.toUpperCase()}`)
                }}
                className={`rounded px-1.5 py-0.5 text-[10px] font-medium transition ${
                  (st === 'auto' && forcedState === undefined) || forcedState === st
                    ? 'bg-nuxt-signal text-void-canvas font-bold'
                    : 'text-muted-fog hover:text-pale-frost hover:bg-deep-slate'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Quick Level Mode Switcher */}
          <div className="flex items-center gap-1 bg-void-canvas px-2 py-0.5 rounded border border-steel-outline text-xs">
            <span className="text-muted-fog text-[10px] font-semibold uppercase tracking-wider">Source:</span>
            {(['fake', 'mic', 'playback'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => {
                  setOrbLevelMode(mode)
                  orbLevelModeRef.current = mode
                  logAction(`Orb level mode set to: ${mode}`)
                }}
                className={`rounded px-1.5 py-0.5 text-[10px] font-medium transition uppercase ${
                  orbLevelMode === mode
                    ? 'bg-nuxt-signal text-void-canvas font-bold'
                    : 'text-muted-fog hover:text-pale-frost hover:bg-deep-slate'
                }`}
              >
                {mode}
              </button>
            ))}
          </div>

          {/* Mini slider in header when in fake mode */}
          {orbLevelMode === 'fake' && (
            <div className="flex items-center gap-1.5 bg-void-canvas px-2 py-0.5 rounded border border-steel-outline text-xs">
              <span className="text-muted-fog text-[10px] font-mono">Level:</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={fakeOrbLevel}
                onChange={(e) => {
                  const val = Number(e.target.value)
                  setFakeOrbLevel(val)
                  fakeOrbLevelRef.current = val
                }}
                className="w-16 sm:w-20 h-2 accent-nuxt-signal cursor-pointer"
                title={`Fake Level: ${fakeOrbLevel.toFixed(2)}`}
              />
              <span className="font-mono text-[10px] text-signal-white font-semibold w-7">
                {fakeOrbLevel.toFixed(2)}
              </span>
            </div>
          )}

          {/* Jump to Dev Controls */}
          <a
            href="#dev-controls"
            className="rounded bg-deep-slate px-2.5 py-1 text-[11px] font-medium text-pale-frost hover:bg-steel-outline hover:text-signal-white border border-steel-outline transition"
          >
            ⬇ Dev Controls
          </a>
        </div>
      </header>

      {/* Port 8000 Unreachable Inline Dev Warning Banner */}
      {backendMode === 'live' && backendError && (
        <div className="w-full bg-amber-950/90 border-b border-amber-600 px-4 py-2 text-xs text-amber-200 flex items-center justify-between gap-3 flex-wrap animate-fadeIn">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-amber-400 font-bold text-sm select-none">⚠️</span>
            <span className="truncate">{backendError}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => handleSwitchMode('mock')}
              className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-500 text-void-canvas font-semibold text-[11px] transition shadow"
            >
              Switch to Offline Mock
            </button>
            <button
              type="button"
              onClick={() => void fetchLiveStartTurn()}
              className="px-2.5 py-1 rounded bg-deep-slate hover:bg-steel-outline text-pale-frost border border-amber-600/60 text-[11px] transition"
            >
              Retry Connection
            </button>
          </div>
        </div>
      )}

      {/* Main Split View: 65% Workspace Placeholder | 35% ExaminerPanel */}
      <main className="flex flex-col lg:flex-row w-full h-[620px] shrink-0 border-b border-steel-outline bg-void-canvas">
        {/* Left 65%: Workspace Placeholder (M4 IDE Simulation) */}
        <section
          className="flex min-w-0 lg:basis-[65%] flex-col border-b lg:border-b-0 lg:border-r border-steel-outline bg-void-canvas h-full overflow-hidden"
          aria-label="Workspace — M4"
        >
          {/* Workspace Tabs Header */}
          <div className="flex shrink-0 items-center justify-between border-b border-steel-outline bg-midnight-panel px-4 py-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-signal-white">
                Workspace — M4
              </span>
              <span className="rounded bg-deep-slate px-2 py-0.5 text-[11px] text-muted-fog border border-steel-outline">
                {currentTurn.highlight?.file_path ?? 'utils/similarity.py'}
              </span>
              {highlightStart > 0 && (
                <span className="text-xs text-nuxt-signal font-mono">
                  [Lines {highlightStart}–{highlightEnd}]
                </span>
              )}
            </div>
            <span className="text-[11px] text-muted-fog">
              Read-only IDE mock • Synchronized with turn.highlight
            </span>
          </div>

          {/* Code Viewer */}
          <div className="flex-1 min-h-0 overflow-y-auto p-4 font-mono text-xs leading-5 bg-void-canvas">
            <table className="w-full border-collapse">
              <tbody>
                {codeLines.map((line, idx) => {
                  const lineNum = idx + 1
                  const isHighlighted =
                    highlightStart > 0 &&
                    lineNum >= highlightStart &&
                    lineNum <= highlightEnd

                  return (
                    <tr
                      key={lineNum}
                      className={`transition-colors ${
                        isHighlighted
                          ? 'bg-nuxt-signal/15 text-signal-white font-semibold'
                          : 'hover:bg-deep-slate/40 text-pale-frost'
                      }`}
                    >
                      <td className="w-12 select-none pr-4 text-right text-muted-fog/60 border-r border-steel-outline/60">
                        {lineNum}
                      </td>
                      <td className="pl-4 whitespace-pre">
                        {isHighlighted && (
                          <span className="inline-block w-2 text-nuxt-signal mr-1 select-none">
                            ▶
                          </span>
                        )}
                        {line}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>

        {/* Right 35%: ExaminerPanel Mount */}
        <aside
          className="min-w-0 lg:basis-[35%] flex flex-col h-full overflow-hidden bg-midnight-panel"
          aria-label="Examiner Panel"
        >
          <ExaminerPanel
            key={`${backendMode}-${sessionId}`}
            initialTurn={currentTurn}
            history={history}
            forceState={forcedState}
            levelSource={orbLevelMode === 'fake' ? getActiveOrbLevel : undefined}
            onSubmitAudio={handleMockAudioSubmit}
            onSubmitText={handleMockTextSubmit}
            onTurn={handleTurnUpdate}
            onRequestReport={handleRequestReport}
            fillersUrl={backendMode === 'live' ? 'http://localhost:8000/api/voice/fillers' : '/api/voice/fillers'}
            disabled={false}
          />
        </aside>
      </main>

      {/* Dev Controls Section (Always Visible & Accessible with Vertical Scroll) */}
      <section
        id="dev-controls"
        className="w-full shrink-0 bg-midnight-panel text-xs p-4 sm:p-6 space-y-6"
        aria-label="Dev Controls & Diagnostics"
      >
        <div className="flex items-center justify-between pb-3 border-b border-steel-outline flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <span className="font-bold text-signal-white text-sm tracking-wide">
              🛠️ M3 Voice Pipeline — Dev Test Controls
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono text-nuxt-signal bg-deep-slate border border-steel-outline">
              Mode: {backendMode === 'live' ? 'Live Backend (port 8000)' : 'Offline Mock'} • Session: {sessionId}
            </span>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5 text-xs text-red-300 hover:text-red-200 font-medium bg-red-950/40 px-2 py-1 rounded border border-red-800/60 select-none">
              <input
                id="dev-simulate-failure-checkbox"
                type="checkbox"
                checked={simulateFailure}
                onChange={(e) => {
                  const checked = e.target.checked
                  handleToggleFailure(checked)
                  e.currentTarget.blur()
                }}
                className="accent-red-500 rounded cursor-pointer"
              />
              <label htmlFor="dev-simulate-failure-checkbox" className="cursor-pointer">
                Simulate submit failure (tests Retry)
              </label>
            </div>
            <div className="h-4 w-px bg-steel-outline" />
            <label className="flex items-center gap-1.5 text-xs text-muted-fog cursor-pointer">
              <input
                type="checkbox"
                checked={autoSubmitViva}
                onChange={(e) => setAutoSubmitViva(e.target.checked)}
                className="accent-nuxt-signal rounded"
              />
              <span>Auto-advance viva on speech release</span>
            </label>
            <div className="h-4 w-px bg-steel-outline" />
            <span className="text-muted-fog">Simulate Latency:</span>
            <select
              value={simulatedDelayMs}
              onChange={(e) => setSimulatedDelayMs(Number(e.target.value))}
              className="rounded bg-void-canvas px-2 py-1 text-pale-frost border border-steel-outline text-xs"
            >
              <option value={0}>0ms (Instant)</option>
              <option value={400}>400ms (Fast)</option>
              <option value={900}>900ms (Spec default)</option>
              <option value={1500}>1500ms (Voice pipeline)</option>
              <option value={2500}>2500ms (Full LLM)</option>
            </select>
          </div>
        </div>

        {/* Section 1: 🔮 Task B5: Voice Orb Animation Controls */}
        <div className="rounded-lg border border-steel-outline bg-deep-slate/50 p-4 shadow-sm">
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-steel-outline/60 flex-wrap gap-2">
            <div className="flex items-center gap-2.5">
              <span className="font-bold text-signal-white text-sm tracking-tight flex items-center gap-1.5">
                🔮 Task B5: Voice Orb Animation Controls
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-deep-slate text-pale-frost border border-steel-outline">
                Active Source: <strong className="text-nuxt-signal uppercase font-mono">{orbLevelMode}</strong>
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-muted-fog">
              <span>Smoothed scale: <strong className="text-signal-white font-mono">1 + level * 0.35</strong> (lerp)</span>
              <span>•</span>
              <span>Canvas + rAF + High-DPI</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {/* Card 1: State Switcher */}
            <div className="flex flex-col gap-2.5 rounded bg-midnight-panel p-3 border border-steel-outline">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-signal-white">
                  Orb State Switcher
                </span>
                <span className="text-[10px] text-muted-fog">
                  Active: <strong className="text-nuxt-signal capitalize">{forcedState ?? (recorder.isRecording ? 'listening' : playbackState !== 'idle' ? 'speaking' : currentTurn.done ? 'done' : 'idle')}</strong>
                </span>
              </div>
              <p className="text-[11px] text-muted-fog leading-relaxed">
                Force VoiceOrb into any state to verify animations:
              </p>
              <div className="grid grid-cols-3 gap-1.5">
                {(['auto', 'idle', 'listening', 'thinking', 'speaking', 'done'] as const).map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => {
                      const target = st === 'auto' ? undefined : st
                      setForcedState(target)
                      logAction(`Voice Orb state switched to: ${st.toUpperCase()}`)
                    }}
                    className={`rounded py-1.5 px-2 text-[11px] font-mono border transition truncate ${
                      (st === 'auto' && forcedState === undefined) || forcedState === st
                        ? 'bg-nuxt-signal text-void-canvas font-bold border-nuxt-signal shadow-[0_0_8px_rgba(0,220,130,0.4)]'
                        : 'bg-void-canvas text-pale-frost border-steel-outline hover:bg-steel-outline hover:text-signal-white'
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>
              <div className="mt-auto pt-2 border-t border-steel-outline/40 text-[10px] text-muted-fog space-y-0.5">
                <div>• <strong className="text-pale-frost">idle</strong>: slow breathing slate/indigo</div>
                <div>• <strong className="text-emerald-400">listening</strong>: emerald mic reactive</div>
                <div>• <strong className="text-amber-300">thinking</strong>: amber rotating dashed ring</div>
                <div>• <strong className="text-indigo-300">speaking</strong>: violet ripples playback</div>
                <div>• <strong className="text-nuxt-signal">done</strong>: calm static checkmark</div>
              </div>
            </div>

            {/* Card 2: Level Source Selector */}
            <div className="flex flex-col gap-2.5 rounded bg-midnight-panel p-3 border border-steel-outline">
              <span className="text-xs font-semibold text-signal-white">
                Level Source Selector
              </span>
              <p className="text-[11px] text-muted-fog leading-relaxed">
                Select amplitude input driving the orb scale & ripples:
              </p>
              <div className="flex flex-col gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setOrbLevelMode('fake')
                    orbLevelModeRef.current = 'fake'
                    logAction('Orb level source set to: Fake Level Slider')
                  }}
                  className={`flex items-center justify-between py-2 px-3 rounded text-xs border transition ${
                    orbLevelMode === 'fake'
                      ? 'bg-nuxt-signal/20 text-nuxt-signal border-nuxt-signal font-semibold shadow-[0_0_8px_rgba(0,220,130,0.2)]'
                      : 'bg-void-canvas text-pale-frost border-steel-outline hover:bg-steel-outline hover:text-signal-white'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <span>🎚️</span>
                    <span>Fake Level Slider</span>
                  </span>
                  {orbLevelMode === 'fake' && <span className="text-xs">✓ Active</span>}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setOrbLevelMode('mic')
                    orbLevelModeRef.current = 'mic'
                    logAction('Orb level source set to: Use mic level (B2 getInputLevel)')
                  }}
                  className={`flex items-center justify-between py-2 px-3 rounded text-xs border transition ${
                    orbLevelMode === 'mic'
                      ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500 font-semibold shadow-[0_0_8px_rgba(16,185,129,0.3)]'
                      : 'bg-void-canvas text-pale-frost border-steel-outline hover:bg-steel-outline hover:text-signal-white'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <span>🎙️</span>
                    <span>Use mic level (B2)</span>
                  </span>
                  {orbLevelMode === 'mic' && <span className="text-xs">✓ Active</span>}
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setOrbLevelMode('playback')
                    orbLevelModeRef.current = 'playback'
                    logAction('Orb level source set to: Use playback level (B3 getLevel)')
                  }}
                  className={`flex items-center justify-between py-2 px-3 rounded text-xs border transition ${
                    orbLevelMode === 'playback'
                      ? 'bg-indigo-950/80 text-indigo-300 border-indigo-500 font-semibold shadow-[0_0_8px_rgba(99,102,241,0.3)]'
                      : 'bg-void-canvas text-pale-frost border-steel-outline hover:bg-steel-outline hover:text-signal-white'
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <span>🔊</span>
                    <span>Use playback level (B3)</span>
                  </span>
                  {orbLevelMode === 'playback' && <span className="text-xs">✓ Active</span>}
                </button>
              </div>
              <div className="mt-auto pt-2 border-t border-steel-outline/40 text-[10px] text-muted-fog">
                Wired directly to `ExaminerPanel levelSource` prop.
              </div>
            </div>

            {/* Card 3: Fake Level Slider */}
            <div className="flex flex-col gap-2.5 rounded bg-midnight-panel p-3 border border-steel-outline">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-signal-white">
                  Fake Level Slider
                </span>
                <span className="font-mono text-sm font-bold text-nuxt-signal">
                  {fakeOrbLevel.toFixed(2)} ({Math.round(fakeOrbLevel * 100)}%)
                </span>
              </div>
              <p className="text-[11px] text-muted-fog">
                Drag slider (0 to 1, step 0.01) to verify scale (1.0x → 1.35x):
              </p>

              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={fakeOrbLevel}
                disabled={orbLevelMode !== 'fake'}
                onChange={(e) => {
                  const val = Number(e.target.value)
                  setFakeOrbLevel(val)
                  fakeOrbLevelRef.current = val
                }}
                className="w-full h-3 accent-nuxt-signal cursor-pointer disabled:opacity-40"
              />

              <div className="flex items-center gap-1 justify-between flex-wrap">
                {[0, 0.25, 0.5, 0.75, 1.0].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    disabled={orbLevelMode !== 'fake'}
                    onClick={() => {
                      setFakeOrbLevel(preset)
                      fakeOrbLevelRef.current = preset
                      logAction(`Fake level preset set to: ${preset.toFixed(2)} (${Math.round(preset * 100)}%)`)
                    }}
                    className={`rounded px-2 py-0.5 text-[10px] font-mono border transition ${
                      Math.abs(fakeOrbLevel - preset) < 0.01
                        ? 'bg-nuxt-signal text-void-canvas font-bold border-nuxt-signal'
                        : 'bg-void-canvas text-muted-fog hover:text-pale-frost border-steel-outline'
                    } disabled:opacity-40`}
                  >
                    {Math.round(preset * 100)}%
                  </button>
                ))}
              </div>

              <div className="mt-auto pt-2 border-t border-steel-outline/40 space-y-1 text-[11px]">
                <div className="flex justify-between text-muted-fog">
                  <span>Target Amplitude:</span>
                  <span className="font-mono text-signal-white font-semibold">
                    {getActiveOrbLevel().toFixed(3)}
                  </span>
                </div>
                <div className="flex justify-between text-muted-fog">
                  <span>Smoothed Scale (1 + lvl*0.35):</span>
                  <span className="font-mono text-nuxt-signal font-semibold">
                    {(1 + getActiveOrbLevel() * 0.35).toFixed(3)}x
                  </span>
                </div>
              </div>
            </div>

            {/* Card 4: Live Amplitude Meter & Standalone Preview */}
            <div className="flex flex-col items-center justify-between gap-2 rounded bg-midnight-panel p-3 border border-steel-outline">
              <div className="w-full flex items-center justify-between">
                <span className="text-xs font-semibold text-signal-white">
                  Active Amplitude & Preview
                </span>
                <span className="text-[10px] text-muted-fog uppercase font-mono">
                  {orbLevelMode}
                </span>
              </div>

              <div className="w-full">
                <LiveOrbLevelMeter
                  getLevel={getActiveOrbLevel}
                  mode={orbLevelMode}
                />
              </div>

              <div className="flex flex-col items-center justify-center p-1 bg-void-canvas/70 rounded-lg border border-steel-outline/60 w-full">
                <VoiceOrb
                  state={forcedState ?? (recorder.isRecording ? 'listening' : playbackState !== 'idle' ? 'speaking' : currentTurn.done ? 'done' : 'idle')}
                  levelSource={getActiveOrbLevel}
                  size={130}
                />
                <span className="text-[10px] text-muted-fog mt-0.5">
                  Standalone Preview (130px)
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Section 2: 🎙️ Recorder Debug Box (Task B2 Core Requirements) */}
        <div className="rounded-lg border border-steel-outline bg-deep-slate/50 p-4 shadow-sm">
          <div className="flex items-center justify-between pb-2 mb-3 border-b border-steel-outline/60 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-bold text-signal-white text-xs uppercase tracking-wider flex items-center gap-1.5">
                🎙️ Recorder Debug Box (Task B2)
              </span>
              <RecorderStatusPill status={recorder.status} />
              {tooShortNotice && (
                <span className="text-[11px] font-semibold text-amber-400 bg-amber-950/80 px-2 py-0.5 rounded border border-amber-600 animate-pulse">
                  ⚠️ Clip was &lt; 300ms (discarded per spec)
                </span>
              )}
              {recorder.error && (
                <span className="text-[11px] font-semibold text-red-400 bg-red-950/80 px-2 py-0.5 rounded border border-red-600">
                  {recorder.error}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-muted-fog">
              <span>Hold <kbd className="rounded bg-void-canvas px-1.5 py-0.5 font-mono text-[10px] text-pale-frost border border-steel-outline">Space</kbd> to talk</span>
              <span>•</span>
              <span>Press <kbd className="rounded bg-void-canvas px-1.5 py-0.5 font-mono text-[10px] text-pale-frost border border-steel-outline">Esc</kbd> to cancel</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {/* Card 1: PTT Trigger & Live Level Bar */}
            <div className="flex flex-col gap-2 rounded bg-midnight-panel p-2.5 border border-steel-outline">
              <span className="text-[11px] font-semibold text-signal-white">
                Live Microphone Level:
              </span>
              <LiveLevelBar getInputLevel={recorder.getInputLevel} />

              <button
                type="button"
                onPointerDown={(e) => {
                  e.preventDefault()
                  unlockAudio()
                  recorder.startRecording()
                }}
                onPointerUp={(e) => {
                  e.preventDefault()
                  recorder.stopRecording()
                }}
                onPointerLeave={() => {
                  if (recorder.isRecording) recorder.stopRecording()
                }}
                className={`flex items-center justify-center gap-2 rounded py-2 px-3 text-xs font-semibold border transition select-none ${
                  recorder.isRecording
                    ? 'bg-red-600 text-white border-red-500 animate-pulse'
                    : 'bg-deep-slate text-pale-frost border-steel-outline hover:bg-steel-outline active:bg-nuxt-signal active:text-void-canvas'
                }`}
              >
                <span>{recorder.isRecording ? '🔴' : '🎙️'}</span>
                <span>
                  {recorder.isRecording
                    ? 'Recording… Release to Finish'
                    : 'Hold to Talk (or Spacebar)'}
                </span>
              </button>
            </div>

            {/* Card 2: Spacebar Input Exclusion Test */}
            <div className="flex flex-col gap-1.5 rounded bg-midnight-panel p-2.5 border border-steel-outline">
              <label
                htmlFor="space-exclusion-input"
                className="text-[11px] font-semibold text-signal-white flex items-center justify-between"
              >
                <span>Spacebar Input Test:</span>
                <span className="text-[10px] text-nuxt-signal font-mono">Ignore Input Focus</span>
              </label>
              <input
                id="space-exclusion-input"
                type="text"
                value={testInputText}
                onChange={(e) => setTestInputText(e.target.value)}
                placeholder="Click here and press Space to test..."
                className="rounded bg-void-canvas px-2.5 py-1.5 text-xs text-pale-frost border border-steel-outline focus:border-nuxt-signal focus:outline-none placeholder:text-blue-steel"
              />
              <span className="text-[10px] text-muted-fog leading-tight">
                Typing Space inside this box inserts spaces normally. It must <strong className="text-amber-300">NOT</strong> trigger audio recording.
              </span>
            </div>

            {/* Card 3: Last Clip Metadata & Playback */}
            <div className="md:col-span-2 flex flex-col gap-1.5 rounded bg-midnight-panel p-2.5 border border-steel-outline">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-signal-white">
                  Last Clip Inspector & Playback:
                </span>
                {lastClip && (
                  <span className="text-[10px] text-nuxt-signal font-mono">
                    ✓ No "data:" prefix ({lastClip.base64.slice(0, 12)}...)
                  </span>
                )}
              </div>

              {lastClip ? (
                <div className="flex flex-col gap-1.5">
                  <div className="grid grid-cols-3 gap-2 text-[10px] font-mono bg-void-canvas p-1.5 rounded border border-steel-outline">
                    <div>
                      <span className="text-muted-fog block text-[9px]">DURATION</span>
                      <span className="text-signal-white font-semibold">
                        {(lastClip.durationMs / 1000).toFixed(2)}s ({lastClip.durationMs}ms)
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-fog block text-[9px]">SIZE</span>
                      <span className="text-signal-white font-semibold">
                        {(lastClip.blob.size / 1024).toFixed(1)} KB ({lastClip.blob.size} B)
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-fog block text-[9px]">MIME</span>
                      <span
                        className="text-nuxt-signal font-semibold truncate block"
                        title={lastClip.mimeType}
                      >
                        {lastClip.mimeType}
                      </span>
                    </div>
                  </div>
                  {lastAudioUrl && (
                    <div className="flex items-center gap-2 mt-0.5">
                      <audio
                        controls
                        src={lastAudioUrl}
                        className="w-full h-7 accent-nuxt-signal"
                      />
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex h-16 items-center justify-center rounded bg-void-canvas p-2 border border-steel-outline text-muted-fog text-xs italic text-center">
                  No audio clip recorded yet. Hold Space (~3s) and speak into your microphone.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Section 3: 🔊 Playback & Browser-TTS Debug Box (Task B3 Core Requirements) */}
        <div className="rounded-lg border border-steel-outline bg-deep-slate/50 p-4 shadow-sm">
          <div className="flex items-center justify-between pb-2 mb-3 border-b border-steel-outline/60 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-bold text-signal-white text-xs uppercase tracking-wider flex items-center gap-1.5">
                🔊 Playback & Browser-TTS Debug Box (Task B3)
              </span>
              <PlaybackStatusPill state={playbackState} />
              {playbackSource && (
                <span className="text-[10px] text-muted-fog font-mono truncate max-w-xs">
                  • {playbackSource}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-muted-fog bg-midnight-panel px-2 py-0.5 rounded border border-steel-outline max-w-xs truncate">
                🗣️ {detectedVoiceLabel}
              </span>
              <button
                type="button"
                onClick={handleStopPlayback}
                className="flex items-center gap-1 px-3 py-1 rounded bg-red-950/80 text-red-300 hover:bg-red-900 border border-red-600 font-semibold text-xs transition active:scale-95"
              >
                <span>⏹️</span>
                <span>Stop Playback</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Card 1: Play MP3 File */}
            <div className="flex flex-col gap-2 rounded bg-midnight-panel p-2.5 border border-steel-outline">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-signal-white">
                  Play MP3 File (Web Audio API)
                </span>
                <span className="text-[10px] text-nuxt-signal font-mono">base64 → decodeAudioData</span>
              </div>

              <input
                type="file"
                ref={fileInputRef}
                accept="audio/*,.mp3,.wav,.ogg,.webm"
                className="hidden"
                onChange={handleSelectAudioFile}
              />

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex-1 rounded py-1.5 px-2 bg-void-canvas hover:bg-steel-outline text-pale-frost text-xs border border-steel-outline transition truncate text-left"
                >
                  {selectedAudioFile ? `📁 ${selectedAudioFile.name}` : '📁 Choose MP3 / Audio File…'}
                </button>
                {selectedAudioFile && (
                  <span className="text-[10px] font-mono text-muted-fog">
                    {(selectedAudioFile.size / 1024).toFixed(0)}KB
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2 mt-auto">
                <button
                  type="button"
                  onClick={handlePlaySelectedFile}
                  disabled={!selectedAudioFile}
                  className="flex-1 flex items-center justify-center gap-1.5 rounded py-1.5 px-3 bg-nuxt-signal text-void-canvas font-bold text-xs hover:opacity-90 disabled:opacity-40 disabled:hover:opacity-40 transition"
                >
                  <span>▶</span>
                  <span>Play MP3 File</span>
                </button>
                <button
                  type="button"
                  onClick={handlePlaySampleChime}
                  className="rounded py-1.5 px-2.5 bg-void-canvas hover:bg-steel-outline text-pale-frost font-medium text-xs border border-steel-outline transition"
                  title="Play 1.0s sample chord chime via Web Audio"
                >
                  🎵 Sample Chime
                </button>
              </div>
            </div>

            {/* Card 2: Speak with Browser TTS */}
            <div className="flex flex-col gap-2 rounded bg-midnight-panel p-2.5 border border-steel-outline">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-signal-white">
                  Speak with Browser TTS (Fallback)
                </span>
                <span className="text-[10px] text-indigo-400 font-mono">prefer en-US → en-IN</span>
              </div>

              <textarea
                value={ttsInputText}
                onChange={(e) => setTtsInputText(e.target.value)}
                rows={2}
                className="w-full rounded bg-void-canvas p-1.5 text-xs text-pale-frost border border-steel-outline focus:border-indigo-400 focus:outline-none resize-none"
                placeholder="Enter text to speak aloud..."
              />

              <div className="flex items-center gap-2 mt-auto">
                <button
                  type="button"
                  onClick={() => handleSpeakTTS()}
                  className="flex-1 flex items-center justify-center gap-1.5 rounded py-1.5 px-3 bg-indigo-600 text-white font-bold text-xs hover:bg-indigo-500 transition"
                >
                  <span>🗣️</span>
                  <span>Speak with Browser TTS</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const turnText = `${currentTurn.ack_text} ${currentTurn.question_text}`
                    setTtsInputText(turnText)
                    logAction(`📋 Copied Turn #${turnIndex + 1} ack + question into TTS`)
                  }}
                  className="rounded py-1.5 px-2 bg-void-canvas hover:bg-steel-outline text-muted-fog hover:text-pale-frost text-[11px] border border-steel-outline transition"
                  title="Use current turn ack + question"
                >
                  📋 Use Turn Text
                </button>
              </div>
            </div>

            {/* Card 3: Live Monitors & Acceptance Tests */}
            <div className="flex flex-col gap-2 rounded bg-midnight-panel p-2.5 border border-steel-outline">
              <span className="text-[11px] font-semibold text-signal-white">
                Live Playback Monitors:
              </span>

              <div className="flex flex-col gap-1">
                <div className="flex justify-between text-[10px] text-muted-fog">
                  <span>Live Playback Level (RMS):</span>
                  <span>0..1</span>
                </div>
                <LivePlaybackLevelBar
                  getPlaybackLevel={() => activePlaybackRef.current?.getLevel() ?? 0}
                  isTTS={playbackState === 'speaking-tts'}
                />
              </div>

              <div className="flex flex-col gap-1">
                <div className="flex justify-between text-[10px] text-muted-fog">
                  <span>Playback Progress:</span>
                  <span>0 → 1</span>
                </div>
                <LivePlaybackProgressBar
                  getPlaybackProgress={() => activePlaybackRef.current?.getProgress() ?? 0}
                  isPlaying={playbackState !== 'idle'}
                />
              </div>

              <div className="flex items-center gap-2 mt-auto pt-1 border-t border-steel-outline/40">
                <span className="text-[10px] text-muted-fog">Tests:</span>
                <button
                  type="button"
                  onClick={handleTestMidPlayStop}
                  className="rounded px-2 py-0.5 bg-void-canvas hover:bg-steel-outline text-[10px] text-pale-frost border border-steel-outline transition"
                >
                  Mid-Play Stop (500ms)
                </button>
                <button
                  type="button"
                  onClick={handleTestOverlap}
                  className="rounded px-2 py-0.5 bg-void-canvas hover:bg-steel-outline text-[10px] text-pale-frost border border-steel-outline transition"
                >
                  Overlap (Audio → TTS)
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Section 4: Mock Controls & Diagnostics Log */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 rounded-lg border border-steel-outline bg-deep-slate/50">
          {/* Column 1: Step to Mock Turn */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-signal-white text-[11px] uppercase tracking-wider">
                Viva Mock Turns
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={handlePrevTurn}
                  disabled={turnIndex === 0}
                  className="rounded bg-deep-slate px-1.5 py-0.5 text-[10px] font-medium border border-steel-outline hover:bg-void-canvas disabled:opacity-40"
                >
                  ◀ Prev
                </button>
                <button
                  onClick={handleNextTurn}
                  disabled={turnIndex === MOCK_TURNS.length - 1}
                  className="rounded bg-deep-slate px-1.5 py-0.5 text-[10px] font-medium border border-steel-outline hover:bg-void-canvas disabled:opacity-40"
                >
                  Next ▶
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {MOCK_TURNS.map((t, idx) => (
                <button
                  key={idx}
                  onClick={() => goToTurn(idx)}
                  className={`rounded px-2 py-1 text-[10px] font-mono border transition ${
                    idx === turnIndex
                      ? 'bg-nuxt-signal text-void-canvas font-bold border-nuxt-signal'
                      : 'bg-midnight-panel text-pale-frost border-steel-outline hover:bg-steel-outline'
                  }`}
                >
                  #{idx + 1} L{t.depth_level} ({t.verdict})
                </button>
              ))}
            </div>
            <p className="mt-1 text-[11px] text-muted-fog">
              Topic: <strong className="text-pale-frost">{currentTurn.topic}</strong>
            </p>
          </div>

          {/* Column 2: Current Turn Payload */}
          <div className="flex flex-col gap-1">
            <span className="font-semibold text-signal-white text-[11px] uppercase tracking-wider">
              Current Turn Payload (TurnResponse)
            </span>
            <pre className="max-h-32 overflow-auto rounded bg-void-canvas p-2 font-mono text-[9px] text-muted-fog border border-steel-outline">
              {JSON.stringify(currentTurn, null, 2)}
            </pre>
          </div>

          {/* Column 3: Event Log & Task Diagnostics */}
          <div className="flex flex-col gap-1">
            <span className="font-semibold text-signal-white text-[11px] uppercase tracking-wider">
              Harness Action Log
            </span>
            <div className="max-h-32 overflow-auto rounded bg-void-canvas p-2 font-mono text-[9px] text-pale-frost/80 border border-steel-outline space-y-0.5">
              {actionLog.map((log, i) => (
                <div key={i}>{log}</div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

const container = document.getElementById('root')
if (container) {
  const root = createRoot(container)
  root.render(
    <React.StrictMode>
      <ExaminerDevHarness />
    </React.StrictMode>
  )
}
