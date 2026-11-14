/**
 * M3 Voice Pipeline — Audio Recorder & Playback Service (Task B2)
 *
 * Implements the exact signatures and specifications from CONTEXT §5.8:
 * - RecordedAudio, RecorderStatus, UsePushToTalkRecorderOptions, UsePushToTalkRecorderReturn
 * - usePushToTalkRecorder: Push-to-talk hook with MediaRecorder and AnalyserNode
 * - blobToBase64: Raw base64 encoding without "data:" prefix
 * - unlockAudio: Resumes shared AudioContext on user interaction
 * - Stubs preserved for Task B3 (playBase64Audio, speakWithBrowserTTS, stopAllPlayback)
 */

import { useCallback, useEffect, useRef, useState } from 'react'

export interface RecordedAudio {
  blob: Blob
  base64: string /* no data: prefix */
  mimeType: string
  durationMs: number
}

export type RecorderStatus =
  | 'idle'
  | 'requesting-permission'
  | 'recording'
  | 'denied'
  | 'unsupported'
  | 'error'

export interface UsePushToTalkRecorderOptions {
  onRecordingComplete: (rec: RecordedAudio) => void
  enabled?: boolean // default true
  bindSpacebar?: boolean // default true
  minDurationMs?: number // default 300 (shorter = discarded)
  maxDurationMs?: number // default 60000 (auto-stop)
  onTooShort?: () => void
}

export interface UsePushToTalkRecorderReturn {
  status: RecorderStatus
  isRecording: boolean
  error: string | null
  startRecording(): void
  stopRecording(): void
  cancelRecording(): void
  getInputLevel(): number /* 0..1 mic level */
}

// Global shared AudioContext across recording and playback
let sharedAudioContext: AudioContext | null = null

export function getSharedAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  if (!AudioCtx) return null
  if (!sharedAudioContext || sharedAudioContext.state === 'closed') {
    sharedAudioContext = new AudioCtx()
  }
  return sharedAudioContext
}

/**
 * Resumes shared AudioContext on a user gesture (pointerdown/keydown)
 */
export function unlockAudio(): void {
  const ctx = getSharedAudioContext()
  if (ctx && ctx.state === 'suspended') {
    void ctx.resume()
  }
}

// Auto-unlock AudioContext on first user interaction per CONTEXT §5.8 / TASKS.md B3
if (typeof window !== 'undefined') {
  const handleFirstInteraction = () => {
    unlockAudio()
    window.removeEventListener('pointerdown', handleFirstInteraction, true)
    window.removeEventListener('keydown', handleFirstInteraction, true)
    window.removeEventListener('touchstart', handleFirstInteraction, true)
  }
  window.addEventListener('pointerdown', handleFirstInteraction, { capture: true, passive: true })
  window.addEventListener('keydown', handleFirstInteraction, { capture: true, passive: true })
  window.addEventListener('touchstart', handleFirstInteraction, { capture: true, passive: true })
}

/**
 * MIME preference: audio/webm;codecs=opus -> audio/webm -> audio/mp4 -> browser default
 */
export function getPreferredMimeType(): string | undefined {
  if (
    typeof window === 'undefined' ||
    typeof MediaRecorder === 'undefined' ||
    typeof MediaRecorder.isTypeSupported !== 'function'
  ) {
    return undefined
  }
  const candidateTypes = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
  ]
  for (const type of candidateTypes) {
    if (MediaRecorder.isTypeSupported(type)) {
      return type
    }
  }
  return undefined
}

/**
 * Checks whether an element is an interactive text input or textarea
 * where typing space should insert a space character.
 */
export function isTextInputElement(el: Element | null | undefined): boolean {
  if (!el) return false
  const tagName = el.tagName ? el.tagName.toUpperCase() : ''
  if (tagName === 'TEXTAREA' || tagName === 'SELECT') {
    return true
  }
  if (tagName === 'INPUT') {
    const type = ((el as HTMLInputElement).type || 'text').toLowerCase()
    // Text-entry input types consume Space; checkboxes, buttons, ranges do not
    return ['text', 'search', 'url', 'password', 'email', 'number', 'tel', ''].includes(type)
  }
  if ((el as HTMLElement).isContentEditable || el.getAttribute?.('contenteditable') === 'true') {
    return true
  }
  if (typeof el.closest === 'function' && el.closest('.monaco-editor')) {
    return true
  }
  return false
}

