import { useEffect } from 'react'
import { Check, Minus, X } from 'lucide-react'
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from 'recharts'
import type { VivaReport } from '../types/api'

interface Props { report: VivaReport | null; loading: boolean; error: string | null; onClose: () => void }

const RUBRIC: { key: keyof VivaReport['rubric']; label: string; weight: number }[] = [
  { key: 'clarity', label: 'Clarity', weight: 30 },
  { key: 'tradeoffs', label: 'Trade-offs', weight: 25 },
  { key: 'edge_cases', label: 'Edge cases', weight: 20 },
  { key: 'code_execution', label: 'Code execution', weight: 15 },
  { key: 'depth', label: 'Depth', weight: 10 },
]

export default function ReportModal({ report, loading, error, onClose }: Props) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-void-canvas/90 p-6" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Viva report"
        className="panel w-full max-w-3xl p-6" onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <h2 className="text-lg font-medium text-pale-frost">Viva report</h2>
          <button onClick={onClose} aria-label="Close report" className="rounded-md p-1 text-muted-fog hover:text-signal-white">
            <X className="h-5 w-5" />
          </button>
        </div>

        {loading && <p className="mt-6 text-sm text-muted-fog">Grading your viva…</p>}
        {error && <p className="mt-6 text-sm text-pale-frost">Could not load the report: {error}</p>}

        {report && (
          <div className="mt-4 space-y-8">
            <div className="flex items-end gap-3">
              <span className="text-[48px] font-bold leading-none tracking-[-1.2px] text-signal-white">{Math.round(report.overall_score)}</span>
              <span className="pb-1 text-sm text-muted-fog">overall score out of 100</span>
            </div>

            <section>
              <h3 className="text-sm font-semibold text-pale-frost">Rubric</h3>
              <ul className="mt-3 space-y-3">
                {RUBRIC.map(r => (
                  <li key={r.key}>
                    <div className="flex justify-between text-sm">
                      <span className="text-pale-frost">{r.label} <span className="text-muted-fog">({r.weight}%)</span></span>
                      <span className="text-muted-fog">{Math.round(report.rubric[r.key])}</span>
                    </div>
                    <div className="mt-1 h-2 rounded-full bg-deep-slate" role="progressbar"
                      aria-valuenow={report.rubric[r.key]} aria-valuemin={0} aria-valuemax={100} aria-label={r.label}>
                      <div className="h-2 rounded-full bg-nuxt-signal" style={{ width: `${Math.max(0, Math.min(100, report.rubric[r.key]))}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <h3 className="text-sm font-semibold text-pale-frost">Topic depth (L1 recall to L4 mutation)</h3>
              <div className="mt-2 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={report.topic_depth} outerRadius="75%">
                    <PolarGrid stroke="#1d293d" />
                    <PolarAngleAxis dataKey="topic" tick={{ fill: '#90a1b9', fontSize: 12 }} />
                    <PolarRadiusAxis domain={[0, 4]} tickCount={5} tick={{ fill: '#314158', fontSize: 10 }} axisLine={false} />
                    <Radar dataKey="level" stroke="#00dc82" fill="#00dc82" fillOpacity={0.2} isAnimationActive={false} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section>
              <h3 className="text-sm font-semibold text-pale-frost">Code challenges</h3>
              {report.challenges.length === 0 ? (
                <p className="mt-2 flex items-center gap-2 text-sm text-muted-fog"><Minus className="h-4 w-4" />No challenges in this viva.</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {report.challenges.map(c => (
                    <li key={c.description} className="flex items-center gap-2 text-sm text-muted-fog">
                      {c.passed ? <Check className="h-4 w-4 text-nuxt-signal" /> : <X className="h-4 w-4 text-pale-frost" />}
                      <span className="text-pale-frost">{c.passed ? 'Verified' : 'Not verified'}</span>{c.description}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <h3 className="text-sm font-semibold text-pale-frost">Study plan</h3>
              <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm leading-6 text-muted-fog">
                {report.study_plan.map(s => <li key={s}>{s}</li>)}
              </ol>
            </section>

            <p className="border-t border-steel-outline pt-4 text-xs text-muted-fog">
              Fluency &amp; accent weight: {report.fluency_weight}%. Grammar, accent and vocal energy are not scored.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
