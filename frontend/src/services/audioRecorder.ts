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
 * Checks whether the keyboard event target is an interactive text input
 * or inside Monaco Editor, where Spacebar must NOT be intercepted.
 */
export function shouldIgnoreKeyboardTarget(e: KeyboardEvent): boolean {
  const elementsToCheck: (HTMLElement | null)[] = [
    e.target as HTMLElement | null,
    typeof document !== 'undefined' ? (document.activeElement as HTMLElement | null) : null,
  ]

  for (const el of elementsToCheck) {
    if (!el) continue
    const tagName = el.tagName ? el.tagName.toUpperCase() : ''
    if (tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT') {
      return true
    }
    if (el.isContentEditable || (el.getAttribute && el.getAttribute('contenteditable') === 'true')) {
      return true
    }
    if (typeof el.closest === 'function' && el.closest('.monaco-editor')) {
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

    const handleKeyDown = (e: KeyboardEvent) => {
      const opts = optionsRef.current
      if (opts.enabled === false) return

      if (e.code === 'Escape') {
        if (isRecordingRef.current || recordingIntentRef.current) {
          e.preventDefault()
          cancelRecording()
        }
        return
      }

      if (e.code === 'Space') {
        if (opts.bindSpacebar === false) return
        if (e.repeat) return
        if (shouldIgnoreKeyboardTarget(e)) return

        // Prevent page scroll when handling push-to-talk
        e.preventDefault()

        if (!isRecordingRef.current && !recordingIntentRef.current) {
          startRecording()
        }
      }
    }

    // Release always stops, even if enabled/bindSpacebar flipped mid-hold (else stuck until maxDuration)
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      if (isRecordingRef.current || recordingIntentRef.current) {
        e.preventDefault()
        stopRecording()
      }
    }

    // Window loses focus while Space is held -> keyup never arrives; finish the clip
    const handleBlur = () => {
      if (isRecordingRef.current || recordingIntentRef.current) stopRecording()
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)
    window.addEventListener('blur', handleBlur)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
      window.removeEventListener('blur', handleBlur)
    }
  }, [startRecording, stopRecording, cancelRecording])

  // Disabling mid-recording discards the clip
  useEffect(() => {
    if (options.enabled === false) cancelRecording()
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
// Stubs for Task B3 (playBase64Audio, speakWithBrowserTTS, stopAllPlayback)
// =============================================================================

export interface AudioPlayback {
  done: Promise<void>
  stop(): void
  getLevel(): number /* 0..1 */
  getProgress(): number /* 0..1 */
}

export function playBase64Audio(
  _b64: string,
  _mimeType: string = 'audio/mpeg'
): AudioPlayback {
  return {
    done: Promise.resolve(),
    stop: () => {},
    getLevel: () => 0,
    getProgress: () => 0,
  }
}

export function speakWithBrowserTTS(_text: string): AudioPlayback {
  return {
    done: Promise.resolve(),
    stop: () => {},
    getLevel: () => 0,
    getProgress: () => 0,
  }
}

export function stopAllPlayback(): void {
  // Implemented in Task B3
}
