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

import React, { useEffect, useRef, useState, useTransition } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import ExaminerPanel from '../components/ExaminerPanel'
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
  const [turnIndex, setTurnIndex] = useState(0)
  const [currentTurn, setCurrentTurn] = useState<TurnResponse>(MOCK_TURNS[0])
  const [simulatedDelayMs, setSimulatedDelayMs] = useState(400)
  const [debugDrawerOpen, setDebugDrawerOpen] = useState(true)
  const [actionLog, setActionLog] = useState<string[]>([
    'Dev harness mounted. Initial Turn 1 loaded.',
    'Task B2 audio recorder initialized. Mic stream standing by.',
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

  // Detect preferred TTS voice on load and voice change
  useEffect(() => {
    const updateVoiceLabel = () => {
      const v = getPreferredTTSVoice()
      if (v) {
        setDetectedVoiceLabel(`${v.name} (${v.lang})`)
      } else {
        setDetectedVoiceLabel('Browser Default (en-IN fallback)')
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

  // Hook instance under test (Task B2)
  const recorder = usePushToTalkRecorder({
    enabled: true,
    bindSpacebar: true,
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

  // Revoke the previous clip URL on replace and on unmount
  useEffect(() => {
    return () => {
      if (lastAudioUrl) URL.revokeObjectURL(lastAudioUrl)
    }
  }, [lastAudioUrl])

  const goToTurn = (index: number) => {
    const clamped = Math.max(0, Math.min(index, MOCK_TURNS.length - 1))
    setTurnIndex(clamped)
    setCurrentTurn(MOCK_TURNS[clamped])
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

  // ExaminerPanel callbacks
  const handleMockAudioSubmit = async (
    rec: RecordedAudio
  ): Promise<TurnResponse> => {
    logAction(`onSubmitAudio: ${rec.durationMs}ms, ${rec.mimeType}, size=${rec.base64.length}b64`)
    if (simulatedDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, simulatedDelayMs))
    }
    const nextIdx = Math.min(turnIndex + 1, MOCK_TURNS.length - 1)
    const next = MOCK_TURNS[nextIdx]
    startTransition(() => {
      setTurnIndex(nextIdx)
      setCurrentTurn(next)
    })
    return next
  }

  const handleMockTextSubmit = async (
    text: string
  ): Promise<TurnResponse> => {
    logAction(`onSubmitText: "${text}"`)
    if (simulatedDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, simulatedDelayMs))
    }
    const nextIdx = Math.min(turnIndex + 1, MOCK_TURNS.length - 1)
    const next = MOCK_TURNS[nextIdx]
    startTransition(() => {
      setTurnIndex(nextIdx)
      setCurrentTurn(next)
    })
    return next
  }

  const handleTurnUpdate = (turn: TurnResponse) => {
    logAction(`onTurn callback: L${turn.depth_level} - ${turn.topic}`)
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
      className="flex flex-col h-screen w-screen overflow-hidden bg-void-canvas text-pale-frost font-sans"
      onPointerDown={() => unlockAudio()}
    >
      {/* Dev Harness Navigation Bar */}
      <header className="flex shrink-0 items-center justify-between border-b border-steel-outline bg-midnight-panel px-4 py-2 text-xs">
        <div className="flex items-center gap-3">
          <span className="font-bold text-signal-white text-sm tracking-wide">
            VivaVoce
          </span>
          <span className="rounded bg-deep-slate px-2 py-0.5 font-mono text-[11px] text-nuxt-signal border border-steel-outline">
            examiner-dev.html (M3 Lane B)
          </span>
          <span className="text-muted-fog">
            Mode (a) scaffold • Task B2 Push-to-Talk Active
          </span>
        </div>
        <div className="flex items-center gap-3">
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
            className="rounded bg-void-canvas px-2 py-1 text-pale-frost border border-steel-outline"
          >
            <option value={0}>0ms (Instant)</option>
            <option value={400}>400ms (Fast)</option>
            <option value={1000}>1000ms (Typical Voice)</option>
            <option value={2500}>2500ms (Full LLM)</option>
          </select>
          <button
            onClick={() => setDebugDrawerOpen((prev) => !prev)}
            className="rounded bg-deep-slate px-3 py-1 font-medium text-pale-frost hover:bg-steel-outline border border-steel-outline transition"
          >
            {debugDrawerOpen ? 'Hide Debug Drawer ↓' : 'Show Debug Drawer ↑'}
          </button>
        </div>
      </header>

      {/* Main Split View: 65% Workspace Placeholder | 35% ExaminerPanel */}
      <main className="flex flex-1 min-h-0 w-full overflow-hidden">
        {/* Left 65%: Workspace Placeholder (M4 IDE Simulation) */}
        <section
          className="flex min-w-0 basis-[65%] flex-col border-r border-steel-outline bg-void-canvas"
          aria-label="Workspace — M4"
        >
          {/* Workspace Tabs Header */}
          <div className="flex items-center justify-between border-b border-steel-outline bg-midnight-panel px-4 py-2">
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
          <div className="flex-1 overflow-auto p-4 font-mono text-xs leading-5 bg-void-canvas">
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
          className="min-w-0 basis-[35%] flex flex-col h-full overflow-hidden bg-midnight-panel"
          aria-label="Examiner Panel"
        >
          <ExaminerPanel
            initialTurn={currentTurn}
            onSubmitAudio={handleMockAudioSubmit}
            onSubmitText={handleMockTextSubmit}
            onTurn={handleTurnUpdate}
            onRequestReport={handleRequestReport}
            fillersUrl="/api/voice/fillers"
            disabled={false}
          />
        </aside>
      </main>

      {/* Collapsible Debug Drawer Featuring Task B2 Recorder Debug */}
      {debugDrawerOpen && (
        <section
          className="shrink-0 border-t border-steel-outline bg-midnight-panel text-xs transition-all max-h-80 overflow-auto"
          aria-label="Debug Drawer"
        >
          {/* Section 1: 🎙️ Recorder Debug Box (Task B2 Core Requirements) */}
          <div className="border-b border-steel-outline bg-deep-slate/80 p-3">
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-steel-outline/60">
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

            <div className="grid grid-cols-4 gap-4">
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
              <div className="col-span-2 flex flex-col gap-1.5 rounded bg-midnight-panel p-2.5 border border-steel-outline">
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

          {/* Section 2: 🔊 Playback & Browser-TTS Debug Box (Task B3 Core Requirements) */}
          <div className="border-b border-steel-outline bg-midnight-panel/90 p-3">
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-steel-outline/60">
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
                <span className="text-[10px] text-muted-fog bg-deep-slate px-2 py-0.5 rounded border border-steel-outline max-w-xs truncate">
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

            <div className="grid grid-cols-3 gap-4">
              {/* Card 1: Play MP3 File */}
              <div className="flex flex-col gap-2 rounded bg-deep-slate/80 p-2.5 border border-steel-outline">
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
              <div className="flex flex-col gap-2 rounded bg-deep-slate/80 p-2.5 border border-steel-outline">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-signal-white">
                    Speak with Browser TTS (Fallback)
                  </span>
                  <span className="text-[10px] text-indigo-400 font-mono">prefer en-IN → en-US</span>
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
              <div className="flex flex-col gap-2 rounded bg-deep-slate/80 p-2.5 border border-steel-outline">
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

          {/* Section 3: Mock Controls & Diagnostics Log */}
          <div className="grid grid-cols-3 gap-4 p-3 bg-midnight-panel">
            {/* Column 1: Step to Mock Turn */}
            <div className="flex flex-col gap-1.5">
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
                    className={`rounded px-2 py-0.5 text-[10px] font-mono border transition ${
                      idx === turnIndex
                        ? 'bg-nuxt-signal text-void-canvas font-bold border-nuxt-signal'
                        : 'bg-deep-slate text-pale-frost border-steel-outline hover:bg-steel-outline'
                    }`}
                  >
                    #{idx + 1} L{t.depth_level} ({t.verdict})
                  </button>
                ))}
              </div>
              <p className="mt-1 text-[10px] text-muted-fog">
                Topic: <strong className="text-pale-frost">{currentTurn.topic}</strong>
              </p>
            </div>

            {/* Column 2: Current Turn Payload */}
            <div className="flex flex-col gap-1">
              <span className="font-semibold text-signal-white text-[11px] uppercase tracking-wider">
                Current Turn Payload (TurnResponse)
              </span>
              <pre className="max-h-24 overflow-auto rounded bg-void-canvas p-2 font-mono text-[9px] text-muted-fog border border-steel-outline">
                {JSON.stringify(currentTurn, null, 2)}
              </pre>
            </div>

            {/* Column 3: Event Log & Task Diagnostics */}
            <div className="flex flex-col gap-1">
              <span className="font-semibold text-signal-white text-[11px] uppercase tracking-wider">
                Harness Action Log
              </span>
              <div className="max-h-24 overflow-auto rounded bg-void-canvas p-2 font-mono text-[9px] text-pale-frost/80 border border-steel-outline space-y-0.5">
                {actionLog.map((log, i) => (
                  <div key={i}>{log}</div>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}
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
