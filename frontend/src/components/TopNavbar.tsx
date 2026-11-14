import { useRef, useState } from 'react'
import { AudioLines, FileUp, GitBranch, Home } from 'lucide-react'
import type { VivaMode } from '../types/api'

interface Props {
  mode: VivaMode | null
  hasSession: boolean
  busy: boolean
  demo: boolean
  authors: string[]
  author: string | null
  onAuthorChange: (a: string | null) => void
  onStartRepo: (url: string) => void
  onUploadPdf: (file: File) => void
  onFinish: () => void
  onHome: () => void
}

const outlineBtn =
  'inline-flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm font-medium text-pale-frost ring-1 ring-inset ring-blue-steel hover:bg-deep-slate disabled:cursor-not-allowed disabled:opacity-40'

export default function TopNavbar(p: Props) {
  const [url, setUrl] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const canStart = url.trim().length > 0 && !p.busy

  const submit = () => { if (canStart) p.onStartRepo(url.trim()) }

  return (
    <header className="h-16 shrink-0 border-b border-steel-outline bg-void-canvas/90 backdrop-blur-sm">
      <div className="mx-auto flex h-full max-w-[1440px] items-center gap-4 px-4">
        <button className={outlineBtn} onClick={p.onHome} disabled={!p.hasSession} aria-label="Home: back to main screen">
          <Home className="h-4 w-4" aria-hidden /> Home
        </button>

        <div className="flex items-center gap-2">
          <AudioLines className="h-6 w-6 text-nuxt-signal" aria-hidden />
          <span className="text-base font-semibold text-signal-white">VivaVoce</span>
        </div>

        {p.mode && (
          <span className="rounded-full px-2.5 py-1 text-xs font-semibold text-nuxt-signal ring-1 ring-inset ring-nuxt-signal/25">
            {p.mode === 'repo' ? 'Repo viva' : 'Paper viva'}
          </span>
        )}

        <div className="ml-auto flex min-w-0 items-center gap-2">
          <label className="flex w-80 min-w-0 items-center gap-2 rounded-md bg-void-canvas px-3 py-2 ring-1 ring-steel-outline focus-within:ring-blue-steel">
            <GitBranch className="h-4 w-4 shrink-0 text-muted-fog" aria-hidden />
            <input
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submit()}
              placeholder="https://github.com/owner/repo"
              aria-label="GitHub repository URL"
              className="min-w-0 flex-1 bg-transparent font-mono text-sm text-pale-frost placeholder:text-blue-steel focus:outline-none"
            />
          </label>

          {p.hasSession ? (
            <button className={outlineBtn} onClick={submit} disabled={!canStart}>Restart</button>
          ) : (
            <button
              onClick={submit}
              disabled={!canStart}
              className="rounded-md bg-nuxt-signal px-3 py-2 text-sm font-medium text-deep-slate hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {p.busy ? 'Loading…' : 'Start viva'}
            </button>
          )}

          <input
            ref={fileRef} type="file" accept="application/pdf" hidden
            onChange={e => { const f = e.target.files?.[0]; if (f) p.onUploadPdf(f); e.target.value = '' }}
          />
          <button className={outlineBtn} onClick={() => fileRef.current?.click()} disabled={p.busy}>
            <FileUp className="h-4 w-4" aria-hidden /> Upload PDF
          </button>
        </div>

        <div className="flex items-center gap-3 pl-2">
          {p.demo && (
            <span title="Backend unreachable: showing cached demo data"
              className="rounded-full px-2.5 py-1 text-xs font-semibold text-muted-fog ring-1 ring-inset ring-blue-steel">
              Demo data
            </span>
          )}
          <button
            onClick={p.onFinish}
            disabled={!p.hasSession || p.busy}
            className="rounded-md bg-signal-white px-3 py-2 text-sm font-medium text-deep-slate hover:bg-pale-frost disabled:cursor-not-allowed disabled:opacity-40"
          >
            Finish viva
          </button>
        </div>
      </div>
    </header>
  )
}
