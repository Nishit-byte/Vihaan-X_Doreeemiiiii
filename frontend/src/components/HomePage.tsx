import { ChevronDown, ChevronLeft, ChevronRight, Plus, Search } from 'lucide-react'

type Page = 'home' | 'project' | 'dsa' | 'research'

interface Props {
  onNavigate: (page: Page) => void
}

export default function HomePage({ onNavigate }: Props) {
  return (
    <div className="flex min-h-full flex-col bg-[#f6f7fb] text-[#282e3e]">
      {/* ── Top Navigation Bar (Quizlet style) ───────────────────────────── */}
      <header className="sticky top-0 z-30 h-[64px] w-full bg-[#ffffff] shadow-[rgba(40,46,62,0.08)_0px_2px_12px_0px]">
        <div className="mx-auto flex h-full max-w-[1280px] items-center gap-6 px-6">
          <div className="flex items-center gap-6 shrink-0">
            <span className="text-[22px] font-bold tracking-tight text-[#4255ff]">
              VivaVoce
            </span>

            <nav aria-label="Primary" className="hidden md:flex items-center gap-5">
              <button
                type="button"
                onClick={() => onNavigate('project')}
                className="flex items-center gap-1 text-[14px] font-semibold text-[#282e3e] hover:text-[#4255ff] cursor-pointer"
              >
                Study tools <ChevronDown className="h-3.5 w-3.5 text-[#586380]" />
              </button>
              <button
                type="button"
                onClick={() => onNavigate('dsa')}
                className="flex items-center gap-1 text-[14px] font-semibold text-[#282e3e] hover:text-[#4255ff] cursor-pointer"
              >
                Subjects <ChevronDown className="h-3.5 w-3.5 text-[#586380]" />
              </button>
            </nav>
          </div>

          {/* Centered Pill Search Bar */}
          <div className="mx-auto hidden sm:flex max-w-[460px] flex-1 items-center gap-2.5 rounded-[200px] bg-[#f6f7fb] px-4 py-2">
            <Search className="h-4 w-4 shrink-0 text-[#586380]" aria-hidden />
            <input
              type="text"
              placeholder="Search repos, DSA topics, or papers"
              aria-label="Search repos, DSA topics, or papers"
              onKeyDown={e => {
                if (e.key === 'Enter') onNavigate('project')
              }}
              className="min-w-0 flex-1 bg-transparent text-[14px] font-normal text-[#282e3e] placeholder:text-[#939bb4] focus:outline-none"
            />
          </div>

          {/* Empty Create & Log in buttons (no-op by design) */}
          <div className="ml-auto flex items-center gap-3 shrink-0">
            <button
              type="button"
              onClick={() => {}}
              className="inline-flex items-center gap-1.5 rounded-[200px] px-3 py-2 text-[14px] font-semibold text-[#4255ff] hover:bg-[#edefff] cursor-pointer"
            >
              <Plus className="h-4 w-4" /> Create
            </button>
            <button
              type="button"
              onClick={() => {}}
              className="rounded-[200px] bg-[#4255ff] px-5 py-2 text-[14px] font-semibold text-[#ffffff] shadow-[rgba(40,46,62,0.1)_0px_2px_4px_0px] hover:brightness-95 cursor-pointer"
            >
              Log in
            </button>
          </div>
        </div>
      </header>

      {/* ── Main Hero + 4 Illustrated Mode Cards ─────────────────────────── */}
      <main className="mx-auto flex w-full max-w-[1280px] flex-1 flex-col items-center justify-center px-6 pt-12 pb-16">
        {/* Hero Stack */}
        <div className="mx-auto max-w-[680px] text-center">
          <h1 className="text-[44px] sm:text-[52px] font-bold leading-[1.15] tracking-[-0.02em] text-[#1a1d28]">
            VivaVoce
          </h1>
          <p className="mt-4 text-[17px] font-normal leading-[1.5] text-[#586380]">
            Master your codebase, DSA patterns, and research papers with an
            adaptive spoken examiner and live code verification.
          </p>
          <div className="mt-6 flex flex-col items-center gap-3">
            <button
              type="button"
              onClick={() => onNavigate('project')}
              className="rounded-[200px] bg-[#4255ff] px-7 py-3 text-[15px] font-semibold text-[#ffffff] shadow-[rgba(40,46,62,0.12)_0px_2px_6px_0px] hover:brightness-95 cursor-pointer"
            >
              Sign up for free
            </button>
            <button
              type="button"
              onClick={() => onNavigate('dsa')}
              className="text-[14px] font-semibold text-[#4255ff] hover:underline cursor-pointer"
            >
              Try coding practice
            </button>
          </div>
        </div>

        {/* 4-Card Carousel Row */}
        <div className="relative mt-12 w-full">
          {/* Decorative Left / Right Carousel Arrows */}
          <button
            type="button"
            aria-label="Previous mode"
            onClick={() => onNavigate('project')}
            className="hidden lg:flex absolute -left-5 top-1/2 z-10 h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-[#d9dde8] bg-[#ffffff] text-[#282e3e] shadow-[rgba(40,46,62,0.1)_0px_4px_12px_0px] hover:bg-[#f6f7fb] cursor-pointer"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <button
            type="button"
            aria-label="Next mode"
            onClick={() => onNavigate('research')}
            className="hidden lg:flex absolute -right-5 top-1/2 z-10 h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-[#d9dde8] bg-[#ffffff] text-[#282e3e] shadow-[rgba(40,46,62,0.1)_0px_4px_12px_0px] hover:bg-[#f6f7fb] cursor-pointer"
          >
            <ChevronRight className="h-5 w-5" />
          </button>

          <div className="mx-auto grid max-w-[1040px] grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {/* ── Card 1: Practice Interview (Cyan) ──────────────────────── */}
            <button
              type="button"
              onClick={() => onNavigate('project')}
              className="group flex h-[340px] flex-col overflow-hidden rounded-[24px] bg-[#9be4f8] pt-6 pl-6 text-left transition-transform duration-150 hover:-translate-y-1 cursor-pointer"
            >
              <h2 className="pr-6 text-center text-[20px] font-bold text-[#1a1d28]">
                Practice Interview
              </h2>
              <div className="mt-5 flex flex-1 flex-col justify-between rounded-tl-[16px] bg-[#ffffff] p-5 shadow-[rgba(40,46,62,0.08)_0px_4px_16px_0px]">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="rounded-[4px] bg-[#edefff] px-2 py-0.5 font-mono text-[11px] font-semibold text-[#4255ff]">
                      scorer.py:6-18
                    </span>
                    <span className="text-[11px] font-semibold text-[#586380]">L2 Why</span>
                  </div>
                  <p className="font-mono text-[12px] leading-5 text-[#282e3e]">
                    def cosine_rerank(q, d):
                    <br />
                    <span className="bg-[#edefff] px-1 text-[#4255ff]">
                      return dot / (norm_q * norm_d)
                    </span>
                  </p>
                </div>
                <div className="rounded-[8px] border border-[#d9dde8] bg-[#f6f7fb] px-3 py-2 text-[12px] text-[#939bb4]">
                  Hold Space or type answer...
                </div>
              </div>
            </button>

            {/* ── Card 2: Study a Paper (Magenta/Lavender) ───────────────── */}
            <button
              type="button"
              onClick={() => onNavigate('research')}
              className="group flex h-[340px] flex-col overflow-hidden rounded-[24px] bg-[#eab4ff] pt-6 pl-6 text-left transition-transform duration-150 hover:-translate-y-1 cursor-pointer"
            >
              <h2 className="pr-6 text-center text-[20px] font-bold text-[#1a1d28]">
                Study a Paper
              </h2>
              <div className="mt-5 flex flex-1 flex-col rounded-tl-[16px] bg-[#ffffff] p-5 shadow-[rgba(40,46,62,0.08)_0px_4px_16px_0px]">
                <div className="text-[17px] font-bold text-[#1a1d28]">GraphCodeBERT</div>
                <div className="mt-1 flex items-center gap-3 border-b border-[#d9dde8] pb-2 text-[11px] font-semibold">
                  <span className="text-[#586380]">Outline</span>
                  <span className="border-b-2 border-[#4255ff] pb-0.5 text-[#1a1d28]">
                    Concept Map
                  </span>
                </div>
                <div className="mt-3 space-y-2 text-[11px]">
                  <div className="grid grid-cols-3 gap-2 border-b border-[#f0f2f7] pb-1.5">
                    <span className="font-semibold text-[#4255ff]">N1</span>
                    <span className="col-span-2 text-[#586380]">AST Data-Flow Graph</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 border-b border-[#f0f2f7] pb-1.5">
                    <span className="font-semibold text-[#4255ff]">N2</span>
                    <span className="col-span-2 text-[#586380]">Contrastive Alignment</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <span className="font-semibold text-[#4255ff]">N3</span>
                    <span className="col-span-2 text-[#586380]">Pass@k Verification</span>
                  </div>
                </div>
              </div>
            </button>

            {/* ── Card 3: Coding Practice (Deep Brand Violet) ────────────── */}
            <button
              type="button"
              onClick={() => onNavigate('dsa')}
              className="group flex h-[340px] flex-col overflow-hidden rounded-[24px] bg-[#423ed8] pt-6 px-6 text-left transition-transform duration-150 hover:-translate-y-1 cursor-pointer"
            >
              <h2 className="text-center text-[20px] font-bold text-[#ffffff]">
                Coding Practice
              </h2>
              <div className="relative mt-8 flex flex-1 items-center justify-center">
                {/* Back card */}
                <div className="absolute bottom-6 h-[155px] w-[88%] rounded-[14px] bg-[#ffffff]/25" />
                {/* Tilted front flashcard */}
                <div className="relative flex h-[165px] w-full -rotate-2 flex-col justify-between rounded-[14px] bg-[#ffffff] p-5 shadow-[rgba(20,24,40,0.22)_0px_8px_24px_0px] transition-transform duration-150 group-hover:rotate-0">
                  <div className="flex items-center justify-between">
                    <span className="rounded-[200px] bg-[#edefff] px-2.5 py-0.5 text-[11px] font-semibold text-[#4255ff]">
                      LeetCode Sync
                    </span>
                    <span className="font-mono text-[11px] font-semibold text-[#586380]">
                      O(n)
                    </span>
                  </div>
                  <div className="text-center">
                    <div className="text-[18px] font-bold text-[#1a1d28]">Two Sum</div>
                    <div className="mt-1 text-[12px] text-[#586380]">
                      Hash Map Complement Lookup
                    </div>
                  </div>
                  <div className="text-center text-[11px] font-semibold text-[#4255ff]">
                    Adaptive next problem →
                  </div>
                </div>
              </div>
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