/**
 * Checks whether the keyboard event target is an interactive text input
 * or inside Monaco Editor, where Spacebar must NOT be intercepted.
 */
export function shouldIgnoreKeyboardTarget(e: KeyboardEvent): boolean {
  const elementsToCheck: (HTMLElement | null)[] = [
    e.target as HTMLElement | null,
    typeof document !== 'undefined' ? (document.activeElement as HTMLElement | null) : null,
  ]

  for (const el of elementsToCheck) {
    if (isTextInputElement(el)) {
      return true
    }
  }

  return false
}

/**
 * Encodes an audio Blob into a raw base64 string without the "data:...;base64," prefix.
 */
export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const result = reader.result
      if (typeof result === 'string') {
        const commaIndex = result.indexOf(',')
        resolve(commaIndex !== -1 ? result.slice(commaIndex + 1) : result)
      } else {
        resolve('')
      }
    }
    reader.onerror = () => reject(reader.error || new Error('Failed to read audio blob'))
    reader.readAsDataURL(blob)
  })
}

/**
 * Push-to-talk recorder hook managing microphone streams, MediaRecorder lifecycle,
 * AnalyserNode audio levels, Spacebar key bindings, and duration boundaries.
 */
export function usePushToTalkRecorder(
  options: UsePushToTalkRecorderOptions
): UsePushToTalkRecorderReturn {
  const [status, setStatus] = useState<RecorderStatus>('idle')
  const [isRecording, setIsRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Mutable refs to prevent stale closures in event listeners
  const optionsRef = useRef(options)
  optionsRef.current = options

  const statusRef = useRef<RecorderStatus>('idle')
  statusRef.current = status

  const isRecordingRef = useRef(false)
  isRecordingRef.current = isRecording

  const streamRef = useRef<MediaStream | null>(null)
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const recordingIntentRef = useRef(false)
  const isCancelledRef = useRef(false)
  const startTimeRef = useRef(0)
  const maxDurationTimerRef = useRef<number | null>(null)

  const isMountedRef = useRef(true)
  const isRequestingStreamRef = useRef(false)
  const streamPromiseRef = useRef<Promise<MediaStream | null> | null>(null)

  /**
   * Acquire and hold a single MediaStream while mounted
   */
  const ensureMicStream = useCallback(async (): Promise<MediaStream | null> => {
    if (
      typeof window === 'undefined' ||
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === 'undefined'
    ) {
      setStatus('unsupported')
      statusRef.current = 'unsupported'
      setError('Audio recording is not supported in this browser')
      return null
    }

    // Reuse existing live stream if active
    const existing = streamRef.current
    if (
      existing &&
      existing.active &&
      existing.getAudioTracks().some((t) => t.readyState === 'live')
    ) {
      return existing
    }

    if (streamPromiseRef.current) {
      return streamPromiseRef.current
    }

    if (statusRef.current !== 'recording') {
      setStatus('requesting-permission')
      statusRef.current = 'requesting-permission'
    }

    isRequestingStreamRef.current = true
    const promise = (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        if (!isMountedRef.current) {
          // StrictMode unmount cleanup protection
          stream.getTracks().forEach((track) => track.stop())
          return null
        }

        streamRef.current = stream

        // Connect microphone to shared AudioContext's AnalyserNode for level readings
        const ctx = getSharedAudioContext()
        if (ctx) {
          try {
            if (sourceNodeRef.current) {
              sourceNodeRef.current.disconnect()
            }
            if (analyserRef.current) {
              analyserRef.current.disconnect()
            }
            const source = ctx.createMediaStreamSource(stream)
            const analyser = ctx.createAnalyser()
            analyser.fftSize = 256
            source.connect(analyser)
            sourceNodeRef.current = source
            analyserRef.current = analyser
          } catch (audioErr) {
            console.warn('[usePushToTalkRecorder] AnalyserNode setup notice:', audioErr)
          }
        }

        if (statusRef.current === 'requesting-permission') {
          setStatus('idle')
          statusRef.current = 'idle'
        }
        setError(null)
        return stream
      } catch (err: unknown) {
        if (!isMountedRef.current) return null
        recordingIntentRef.current = false
        const errObj = err as { name?: string; message?: string }
        if (errObj?.name === 'NotAllowedError' || errObj?.name === 'PermissionDeniedError') {
          setStatus('denied')
          statusRef.current = 'denied'
          setError('Microphone access denied')
        } else {
          setStatus('error')
          statusRef.current = 'error'
          setError(errObj?.message || 'Failed to acquire microphone access')
        }
        return null
      } finally {
        isRequestingStreamRef.current = false
        streamPromiseRef.current = null
      }
    })()

    streamPromiseRef.current = promise
    return promise
  }, [])

  /**
   * Stop recording cleanly and finalize the audio clip
   */
  const stopRecording = useCallback(() => {
    recordingIntentRef.current = false

    if (maxDurationTimerRef.current) {
      window.clearTimeout(maxDurationTimerRef.current)
      maxDurationTimerRef.current = null
    }

    const rec = mediaRecorderRef.current
    if (rec && rec.state !== 'inactive') {
      try {
        rec.stop()
      } catch {
        // ignore if already closed
      }
    } else if (isRecordingRef.current) {
      setIsRecording(false)
      isRecordingRef.current = false
      setStatus('idle')
      statusRef.current = 'idle'
    }
  }, [])

  /**
   * Cancel recording without saving or emitting any clip
   */
  const cancelRecording = useCallback(() => {
    recordingIntentRef.current = false
    isCancelledRef.current = true

    if (maxDurationTimerRef.current) {
      window.clearTimeout(maxDurationTimerRef.current)
      maxDurationTimerRef.current = null
    }

    const rec = mediaRecorderRef.current
    if (rec && rec.state !== 'inactive') {
      try {
        rec.stop()
      } catch {
        // ignore
      }
    } else if (isRecordingRef.current) {
      setIsRecording(false)
      isRecordingRef.current = false
      setStatus('idle')
      statusRef.current = 'idle'
    }
  }, [])

  /**
   * Starts MediaRecorder on an active stream with timeslice(250)
   */
  const beginRecordingWithStream = useCallback((stream: MediaStream) => {
    if (isRecordingRef.current) return
    if (!stream.active || !stream.getAudioTracks().some((t) => t.readyState === 'live')) {
      setStatus('error')
      statusRef.current = 'error'
      setError('Microphone stream is not active')
      return
    }

    unlockAudio()

    const preferredMime = getPreferredMimeType()
    let recorder: MediaRecorder
    try {
      recorder = preferredMime
        ? new MediaRecorder(stream, { mimeType: preferredMime })
        : new MediaRecorder(stream)
    } catch {
      try {
        recorder = new MediaRecorder(stream)
      } catch (recErr) {
        setStatus('error')
        statusRef.current = 'error'
        setError(recErr instanceof Error ? recErr.message : 'MediaRecorder creation failed')
        return
      }
    }

    mediaRecorderRef.current = recorder
    chunksRef.current = []
    isCancelledRef.current = false
    startTimeRef.current = Date.now()

    recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data && e.data.size > 0) {
        chunksRef.current.push(e.data)
      }
    }

    recorder.onstop = async () => {
      if (maxDurationTimerRef.current) {
        window.clearTimeout(maxDurationTimerRef.current)
        maxDurationTimerRef.current = null
      }

      const wasCancelled = isCancelledRef.current
      const durationMs = Date.now() - startTimeRef.current
      const chunks = [...chunksRef.current]
      chunksRef.current = []

      if (!isMountedRef.current) return

      setIsRecording(false)
      isRecordingRef.current = false
      setStatus('idle')
      statusRef.current = 'idle'

      if (wasCancelled) {
        return
      }

      const minDur = optionsRef.current.minDurationMs ?? 300
      if (durationMs < minDur) {
        optionsRef.current.onTooShort?.()
        return
      }

      const finalMime = recorder.mimeType || preferredMime || 'audio/webm'
      const blob = new Blob(chunks, { type: finalMime })
      if (chunks.length === 0 || blob.size === 0) {
        optionsRef.current.onTooShort?.()
        return
      }
      try {
        const base64 = await blobToBase64(blob)
        if (!isMountedRef.current) return
        optionsRef.current.onRecordingComplete({
          blob,
          base64,
          mimeType: finalMime,
          durationMs,
        })
      } catch (b64Err) {
        if (isMountedRef.current) {
          setError(b64Err instanceof Error ? b64Err.message : 'Failed to encode recorded audio')
        }
      }
    }

    try {
      recorder.start(250)
    } catch (startErr) {
      setStatus('error')
      statusRef.current = 'error'
      setError(startErr instanceof Error ? startErr.message : 'Failed to start MediaRecorder')
      return
    }

    setIsRecording(true)
    isRecordingRef.current = true
    setStatus('recording')
    statusRef.current = 'recording'
    setError(null)

    // Auto-stop at maxDurationMs
    const maxDur = optionsRef.current.maxDurationMs ?? 60000
    if (maxDur > 0 && Number.isFinite(maxDur)) {
      maxDurationTimerRef.current = window.setTimeout(() => {
        stopRecording()
      }, maxDur)
    }
  }, [stopRecording])

  /**
   * Request recording start; handles lazy mic acquisition and Spacebar release race condition
   */
  const startRecording = useCallback(() => {
    if (optionsRef.current.enabled === false) return
    if (isRecordingRef.current) return
    if (statusRef.current === 'denied' || statusRef.current === 'unsupported') return

    recordingIntentRef.current = true
    isCancelledRef.current = false

    const existing = streamRef.current
    if (
      existing &&
      existing.active &&
      existing.getAudioTracks().some((t) => t.readyState === 'live')
    ) {
      beginRecordingWithStream(existing)
    } else {
      void ensureMicStream().then((stream) => {
        if (!isMountedRef.current) return
        // Edge case: Space released before getUserMedia resolves (must not get stuck recording)
        if (!recordingIntentRef.current) {
          if (statusRef.current === 'requesting-permission') {
            setStatus('idle')
            statusRef.current = 'idle'
          }
          return
        }
        if (stream) {
          beginRecordingWithStream(stream)
        }
      })
    }
  }, [ensureMicStream, beginRecordingWithStream])

  /**
   * Returns instantaneous input level (0..1) computed from AnalyserNode
   */
  const getInputLevel = useCallback((): number => {
    const analyser = analyserRef.current
    if (!analyser) return 0

    const data = new Uint8Array(analyser.fftSize)
    analyser.getByteTimeDomainData(data)

    let sumSquares = 0
    for (let i = 0; i < data.length; i++) {
      const normalized = (data[i] - 128) / 128
      sumSquares += normalized * normalized
    }

    const rms = Math.sqrt(sumSquares / data.length)
    // Scale RMS (~0..0.4 in normal speech) to a reactive 0..1 range
    return Math.min(1, Math.max(0, rms * 2.5))
  }, [])

  // Mount lifecycle: keep mic stream open while mounted, clean up on unmount
  useEffect(() => {
    isMountedRef.current = true

    if (optionsRef.current.enabled !== false) {
      void ensureMicStream()
    }

    return () => {
      isMountedRef.current = false
      recordingIntentRef.current = false

      if (maxDurationTimerRef.current) {
        window.clearTimeout(maxDurationTimerRef.current)
        maxDurationTimerRef.current = null
      }

      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          isCancelledRef.current = true
          mediaRecorderRef.current.stop()
        } catch {
          // ignore
        }
      }

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => {
          try {
            track.stop()
          } catch {
            // ignore
          }
        })
        streamRef.current = null
      }

      if (sourceNodeRef.current) {
        try {
          sourceNodeRef.current.disconnect()
        } catch {
          // ignore
        }
        sourceNodeRef.current = null
      }

      if (analyserRef.current) {
        try {
          analyserRef.current.disconnect()
        } catch {
          // ignore
        }
        analyserRef.current = null
      }
    }
  }, [ensureMicStream])

  // Spacebar and Escape keyboard listener
  useEffect(() => {
    if (typeof window === 'undefined') return

    const isSpaceKey = (e: KeyboardEvent) => e.code === 'Space' || e.key === ' '

    const handleKeyDown = (e: KeyboardEvent) => {
      const opts = optionsRef.current

      if (e.code === 'Escape' || e.key === 'Escape') {
        if (isRecordingRef.current || recordingIntentRef.current) {
          e.preventDefault()
          cancelRecording()
        }
        return
      }

      if (isSpaceKey(e)) {
        // Ensure every Spacebar keydown handler calls e.preventDefault() if document.activeElement is not an input/textarea
        const isInput = shouldIgnoreKeyboardTarget(e)
        if (!isInput) {
          e.preventDefault()
        } else {
          // Allow native typing inside inputs, textareas, contenteditables, and Monaco
          return
        }

        // If a non-text element (like a checkbox or button) had browser focus, blur it
        // so Spacebar never toggles or activates the focused control
        if (
          typeof document !== 'undefined' &&
          document.activeElement &&
          document.activeElement !== document.body
        ) {
          ;(document.activeElement as HTMLElement).blur?.()
        }

        if (opts.enabled === false || opts.bindSpacebar === false) return
        if (e.repeat) return

        if (!isRecordingRef.current && !recordingIntentRef.current) {
          startRecording()
        }
      }
    }

    // Release always stops, even if enabled/bindSpacebar flipped mid-hold (else stuck until maxDuration)
    const handleKeyUp = (e: KeyboardEvent) => {
      if (!isSpaceKey(e)) return

      // Ensure every Spacebar keyup handler calls e.preventDefault() if document.activeElement is not an input/textarea
      const isInput = shouldIgnoreKeyboardTarget(e)
      if (!isInput) {
        e.preventDefault()
      } else {
        return
      }

      if (
        isRecordingRef.current ||
        recordingIntentRef.current ||
        (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive')
      ) {
        stopRecording()
      }
    }

    // Window loses focus while Space is held -> keyup never arrives; finish the clip
    const handleBlur = () => {
      if (
        isRecordingRef.current ||
        recordingIntentRef.current ||
        (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive')
      ) {
        stopRecording()
      }
    }

    window.addEventListener('keydown', handleKeyDown, { capture: true, passive: false })
    window.addEventListener('keyup', handleKeyUp, { capture: true, passive: false })
    window.addEventListener('blur', handleBlur)

    return () => {
      window.removeEventListener('keydown', handleKeyDown, { capture: true })
      window.removeEventListener('keyup', handleKeyUp, { capture: true })
      window.removeEventListener('blur', handleBlur)
    }
  }, [startRecording, stopRecording, cancelRecording])

  // Disabling mid-recording discards the clip
  useEffect(() => {
    if (
      options.enabled === false &&
      (isRecordingRef.current ||
        recordingIntentRef.current ||
        (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive'))
    ) {
      cancelRecording()
    }
  }, [options.enabled, cancelRecording])

  return {
    status,
    isRecording,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
    getInputLevel,
  }
}

// =============================================================================
// Task B3: Audio Playback, Levels & Browser-TTS Fallback
// =============================================================================

export interface AudioPlayback {
  done: Promise<void>
  stop(): void
  getLevel(): number /* 0..1 */
  getProgress(): number /* 0..1 */
}

// Module-level references to active playback and active TTS utterance
let activePlayback: AudioPlayback | null = null
let activeUtterance: SpeechSynthesisUtterance | null = null

/**
 * Converts a base64 string (with or without data: URL prefix) to an ArrayBuffer.
 */
export function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const cleanB64 = b64.replace(/^data:[^;]+;base64,/, '').replace(/\s+/g, '')
  if (!cleanB64) {
    return new ArrayBuffer(0)
  }
  const binaryString =
    typeof window !== 'undefined' && typeof window.atob === 'function'
      ? window.atob(cleanB64)
      : typeof atob === 'function'
      ? atob(cleanB64)
      : ''
  const len = binaryString.length
  const bytes = new Uint8Array(len)
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i)
  }
  return bytes.buffer
}

