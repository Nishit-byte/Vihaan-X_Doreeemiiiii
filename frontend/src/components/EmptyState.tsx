import { Code2, FileText } from 'lucide-react'

interface Props { busy: boolean; onDemoRepo: () => void; onDemoPaper: () => void }

const LADDER = [
  { level: 'L1', name: 'Recall', ask: 'What does this do?' },
  { level: 'L2', name: 'Comprehension', ask: 'Why was it done this way?' },
  { level: 'L3', name: 'Analysis', ask: 'What are the trade-offs against the alternative?' },
  { level: 'L4', name: 'Evaluation', ask: 'What breaks if it changes? Then fix it live in the editor.' },
]

const outlineBtn =
  'rounded-md px-2.5 py-1.5 text-sm font-medium text-pale-frost ring-1 ring-inset ring-blue-steel hover:bg-deep-slate disabled:cursor-not-allowed disabled:opacity-40'

export default function EmptyState({ busy, onDemoRepo, onDemoPaper }: Props) {
  return (
    <div className="h-full overflow-auto">
      <div className="mx-auto max-w-3xl space-y-6 p-6">
        <div>
          <h1 className="text-lg font-medium text-pale-frost">Start a viva</h1>
          <p className="mt-1 text-sm text-muted-fog">
            Choose an input from the top bar. The examiner then asks spoken questions tied to your code
            or paper, and you answer by voice or text.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <article className="panel p-3">
            <div className="flex items-center gap-2 text-base font-medium text-pale-frost">
              <Code2 className="h-5 w-5 text-nuxt-signal" strokeWidth={1.5} aria-hidden />Repository viva
            </div>
            <p className="mt-2 text-sm leading-6 text-muted-fog">
              Paste a GitHub URL in the top bar and press Start viva. Questions cite exact lines in the
              editor. Pick an author to examine one contributor’s code.
            </p>
            <button onClick={onDemoRepo} disabled={busy} className={`mt-3 ${outlineBtn}`}>Load cached demo repo</button>
          </article>
          <article className="panel p-3">
            <div className="flex items-center gap-2 text-base font-medium text-pale-frost">
              <FileText className="h-5 w-5 text-nuxt-signal" strokeWidth={1.5} aria-hidden />Research paper viva
            </div>
            <p className="mt-2 text-sm leading-6 text-muted-fog">
              Upload a PDF from the top bar. Questions point at stages of an architecture diagram built
              from the paper, with the matching excerpt beside it.
            </p>
            <button onClick={onDemoPaper} disabled={busy} className={`mt-3 ${outlineBtn}`}>Load cached demo paper</button>
          </article>
        </div>

        <section aria-label="Question depth ladder">
          <h2 className="text-sm font-semibold text-pale-frost">How questions escalate</h2>
          <p className="mt-1 text-sm text-muted-fog">Strong answers move you up a level. At L4 the editor also serves a coding or DSA challenge that is verified by running tests.</p>
          <ul className="panel mt-3 divide-y divide-steel-outline">
            {LADDER.map(r => (
              <li key={r.level} className="flex items-baseline gap-3 px-3 py-2">
                <span className="w-7 font-mono text-sm text-nuxt-signal">{r.level}</span>
                <span className="w-32 shrink-0 text-sm font-medium text-pale-frost">{r.name}</span>
                <span className="text-sm text-muted-fog">{r.ask}</span>
              </li>
            ))}
          </ul>
        </section>

        <p className="text-xs text-muted-fog">Grading ignores grammar, accent and vocal energy: fluency weight is 0%.</p>
      </div>
    </div>
  )
}
