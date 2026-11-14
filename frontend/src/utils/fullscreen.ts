/**
 * Fullscreen Proctoring Utility (frontend/src/utils/fullscreen.ts)
 * 
 * Provides synchronous user-gesture-safe fullscreen requests with vendor prefixes,
 * and robust detection of embedded webview/iframe environments where
 * document.fullscreenEnabled is false.
 */

export const isFullscreenSupported = (): boolean => {
  if (typeof document === 'undefined') return false
  return Boolean(
    document.fullscreenEnabled ??
    (document as any).webkitFullscreenEnabled ??
    (document as any).mozFullScreenEnabled ??
    (document as any).msFullscreenEnabled ??
    false
  )
}

export const isInFullscreen = (): boolean => {
  if (typeof document === 'undefined') return false
  return Boolean(
    document.fullscreenElement ||
    (document as any).webkitFullscreenElement ||
    (document as any).mozFullScreenElement ||
    (document as any).msFullscreenElement
  )
}

/**
 * Triggers browser fullscreen mode synchronously.
 * MUST be called as the very first line inside an onClick handler
 * before any await, dispatch, or asynchronous tick to retain the browser user gesture token.
 */
export const triggerFullscreen = (): boolean => {
  if (typeof document === 'undefined') return false

  if (isInFullscreen()) {
    return true
  }

  // Gracefully handle embedded webview / iframe restrictions
  if (!isFullscreenSupported()) {
    console.warn(
      '[Proctor] Fullscreen mode is not enabled or available in this environment (e.g. iframe or IDE webview restriction).'
    )
    return false
  }

  const elem = document.documentElement as HTMLElement & {
    webkitRequestFullscreen?: () => Promise<void>
    mozRequestFullScreen?: () => Promise<void>
    msRequestFullscreen?: () => Promise<void>
  }

  try {
    if (elem.requestFullscreen) {
      elem.requestFullscreen().catch(err => {
        console.warn('[Proctor] elem.requestFullscreen() was rejected by browser:', err)
      })
      return true
    } else if (elem.webkitRequestFullscreen) {
      elem.webkitRequestFullscreen()
      return true
    } else if (elem.msRequestFullscreen) {
      elem.msRequestFullscreen()
      return true
    } else if (elem.mozRequestFullScreen) {
      elem.mozRequestFullScreen()
      return true
    }
  } catch (err) {
    console.warn('[Proctor] Synchronous fullscreen trigger threw an error:', err)
  }
  return false
}

export const exitFullscreenSafely = async (): Promise<void> => {
  if (typeof document === 'undefined') return
  try {
    const doc = document as Document & {
      webkitExitFullscreen?: () => Promise<void>
      mozCancelFullScreen?: () => Promise<void>
      msExitFullscreen?: () => Promise<void>
    }
    if (document.fullscreenElement) {
      await document.exitFullscreen()
    } else if (doc.webkitExitFullscreen && (document as any).webkitFullscreenElement) {
      await doc.webkitExitFullscreen()
    } else if (doc.msExitFullscreen && (document as any).msFullscreenElement) {
      await doc.msExitFullscreen()
    } else if (doc.mozCancelFullScreen && (document as any).mozFullScreenElement) {
      await doc.mozCancelFullScreen()
    }
  } catch (err) {
    console.warn('[Proctor] Exit fullscreen safely failed:', err)
  }
}