let cachedVoices: SpeechSynthesisVoice[] = []

if (typeof window !== 'undefined' && window.speechSynthesis) {
  cachedVoices = window.speechSynthesis.getVoices()
  if (typeof window.speechSynthesis.addEventListener === 'function') {
    window.speechSynthesis.addEventListener('voiceschanged', () => {
      cachedVoices = window.speechSynthesis.getVoices()
    })
  } else {
    window.speechSynthesis.onvoiceschanged = () => {
      cachedVoices = window.speechSynthesis.getVoices()
    }
  }
}

/**
 * Voice selection preferring en-US voices (matching the backend Edge-TTS voice),
 * falling back to en-IN, then any English voice.
 */
export function getPreferredTTSVoice(): SpeechSynthesisVoice | null {
  if (typeof window === 'undefined' || !window.speechSynthesis) return null
  const live = window.speechSynthesis.getVoices()
  const voices = live && live.length > 0 ? live : cachedVoices
  if (!voices || voices.length === 0) return null

  // 1. Prefer en-US voice (matches backend TTS_VOICE en-US-AndrewNeural)
  const enUs = voices.find((v) => {
    const l = (v.lang || '').toLowerCase().replace('_', '-')
    return l === 'en-us' || l.startsWith('en-us')
  })
  if (enUs) return enUs

  // 2. Else en-IN voice
  const enIn = voices.find((v) => {
    const l = (v.lang || '').toLowerCase().replace('_', '-')
    return l === 'en-in' || l.startsWith('en-in') || /india/i.test(v.name)
  })
  if (enIn) return enIn

  // 3. Else any English voice
  const anyEn = voices.find((v) => (v.lang || '').toLowerCase().startsWith('en'))
  if (anyEn) return anyEn

  return voices[0] || null
}

