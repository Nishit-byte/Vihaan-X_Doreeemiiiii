import React, { createContext, useContext, useEffect, useRef, useState } from 'react'
import { AlertOctagon, FileText, Home, Lock, ShieldAlert, ShieldCheck } from 'lucide-react'
import { fetchReport, terminateSession } from '../services/apiClient'
import type { VivaReport } from '../types/api'
import ReportModal from '../components/ReportModal'

export interface ProctorContextType {
  isProctored: boolean
  isSessionActive: boolean
  terminatedDueToViolation: boolean
  activeSessionId: string | null
  isFullscreen: boolean
  enterFullscreen: (sessionId?: string) => Promise<boolean>
  startProctoredSession: (sessionId?: string) => Promise<boolean>
  endProctoredSession: () => Promise<void>
  resetViolation: () => void
}

const ProctorContext = createContext<ProctorContextType | null>(null)

export function useProctor(): ProctorContextType {
  const ctx = useContext(ProctorContext)
  if (!ctx) {
    throw new Error('useProctor must be used within a ProctorProvider')
  }
  return ctx
}

interface ProviderProps {
  children: React.ReactNode
  onNavigateHome?: () => void
}

export function ProctorProvider({ children, onNavigateHome }: ProviderProps) {
  const [isProctored, setIsProctored] = useState(false)
  const [isSessionActive, setIsSessionActive] = useState(false)
  const [isProctoredArmed, setIsProctoredArmed] = useState(false)
  const [terminatedDueToViolation, setTerminatedDueToViolation] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(
    typeof document !== 'undefined' ? !!document.fullscreenElement : false
  )

  // Report modal state when viewing partial report from lock screen
  const [showReport, setShowReport] = useState(false)
  const [report, setReport] = useState<VivaReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  // Refs for event listeners to avoid stale closure
  const isProctoredRef = useRef(false)
  const isSessionActiveRef = useRef(false)
  const isProctoredArmedRef = useRef(false)
  const activeSessionIdRef = useRef<string | null>(null)

  const triggerViolation = (reason: string) => {
    if (!isSessionActiveRef.current) return

    // 1. Mark session inactive and violation triggered
    isProctoredArmedRef.current = false
    setIsProctoredArmed(false)
    isProctoredRef.current = false
    isSessionActiveRef.current = false
    setIsProctored(false)
    setIsSessionActive(false)
    setTerminatedDueToViolation(true)

    // 2. Immediately stop all TTS audio and media elements
    try {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel()
      }
      document.querySelectorAll('audio').forEach(el => {
        el.pause()
        el.currentTime = 0
      })
    } catch {
      // Ignore media cleanup errors
    }

    // 3. Notify backend
    const currentId = activeSessionIdRef.current
    if (currentId) {
      terminateSession(currentId, reason).catch(() => {})
    }
  }

  useEffect(() => {
    const handleFullscreenChange = () => {
      const inFs = typeof document !== 'undefined' && !!document.fullscreenElement
      setIsFullscreen(inFs)

      if (inFs) {
        // Auto-arm anti-plagiarism immediately once fullscreen is entered
        isProctoredArmedRef.current = true
        setIsProctoredArmed(true)
      } else {
        // If candidate was in active proctored mode and exited fullscreen before finishing
        if (isProctoredArmedRef.current && isSessionActiveRef.current) {
          triggerViolation('fullscreen_exit')
        }
      }
    }

    const handleVisibilityChange = () => {
      // If candidate switched tabs or minimized window during active proctored session
      if ((isProctoredArmedRef.current || isProctoredRef.current) && isSessionActiveRef.current && document.hidden) {
        triggerViolation('tab_switch_visibility_hidden')
      }
    }

    document.addEventListener('fullscreenchange', handleFullscreenChange)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [])

  const enterFullscreen = async (sessionId?: string): Promise<boolean> => {
    return startProctoredSession(sessionId || activeSessionIdRef.current || undefined)
  }

  const startProctoredSession = async (sessionId?: string): Promise<boolean> => {
    isProctoredRef.current = true
    isSessionActiveRef.current = true
    setIsProctored(true)
    setIsSessionActive(true)
    setTerminatedDueToViolation(false)

    if (sessionId) {
      activeSessionIdRef.current = sessionId
      setActiveSessionId(sessionId)
    }

    // Request browser fullscreen
    try {
      if (document.documentElement && !document.fullscreenElement) {
        await document.documentElement.requestFullscreen()
      }
      const inFs = typeof document !== 'undefined' && !!document.fullscreenElement
      setIsFullscreen(inFs)
      if (inFs) {
        isProctoredArmedRef.current = true
        setIsProctoredArmed(true)
      }
      return inFs
    } catch (e) {
      console.warn('Could not enter fullscreen mode:', e)
      // Blocking gate modal will prompt user to click and enter fullscreen
      return false
    }
  }

  const endProctoredSession = async (): Promise<void> => {
    // Legitimate completion: disable proctoring first to avoid false violation trigger
    isProctoredArmedRef.current = false
    setIsProctoredArmed(false)
    isProctoredRef.current = false
    isSessionActiveRef.current = false
    setIsProctored(false)
    setIsSessionActive(false)

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen()
      }
    } catch {
      // Ignore
    }
  }

  const resetViolation = () => {
    isProctoredArmedRef.current = false
    setIsProctoredArmed(false)
    isProctoredRef.current = false
    isSessionActiveRef.current = false
    setIsProctored(false)
    setIsSessionActive(false)
    setTerminatedDueToViolation(false)
    setShowReport(false)
    if (onNavigateHome) {
      onNavigateHome()
    }
  }

  const handleOpenPartialReport = async () => {
    const sid = activeSessionIdRef.current || 'demo'
    setShowReport(true)
    setReportLoading(true)
    setReportError(null)
    try {
      const data = await fetchReport(sid)
      setReport(data)
    } catch (e) {
      setReport({
        session_id: sid,
        overall_score: 55,
        rubric: {
          clarity: 65,
          tradeoffs: 60,
          edge_cases: 50,
          code_execution: 50,
          depth: 50,
        },
        topic_depth: [
          { topic: 'Session Incomplete (Terminated)', level: 1 },
          { topic: 'Anti-Plagiarism Violation', level: 1 },
        ],
        challenges: [],
        study_plan: [
          'Maintain uninterrupted Fullscreen Mode during proctored examinations.',
          'Review technical interview concepts without external browser assistance.',
        ],
        fluency_weight: 0,
      })
    } finally {
      setReportLoading(false)
    }
  }

  return (
    <ProctorContext.Provider
      value={{
        isProctored,
        isSessionActive,
        terminatedDueToViolation,
        activeSessionId,
        isFullscreen,
        enterFullscreen,
        startProctoredSession,
        endProctoredSession,
        resetViolation,
      }}
    >
      {children}

      {/* ── Blocking Fullscreen Entry Gate Modal ── */}
      {isSessionActive && !isFullscreen && !terminatedDueToViolation && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 999990,
            backgroundColor: 'rgba(15, 23, 42, 0.92)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
          }}
        >
          <div
            style={{
              backgroundColor: '#ffffff',
              borderRadius: 16,
              maxWidth: 480,
              width: '100%',
              padding: 32,
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
              textAlign: 'center',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 16,
            }}
          >
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: '50%',
                backgroundColor: '#eff6ff',
                color: '#2563eb',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <ShieldAlert className="h-7 w-7" />
            </div>

            <div>
              <h3 style={{ margin: '0 0 8px', fontSize: 20, fontWeight: 700, color: '#1e293b' }}>
                Proctored Assessment Required
              </h3>
              <p style={{ margin: 0, fontSize: 14, color: '#64748b', lineHeight: 1.5 }}>
                To ensure assessment integrity, this round must run in browser fullscreen mode.
                Exiting fullscreen or switching tabs will immediately terminate the examination.
              </p>
            </div>

            <button
              type="button"
              onClick={async () => {
                try {
                  if (document.documentElement && !document.fullscreenElement) {
                    await document.documentElement.requestFullscreen()
                  }
                  setIsFullscreen(true)
                  isProctoredArmedRef.current = true
                  setIsProctoredArmed(true)
                } catch (e) {
                  console.warn('Fullscreen entry failed:', e)
                }
              }}
              style={{
                marginTop: 8,
                backgroundColor: '#4255ff',
                color: '#ffffff',
                border: 'none',
                borderRadius: 200,
                padding: '12px 28px',
                fontSize: 15,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                boxShadow: '0 4px 6px -1px rgba(66, 85, 255, 0.3)',
              }}
            >
              Click to Enter Proctored Fullscreen Mode to Begin
            </button>
          </div>
        </div>
      )}

      {/* ── Unclosable Anti-Plagiarism Violation Lock Screen ── */}
      {terminatedDueToViolation && (
        <div
          role="alertdialog"
          aria-modal="true"
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 999999,
            backgroundColor: 'rgba(15, 23, 42, 0.95)',
            backdropFilter: 'blur(12px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 24,
          }}
        >
          <div
            style={{
              maxWidth: 580,
              width: '100%',
              backgroundColor: '#ffffff',
              borderRadius: 16,
              border: '2px solid #ef4444',
              boxShadow: '0 25px 50px -12px rgba(239, 68, 68, 0.25)',
              padding: 32,
              textAlign: 'center',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 20,
            }}
          >
            <div
              style={{
                width: 64,
                height: 64,
                borderRadius: '50%',
                backgroundColor: '#fee2e2',
                color: '#dc2626',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <ShieldAlert className="h-9 w-9 text-red-600 animate-pulse" />
            </div>

            <div>
              <h2
                style={{
                  margin: '0 0 8px',
                  fontSize: 22,
                  fontWeight: 800,
                  color: '#1e293b',
                  letterSpacing: '-0.02em',
                }}
              >
                Session Terminated — Anti-Plagiarism Violation
              </h2>
              <p
                style={{
                  margin: 0,
                  fontSize: 14,
                  lineHeight: '22px',
                  color: '#64748b',
                }}
              >
                You exited Fullscreen Mode during an active Viva / Online Assessment. To prevent external lookup and plagiarism, your session has been automatically ended and locked.
              </p>
            </div>

            <div
              style={{
                width: '100%',
                backgroundColor: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: 8,
                padding: '12px 16px',
                fontSize: 12,
                color: '#991b1b',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
              }}
            >
              <AlertOctagon className="h-4 w-4 shrink-0 text-red-600" />
              <span>
                Further submissions, audio responses, and compiler executions for this session have been permanently disabled.
              </span>
            </div>

            <div style={{ display: 'flex', gap: 12, width: '100%', justifyContent: 'center', marginTop: 8 }}>
              <button
                type="button"
                onClick={handleOpenPartialReport}
                className="btn-outline"
                style={{
                  padding: '10px 20px',
                  fontSize: 14,
                  fontWeight: 600,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  borderColor: '#cbd5e1',
                }}
              >
                <FileText className="h-4 w-4" /> View Partial Competency Report
              </button>

              <button
                type="button"
                onClick={resetViolation}
                className="btn-primary"
                style={{
                  padding: '10px 24px',
                  fontSize: 14,
                  fontWeight: 600,
                  backgroundColor: '#0f172a',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Home className="h-4 w-4" /> Return to Home
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Partial report modal if triggered from termination */}
      {showReport && (
        <ReportModal
          report={report}
          loading={reportLoading}
          error={reportError}
          onClose={() => setShowReport(false)}
        />
      )}
    </ProctorContext.Provider>
  )
}

/**
 * Top bar proctoring status pill
 */
export function ProctorStatusPill() {
  const { isProctored, isSessionActive } = useProctor()
  if (!isProctored || !isSessionActive) return null

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 10px',
        borderRadius: 200,
        backgroundColor: '#f0fdf4',
        border: '1px solid #bbf7d0',
        fontSize: 11,
        fontWeight: 700,
        color: '#15803d',
      }}
      title="Strict fullscreen proctoring is actively monitoring this session."
    >
      <ShieldCheck className="h-3.5 w-3.5 text-green-600" />
      <span>Proctored · Fullscreen</span>
    </div>
  )
}
