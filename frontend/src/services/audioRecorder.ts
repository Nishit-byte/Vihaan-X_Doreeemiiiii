/**
 * M3 Voice Pipeline — Audio Recorder & Playback Service (Stubs for Task B1)
 *
 * Implements the exact signatures from CONTEXT §5.8.
 * Real implementations will be added in:
 * - B2: usePushToTalkRecorder, blobToBase64
 * - B3: playBase64Audio, speakWithBrowserTTS, stopAllPlayback, unlockAudio
 */

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

export function usePushToTalkRecorder(
  _options: UsePushToTalkRecorderOptions
): UsePushToTalkRecorderReturn {
  // Stub for Task B1 — implemented in Task B2
  return {
    status: 'idle',
    isRecording: false,
    error: null,
    startRecording: () => {},
    stopRecording: () => {},
    cancelRecording: () => {},
    getInputLevel: () => 0,
  }
}

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
  // Stub for Task B1 — implemented in Task B3
  return {
    done: Promise.resolve(),
    stop: () => {},
    getLevel: () => 0,
    getProgress: () => 0,
  }
}

export function speakWithBrowserTTS(_text: string): AudioPlayback {
  // Stub for Task B1 — implemented in Task B3
  return {
    done: Promise.resolve(),
    stop: () => {},
    getLevel: () => 0,
    getProgress: () => 0,
  }
}

export function stopAllPlayback(): void {
  // Stub for Task B1 — implemented in Task B3
}

export function unlockAudio(): void {
  // Stub for Task B1 — implemented in Task B3
}

export function blobToBase64(blob: Blob): Promise<string> {
  // Utility for converting audio Blob to raw base64 string (no data: prefix)
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = String(reader.result || '')
      const b64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl
      resolve(b64)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