/**
 * Stops any currently active playback (Web Audio source or Browser TTS)
 */
export function stopAllPlayback(): void {
  if (activePlayback) {
    const current = activePlayback
    activePlayback = null
    try {
      current.stop()
    } catch {}
  }
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    try {
      window.speechSynthesis.cancel()
    } catch {}
  }
  activeUtterance = null
}

/**
 * Decodes and plays a base64-encoded audio clip (MP3, WAV, WebM) via Web Audio API.
 * Pipeline: base64 -> ArrayBuffer -> decodeAudioData -> AudioBufferSourceNode -> AnalyserNode -> destination.
 *
 * Rules:
 * - One shared AudioContext
 * - One playback at a time (calling this stops previous playback)
 * - getProgress: calculated from AudioContext running clock (0..1)
 * - getLevel: instantaneous RMS amplitude (0..1) from AnalyserNode
 * - done: Promise that always resolves (on natural completion, stop, or decode error)
 */
export function playBase64Audio(
  b64: string,
  _mimeType: string = 'audio/mpeg'
): AudioPlayback {
  // Enforce single active playback
  stopAllPlayback()

  let isStopped = false
  let isEnded = false
  let isStarted = false
  let sourceNode: AudioBufferSourceNode | null = null
  let analyserNode: AnalyserNode | null = null
  let duration = 0
  let startCtxTime = 0
  let stoppedProgress = 0

  let resolveDone: () => void
  const done = new Promise<void>((resolve) => {
    resolveDone = resolve
  })

  function cleanupNodes() {
    if (sourceNode) {
      try {
        sourceNode.disconnect()
      } catch {}
      sourceNode = null
    }
    if (analyserNode) {
      try {
        analyserNode.disconnect()
      } catch {}
      analyserNode = null
    }
  }

  function handleFinish() {
    if (isEnded) return
    isEnded = true
    if (activePlayback === playback) {
      activePlayback = null
    }
    cleanupNodes()
    resolveDone()
  }

  function stop() {
    if (isStopped || isEnded) return
    isStopped = true
    if (activePlayback === playback) {
      activePlayback = null
    }
    const ctx = getSharedAudioContext()
    if (duration > 0 && ctx && isStarted) {
      stoppedProgress = Math.min(1, Math.max(0, (ctx.currentTime - startCtxTime) / duration))
    }
    if (sourceNode) {
      try {
        sourceNode.stop()
      } catch {}
    }
    cleanupNodes()
    resolveDone()
  }

  function getLevel(): number {
    if (isStopped || isEnded || !isStarted || !analyserNode) return 0
    try {
      const data = new Uint8Array(analyserNode.fftSize)
      analyserNode.getByteTimeDomainData(data)
      let sumSquares = 0
      for (let i = 0; i < data.length; i++) {
        const normalized = (data[i] - 128) / 128
        sumSquares += normalized * normalized
      }
      const rms = Math.sqrt(sumSquares / data.length)
      return Math.min(1, Math.max(0, rms * 2.5))
    } catch {
      return 0
    }
  }

  function getProgress(): number {
    if (isStopped) return stoppedProgress
    if (isEnded) return 1
    const ctx = getSharedAudioContext()
    if (!ctx || !isStarted || duration <= 0) return 0
    const elapsed = Math.max(0, ctx.currentTime - startCtxTime)
    return Math.min(1, Math.max(0, elapsed / duration))
  }

  const playback: AudioPlayback = {
    done,
    stop,
    getLevel,
    getProgress,
  }

  activePlayback = playback

  const ctx = getSharedAudioContext()
  if (!ctx || !b64 || !b64.trim()) {
    handleFinish()
    return playback
  }

  unlockAudio()

  try {
    const arrayBuffer = base64ToArrayBuffer(b64)
    if (arrayBuffer.byteLength === 0) {
      handleFinish()
      return playback
    }

    const decodePromise = new Promise<AudioBuffer>((res, rej) => {
      // slice(0) to pass a clean copy because decodeAudioData can neuter the ArrayBuffer
      const copy = arrayBuffer.slice(0)
      const p = ctx.decodeAudioData(copy, res, rej)
      if (p && typeof (p as Promise<AudioBuffer>).then === 'function') {
        ;(p as Promise<AudioBuffer>).then(res, rej)
      }
    })

    decodePromise
      .then(async (audioBuffer) => {
        if (isStopped || isEnded) return

        duration = audioBuffer.duration

        if (ctx.state === 'suspended') {
          try {
            await ctx.resume()
          } catch {}
        }

        if (isStopped || isEnded) return

        const source = ctx.createBufferSource()
        source.buffer = audioBuffer
        sourceNode = source

        const analyser = ctx.createAnalyser()
        analyser.fftSize = 256
        analyserNode = analyser

        source.connect(analyser)
        analyser.connect(ctx.destination)

        source.onended = () => {
          handleFinish()
        }

        startCtxTime = ctx.currentTime
        isStarted = true
        source.start(0)
      })
      .catch((err) => {
        console.warn('[playBase64Audio] Failed to decode audio data:', err)
        handleFinish()
      })
  } catch (err) {
    console.warn('[playBase64Audio] Failed to process audio base64:', err)
    handleFinish()
  }

  return playback
}

