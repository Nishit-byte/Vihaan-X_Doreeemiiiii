import { useEffect } from 'react'
import { Check, Minus, X } from 'lucide-react'
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer } from 'recharts'
import type { VivaReport } from '../types/api'

interface Props {
  report: VivaReport | null
  loading: boolean
  error: string | null
  onClose: () => void
}

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
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-auto p-6"
      style={{ background: 'rgba(40, 46, 62, 0.4)', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Viva report"
        className="w-full max-w-3xl rounded-2xl border border-mist-border bg-paper-white p-8 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-mist-border pb-4">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-iris-bolt">Examination Evaluation</span>
            <h2 className="text-2xl font-bold text-ink-charcoal">Viva Performance Report</h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close report"
            className="rounded-full p-2 text-slate-veil hover:bg-chalk-canvas hover:text-ink-charcoal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {loading && <p className="mt-8 text-center text-sm text-slate-veil">Grading your examination against rubric…</p>}
        {error && <p className="mt-8 text-center text-sm text-red-600">Could not load report: {error}</p>}

        {report && (
          <div className="mt-6 space-y-8">
            {/* Score header */}
            <div className="flex items-center gap-6 rounded-xl bg-lilac-wash p-6">
              <div className="flex items-baseline gap-2">
                <span className="text-5xl font-extrabold text-iris-bolt">{Math.round(report.overall_score)}</span>
                <span className="text-lg font-semibold text-slate-veil">/100</span>
              </div>
              <div className="border-l border-mist-border pl-6">
                <div className="text-base font-bold text-ink-charcoal">Overall Assessment</div>
                <div className="text-sm text-slate-veil">
                  {report.overall_score >= 80
                    ? 'Excellent performance demonstrating deep structural understanding.'
                    : report.overall_score >= 60
                    ? 'Solid comprehension with opportunities to strengthen trade-off analysis.'
                    : 'Fundamental concepts identified; further preparation recommended.'}
                </div>
              </div>
            </div>

            {/* Rubric */}
            <section>
              <h3 className="text-base font-bold text-ink-charcoal">Competency Rubric</h3>
              <ul className="mt-4 space-y-4">
                {RUBRIC.map(r => (
                  <li key={r.key}>
                    <div className="flex justify-between text-sm">
                      <span className="font-semibold text-ink-charcoal">
                        {r.label} <span className="font-normal text-slate-veil">({r.weight}%)</span>
                      </span>
                      <span className="font-mono font-bold text-iris-bolt">{Math.round(report.rubric[r.key])}%</span>
                    </div>
                    <div
                      className="mt-1.5 h-2.5 w-full rounded-full bg-chalk-canvas"
                      role="progressbar"
                      aria-valuenow={report.rubric[r.key]}
                      aria-valuemin={0}
                      aria-valuemax={100}
                    >
                      <div
                        className="h-2.5 rounded-full bg-iris-bolt"
                        style={{ width: `${Math.max(0, Math.min(100, report.rubric[r.key]))}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </section>

            {/* Topic depth radar */}
            <section>
              <h3 className="text-base font-bold text-ink-charcoal">Topic Depth (L1 Recall to L4 Evaluate)</h3>
              <div className="mt-2 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={report.topic_depth} outerRadius="75%">
                    <PolarGrid stroke="#d9dde8" />
                    <PolarAngleAxis dataKey="topic" tick={{ fill: '#282e3e', fontSize: 12, fontWeight: 600 }} />
                    <PolarRadiusAxis domain={[0, 4]} tickCount={5} tick={{ fill: '#586380', fontSize: 10 }} axisLine={false} />
                    <Radar dataKey="level" stroke="#4255ff" fill="#4255ff" fillOpacity={0.25} isAnimationActive={false} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* Code challenges */}
            <section>
              <h3 className="text-base font-bold text-ink-charcoal">Coding Challenges</h3>
              {report.challenges.length === 0 ? (
                <p className="mt-2 flex items-center gap-2 text-sm text-slate-veil">
                  <Minus className="h-4 w-4" /> No coding challenges served in this session.
                </p>
              ) : (
                <ul className="mt-3 space-y-2">
                  {report.challenges.map(c => (
                    <li
                      key={c.description}
                      className="flex items-center gap-3 rounded-lg border border-mist-border bg-chalk-canvas p-3 text-sm text-ink-charcoal"
                    >
                      {c.passed ? (
                        <span className="flex items-center gap-1 rounded bg-green-100 px-2 py-0.5 text-xs font-bold text-green-700">
                          <Check className="h-3.5 w-3.5" /> Passed
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-700">
                          Pending
                        </span>
                      )}
                      <span>{c.description}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Study Plan */}
            <section>
              <h3 className="text-base font-bold text-ink-charcoal">Recommended Study Plan</h3>
              <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-slate-veil">
                {report.study_plan.map(s => (
                  <li key={s} className="pl-1">
                    {s}
                  </li>
                ))}
              </ol>
            </section>

            <p className="border-t border-mist-border pt-4 text-xs text-fog-mist">
              Fluency &amp; accent weight: {report.fluency_weight}%. Grammatical quirks and accents are not penalized.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
