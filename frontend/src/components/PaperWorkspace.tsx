import { useEffect, useId, useRef, useState } from 'react'
import type { PaperIndex } from '../types/api'

interface Props {
  paper: PaperIndex
  activeNodeId: string | null | undefined
  excerpt: string | null | undefined
}

const nodeIdOf = (el: Element) => el.id.match(/flowchart-(.+)-\d+$/)?.[1] ?? null

export default function PaperWorkspace({ paper, activeNodeId, excerpt }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const uid = useId().replace(/:/g, '')
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string | null>(null)
  const [labels, setLabels] = useState<Record<string, string>>({})

  // Render diagram once per paper
  useEffect(() => {
    let cancelled = false
    setReady(false); setError(null)
    ;(async () => {
      try {
        const mermaid = (await import('mermaid')).default
        mermaid.initialize({
          startOnLoad: false, theme: 'base',
          themeVariables: {
            background: '#080e21', primaryColor: '#0f172b', primaryTextColor: '#e2e8f0',
            primaryBorderColor: '#314158', lineColor: '#90a1b9', fontFamily: 'Public Sans, sans-serif', fontSize: '14px',
          },
          flowchart: { curve: 'basis', padding: 12 },
        })
        const { svg } = await mermaid.render('vv' + uid, paper.mermaid)
        if (cancelled || !hostRef.current) return
        hostRef.current.innerHTML = svg
        const map: Record<string, string> = {}
        hostRef.current.querySelectorAll('g.node').forEach(g => {
          const id = nodeIdOf(g); if (id) map[id] = (g.textContent ?? '').trim()
        })
        setLabels(map); setReady(true)
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Could not render diagram')
      }
    })()
    return () => { cancelled = true }
  }, [paper.mermaid, uid])

  // Examiner moved to a new node: drop manual selection
  useEffect(() => { setPicked(null) }, [activeNodeId])

  const shownId = picked ?? activeNodeId ?? null
  useEffect(() => {
    if (!ready || !hostRef.current) return
    hostRef.current.querySelectorAll('g.node').forEach(g =>
      g.classList.toggle('vv-active', nodeIdOf(g) === shownId))
  }, [ready, shownId])

  const text = picked ? paper.nodes[picked] : (excerpt ?? (activeNodeId ? paper.nodes[activeNodeId] : null))

  return (
    <div className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex items-center gap-2 border-b border-steel-outline p-2">
        <span className="rounded-md bg-deep-slate px-2.5 py-1.5 text-sm font-medium text-signal-white">Paper map</span>
        <span className="ml-auto text-xs text-muted-fog">Click a stage to read its excerpt</span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4">
        {error ? (
          <div>
            <p className="text-sm text-pale-frost">The diagram could not be drawn: {error}</p>
            <pre className="mt-2 overflow-auto rounded-md bg-void-canvas p-3 font-mono text-sm text-muted-fog">{paper.mermaid}</pre>
          </div>
        ) : (
          <>
            {!ready && <p className="text-sm text-muted-fog">Drawing paper map…</p>}
            <div
              ref={hostRef}
              className="mermaid-host flex justify-center"
              onClick={e => {
                const g = (e.target as Element).closest('g.node'); if (!g) return
                const id = nodeIdOf(g); if (id && paper.nodes[id]) setPicked(id)
              }}
            />
          </>
        )}
      </div>

      <div className="border-t border-steel-outline p-3">
        <div className="panel bg-void-canvas p-3" style={{ background: 'var(--color-void-canvas)' }}>
          {text ? (
            <>
              <div className="flex items-center gap-2 text-sm font-semibold text-pale-frost">
                <span className="rounded-full px-2 py-0.5 text-xs text-nuxt-signal ring-1 ring-inset ring-nuxt-signal/25">{shownId}</span>
                {shownId && labels[shownId]}
              </div>
              <p className="mt-2 text-sm leading-6 text-muted-fog">{text}</p>
            </>
          ) : (
            <p className="text-sm text-muted-fog">The examiner will highlight a stage here and show its excerpt.</p>
          )}
        </div>
      </div>
    </div>
  )
}
