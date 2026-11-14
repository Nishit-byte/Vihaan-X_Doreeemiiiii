import { BookOpen, Code2, FileText, Mic } from 'lucide-react'

type Page = 'home' | 'project' | 'dsa' | 'research'

interface Props {
  onNavigate: (page: Page) => void
}

const CARDS = [
  {
    id: 'project' as Page,
    icon: <Code2 className="h-7 w-7" strokeWidth={1.5} />,
    label: 'Project Interview Prep',
    description:
      'Walk through your GitHub repository with a live AI examiner. Questions escalate from recall to live code challenges — just like a real project viva.',
    pastel: '#dbdfff',
    accent: '#4255ff',
    badge: 'Repo Viva',
  },
  {
    id: 'dsa' as Page,
    icon: <BookOpen className="h-7 w-7" strokeWidth={1.5} />,
    label: 'DSA / OA Prep',
    description:
      'Practice data structures, algorithms, and online assessment problems with a voice-driven examiner that grades your reasoning and solution step-by-step.',
    pastel: '#c9f0f8',
    accent: '#0891b2',
    badge: 'Coding Round',
  },
  {
    id: 'research' as Page,
    icon: <FileText className="h-7 w-7" strokeWidth={1.5} />,
    label: 'Research Paper Prep',
    description:
      'Upload a PDF and get interviewed on your paper\'s methodology, results, and trade-offs. The examiner maps your architecture and digs into every section.',
    pastel: '#ffd6e7',
    accent: '#db2777',
    badge: 'Paper Viva',
  },
]