/**
 * Speaks text using the browser's native SpeechSynthesis API as fallback when audio_base64 is empty.
 *
 * Rules:
 * - Preferred voice: en-US (American English), else en-IN, else any English
 * - getProgress: tracked from 'boundary' event charIndex, with smooth time-based estimate fallback
 * - getLevel: simulated organic speech level (0..1) while speaking; 0 when silent or stopped
 * - stop(): cancels SpeechSynthesis immediately
 * - One playback at a time (calling this stops previous playback)
 * - done: Promise that always resolves on completion or stop
 */
export function speakWithBrowserTTS(text: string): AudioPlayback {
  stopAllPlayback()

  let isStopped = false
  let isEnded = false
  let isStarted = false
  let speakStartTime = 0
  let hasReceivedBoundary = false
  let latestCharIndex = 0
  let stoppedProgress = 0
  let keepAliveTimer: number | null = null
  let startFallbackTimer: number | null = null

  let resolveDone: () => void
  const done = new Promise<void>((resolve) => {
    resolveDone = resolve
  })

  function cleanup() {
    if (keepAliveTimer !== null) {
      window.clearInterval(keepAliveTimer)
      keepAliveTimer = null
    }
    if (startFallbackTimer !== null) {
      if (typeof window !== 'undefined' && typeof window.clearTimeout === 'function') {
        window.clearTimeout(startFallbackTimer)
      } else {
        clearTimeout(startFallbackTimer)
      }
      startFallbackTimer = null
    }
    if (activeUtterance === utterance) {
      activeUtterance = null
    }
  }

  function handleFinish() {
    if (isEnded) return
    isEnded = true
    if (activePlayback === playback) {
      activePlayback = null
    }
    cleanup()
    resolveDone()
  }

  function stop() {
    if (isStopped || isEnded) return
    stoppedProgress = getProgress()
    isStopped = true
    if (activePlayback === playback) {
      activePlayback = null
    }
    cleanup()
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      try {
        window.speechSynthesis.cancel()
      } catch {}
    }
    handleFinish()
  }

  const cleanText = text ? text.trim() : ''
  const wordCount = cleanText ? cleanText.split(/\s+/).length : 0
  // Standard speech rate: ~2.5 words per second
  const estimatedDurationSec = Math.max(1, wordCount / 2.5)

  function getProgress(): number {
    if (isStopped) return stoppedProgress
    if (isEnded) return 1
    if (!cleanText) return 0

    // Gracefully recover start if onstart event never fired in browser
    if (!isStarted && typeof window !== 'undefined' && window.speechSynthesis?.speaking) {
      isStarted = true
      if (!speakStartTime) speakStartTime = performance.now()
    }
    if (!isStarted) return 0

    const elapsedSec = (performance.now() - speakStartTime) / 1000

    if (hasReceivedBoundary && cleanText.length > 0) {
      const charProgress = latestCharIndex / cleanText.length
      const timeEst = elapsedSec / estimatedDurationSec
      return Math.min(0.98, Math.max(charProgress, timeEst * 0.9))
    }

    // Time-based estimate if boundary events never fire in current browser/voice
    const timeProgress = elapsedSec / estimatedDurationSec
    return Math.min(0.95, Math.max(0, timeProgress))
  }

  function getLevel(): number {
    if (isStopped || isEnded || !isStarted) return 0
    const t = (performance.now() - speakStartTime) / 1000
    // Dynamic speech cadence simulation (0.08..0.85 range)
    const wave1 = Math.sin(t * 14) * 0.18
    const wave2 = Math.sin(t * 6) * 0.14
    const wave3 = Math.cos(t * 26) * 0.08
    const level = 0.38 + wave1 + wave2 + wave3
    return Math.min(1, Math.max(0.08, level))
  }

  const playback: AudioPlayback = {
    done,
    stop,
    getLevel,
    getProgress,
  }

  activePlayback = playback

  if (
    typeof window === 'undefined' ||
    !window.speechSynthesis ||
    !cleanText
  ) {
    handleFinish()
    return playback
  }

  let utterance: SpeechSynthesisUtterance

  try {
    window.speechSynthesis.cancel()

    utterance = new SpeechSynthesisUtterance(cleanText)
    activeUtterance = utterance

    const preferredVoice = getPreferredTTSVoice()
    if (preferredVoice) {
      utterance.voice = preferredVoice
      utterance.lang = preferredVoice.lang
    } else {
      utterance.lang = 'en-US'
    }
    utterance.rate = 1.0
    utterance.pitch = 1.0

    utterance.onstart = () => {
      isStarted = true
      speakStartTime = performance.now()
    }

    utterance.onboundary = (e: SpeechSynthesisEvent) => {
      hasReceivedBoundary = true
      if (typeof e.charIndex === 'number' && e.charIndex >= 0) {
        latestCharIndex = e.charIndex
      }
    }

    utterance.onend = () => {
      handleFinish()
    }

    utterance.onerror = () => {
      // Always resolve on error/cancel per spec
      handleFinish()
    }

    // Chrome keep-alive guard for longer speech
    keepAliveTimer = window.setInterval(() => {
      if (typeof window !== 'undefined' && window.speechSynthesis && window.speechSynthesis.speaking) {
        if (typeof window.speechSynthesis.pause === 'function') window.speechSynthesis.pause()
        if (typeof window.speechSynthesis.resume === 'function') window.speechSynthesis.resume()
      }
    }, 10000)

    window.speechSynthesis.speak(utterance)

    // Fallback if browser voice fails to trigger onstart
    const scheduleTimeout =
      typeof window !== 'undefined' && typeof window.setTimeout === 'function'
        ? window.setTimeout
        : setTimeout

    startFallbackTimer = (scheduleTimeout as typeof setTimeout)(() => {
      if (!isStarted && !isEnded && !isStopped) {
        isStarted = true
        if (!speakStartTime) speakStartTime = performance.now()
      }
    }, 150) as unknown as number
  } catch (err) {
    console.warn('[speakWithBrowserTTS] SpeechSynthesis failed:', err)
    handleFinish()
  }

  return playback
}