export default function HomePage({ onNavigate }: Props) {
  return (
    <div
      className="flex min-h-full flex-col"
      style={{ background: 'var(--color-chalk-canvas)' }}
    >
      {/* ── Top Nav ──────────────────────────────────────────────────────── */}
      <header
        style={{
          background: 'var(--color-paper-white)',
          boxShadow: 'var(--shadow-nav)',
          position: 'sticky',
          top: 0,
          zIndex: 50,
        }}
      >
        <div
          style={{
            maxWidth: 1200,
            margin: '0 auto',
            padding: '0 24px',
            height: 56,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Mic
              className="h-5 w-5"
              style={{ color: 'var(--color-iris-bolt)' }}
              strokeWidth={2}
            />
            <span
              style={{
                fontWeight: 700,
                fontSize: 18,
                color: 'var(--color-iris-bolt)',
                letterSpacing: '-0.3px',
              }}
            >
              VivaVoce
            </span>
          </div>
          <span
            style={{
              marginLeft: 'auto',
              fontSize: 13,
              color: 'var(--color-slate-veil)',
            }}
          >
            AI-powered interview examiner
          </span>
        </div>
      </header>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section
        style={{
          textAlign: 'center',
          padding: '80px 24px 48px',
          maxWidth: 760,
          margin: '0 auto',
        }}
      >
        <span
          style={{
            display: 'inline-block',
            background: 'var(--color-lilac-wash)',
            color: 'var(--color-iris-bolt)',
            fontWeight: 600,
            fontSize: 13,
            padding: '5px 16px',
            borderRadius: 200,
            marginBottom: 20,
            letterSpacing: 0.3,
          }}
        >
          Powered by VivaVoce
        </span>
        <h1
          style={{
            fontSize: 44,
            fontWeight: 700,
            lineHeight: '55px',
            color: 'var(--color-ink-charcoal)',
            margin: '0 0 20px',
          }}
        >
          Your AI-Powered{' '}
          <span style={{ color: 'var(--color-iris-bolt)' }}>Viva Examiner</span>
        </h1>
        <p
          style={{
            fontSize: 18,
            lineHeight: '28px',
            color: 'var(--color-slate-veil)',
            margin: '0 auto 32px',
            maxWidth: 560,
          }}
        >
          Choose your preparation mode below. The examiner asks spoken questions
          at escalating depth — answer by voice or text, get real-time feedback.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, flexWrap: 'wrap' }}>
          {(['L1 Recall', 'L2 Comprehend', 'L3 Analyze', 'L4 Evaluate'] as const).map(l => (
            <span
              key={l}
              style={{
                background: 'var(--color-paper-white)',
                border: '1px solid var(--color-mist-border)',
                borderRadius: 4,
                padding: '4px 12px',
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--color-slate-veil)',
              }}
            >
              {l}
            </span>
          ))}
          <span style={{ fontSize: 12, color: 'var(--color-fog-mist)', marginLeft: 4 }}>
            — escalating question depth
          </span>
        </div>
      </section>

      {/* ── 3-Card Grid ──────────────────────────────────────────────────── */}
      <section
        style={{
          maxWidth: 1100,
          margin: '0 auto',
          padding: '0 24px 80px',
          width: '100%',
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: 24,
          }}
        >
          {CARDS.map(card => (
            <button
              key={card.id}
              onClick={() => onNavigate(card.id)}
              style={{
                all: 'unset',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                borderRadius: 24,
                overflow: 'hidden',
                boxShadow: 'var(--shadow-card)',
                background: 'var(--color-paper-white)',
                border: '1px solid var(--color-mist-border)',
                transition: 'transform 0.18s, box-shadow 0.18s',
                textAlign: 'left',
              }}
              onMouseEnter={e => {
                ;(e.currentTarget as HTMLElement).style.transform =
                  'translateY(-4px)'
                ;(e.currentTarget as HTMLElement).style.boxShadow =
                  'rgba(40,46,62,0.15) 0px 8px 32px 0px'
              }}
              onMouseLeave={e => {
                ;(e.currentTarget as HTMLElement).style.transform = 'none'
                ;(e.currentTarget as HTMLElement).style.boxShadow =
                  'var(--shadow-card)'
              }}
            >
              {/* Pastel header area */}
              <div
                style={{
                  background: card.pastel,
                  padding: '32px 28px 24px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                }}
              >
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 52,
                    height: 52,
                    borderRadius: 14,
                    background: 'rgba(255,255,255,0.7)',
                    color: card.accent,
                  }}
                >
                  {card.icon}
                </span>
                <span
                  style={{
                    display: 'inline-block',
                    background: 'rgba(255,255,255,0.75)',
                    color: card.accent,
                    fontSize: 11,
                    fontWeight: 700,
                    padding: '3px 10px',
                    borderRadius: 200,
                    letterSpacing: 0.5,
                    textTransform: 'uppercase',
                    width: 'fit-content',
                  }}
                >
                  {card.badge}
                </span>
                <h2
                  style={{
                    margin: 0,
                    fontSize: 22,
                    fontWeight: 700,
                    lineHeight: '30px',
                    color: 'var(--color-ink-charcoal)',
                  }}
                >
                  {card.label}
                </h2>
              </div>

              {/* White body */}
              <div
                style={{
                  padding: '20px 28px 28px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 20,
                  flex: 1,
                }}
              >
                <p
                  style={{
                    margin: 0,
                    fontSize: 15,
                    lineHeight: '24px',
                    color: 'var(--color-slate-veil)',
                    flex: 1,
                  }}
                >
                  {card.description}
                </p>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    background: card.accent,
                    color: '#fff',
                    fontWeight: 600,
                    fontSize: 14,
                    padding: '10px 22px',
                    borderRadius: 200,
                    boxShadow: 'var(--shadow-btn)',
                    width: 'fit-content',
                  }}
                >
                  Start prep →
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer
        style={{
          borderTop: '1px solid var(--color-mist-border)',
          padding: '24px',
          textAlign: 'center',
          fontSize: 13,
          color: 'var(--color-fog-mist)',
          background: 'var(--color-paper-white)',
        }}
      >
        VivaVoce — AI Interview Examiner &nbsp;·&nbsp; Grading ignores grammar,
        accent & vocal energy: fluency weight is 0%.
      </footer>
    </div>
  )
}
