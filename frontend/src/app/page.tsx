import {
  ArrowRight,
  Bot,
  Brain,
  CheckCircle2,
  Code,
  Compass,
  Cpu,
  GitBranch,
  Image as ImageIcon,
  MessageSquare,
  Palette,
  Search,
  Sparkles,
  Users,
  Wind,
  Zap,
} from "lucide-react"

const agents = [
  { icon: Bot, label: "ChatGPT", role: "Synthesizer", color: "#10A37F" },
  { icon: Cpu, label: "Claude", role: "Analyst", color: "#D97706" },
  { icon: Sparkles, label: "Gemini", role: "Reasoner", color: "#4285F4" },
  { icon: CheckCircle2, label: "DeepSeek", role: "Verifier", color: "#2563EB" },
  { icon: GitBranch, label: "Llama", role: "Critic", color: "#8B5CF6" },
  { icon: Wind, label: "Mistral", role: "Strategist", color: "#F97316" },
  { icon: Search, label: "Qwen", role: "Researcher", color: "#059669" },
  { icon: Compass, label: "Grok", role: "Explorer", color: "#E11D48" },
  { icon: Brain, label: "Perplexity", role: "Searcher", color: "#14B8A6" },
  { icon: Code, label: "Copilot", role: "Assistant", color: "#10B981" },
  { icon: ImageIcon, label: "Midjourney", role: "Artist", color: "#EC4899" },
  { icon: MessageSquare, label: "Cohere", role: "Generator", color: "#6366F1" },
  { icon: Users, label: "Hugging Face", role: "Hub", color: "#FBBF24" },
  { icon: Palette, label: "DALL-E", role: "Creator", color: "#F43F5E" },
]

const steps = [
  { icon: Zap, title: "Ask", desc: "One question, a time budget, and your keys." },
  { icon: Users, title: "Team forms", desc: "A planner assembles diverse agents across model families." },
  { icon: GitBranch, title: "Debate", desc: "Agents reason independently, then cross-examine each other." },
  { icon: Sparkles, title: "Consensus", desc: "A verifier checks sources, a critic stress-tests claims." },
]

export default function LandingPage() {
  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-background text-foreground">
      {/* Ambient background */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="animate-aurora absolute -top-40 left-1/2 h-[600px] w-[900px] -translate-x-1/2 rounded-full bg-brand/20 blur-[140px]" />
        <div className="animate-float-slow absolute top-1/3 -left-40 h-96 w-96 rounded-full bg-info/10 blur-[120px]" />
        <div className="animate-float-slower absolute -right-40 bottom-0 h-96 w-96 rounded-full bg-brand/10 blur-[120px]" />
        <div
          className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
          style={{
            backgroundImage:
              "linear-gradient(var(--foreground) 1px, transparent 1px), linear-gradient(90deg, var(--foreground) 1px, transparent 1px)",
            backgroundSize: "64px 64px",
          }}
        />
      </div>

      {/* Nav */}
      <header className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-brand-foreground shadow-lg shadow-brand/30">
            <Zap className="size-5" />
          </div>
          <span className="text-lg font-bold tracking-tight">Assembly</span>
        </div>
        <a
          href="/chat"
          className="group inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition-all hover:border-brand hover:text-brand hover:shadow-lg hover:shadow-brand/10"
        >
          Launch App
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
        </a>
      </header>

      {/* Hero */}
      <main className="relative z-10 mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-12 lg:py-20">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-12 lg:gap-8">
          <div className="flex flex-1 flex-col items-start text-left">
            <div className="animate-fade-up inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand-subtle px-4 py-1.5 text-xs font-medium text-brand">
              <Sparkles className="size-3.5" />
              Multi-agent AI research
            </div>

            <h1 className="animate-fade-up mt-8 max-w-2xl text-5xl font-bold leading-[1.1] tracking-tight sm:text-7xl" style={{ animationDelay: "0.1s" }}>
              One question.
              <br />
              <span className="bg-gradient-to-r from-brand via-[#e8a020] to-[#c8860a] bg-clip-text text-transparent">
                A team of minds.
              </span>
            </h1>

            <p className="animate-fade-up mt-6 max-w-xl text-lg text-muted-foreground sm:text-xl" style={{ animationDelay: "0.2s" }}>
              Assembly forms a temporary team of AI agents that reason independently, cross-examine, verify with live sources, and synthesise a single high-confidence answer.
            </p>

            <div className="animate-fade-up mt-10 flex flex-col items-start gap-4 sm:flex-row sm:items-center" style={{ animationDelay: "0.3s" }}>
              <a
                href="/chat"
                className="group inline-flex h-12 items-center gap-2 rounded-xl bg-brand px-8 text-base font-semibold text-brand-foreground shadow-xl shadow-brand/30 transition-all hover:bg-brand-hover hover:shadow-2xl hover:shadow-brand/40 hover:-translate-y-0.5"
              >
                <Zap className="size-5" />
                Start Researching
                <ArrowRight className="size-5 transition-transform group-hover:translate-x-1" />
              </a>
              <a
                href="/setup"
                className="inline-flex h-12 items-center gap-2 rounded-xl border border-border bg-card px-8 text-base font-semibold text-foreground transition-all hover:border-brand/50 hover:text-brand hover:-translate-y-0.5"
              >
                Configure Keys
              </a>
            </div>
          </div>

          {/* Agent orbit visual */}
          <div className="animate-fade-up relative flex flex-shrink-0 items-center justify-center py-8 lg:py-0" style={{ animationDelay: "0.4s" }}>
            <div className="relative flex h-72 w-72 items-center justify-center sm:h-80 sm:w-80">
              {/* Orbit rings */}
              <div className="animate-spin-slower absolute inset-0 rounded-full border border-border/50" />
              <div className="animate-spin-reverse absolute inset-8 rounded-full border border-border/30" />
              <div className="animate-spin-slow absolute inset-16 rounded-full border border-border/20" />

              {/* Center */}
              <div className="animate-pulse-glow relative z-10 flex h-24 w-24 items-center justify-center rounded-3xl bg-brand text-brand-foreground shadow-2xl shadow-brand/40">
                <Zap className="size-10" />
              </div>

              {/* Agent nodes */}
              {agents.map((agent, i) => {
                const Icon = agent.icon
                const angle = i * (360 / agents.length)
                const delay = `-${((i * 16) / agents.length).toFixed(2)}s`
                return (
                  <div
                    key={agent.label}
                    className="animate-orbit absolute"
                    style={{ animationDelay: delay, transform: `rotate(${angle}deg)` }}
                  >
                    <div
                      className="animate-counter-orbit flex h-14 w-14 sm:h-16 sm:w-16 flex-col items-center justify-center gap-0.5 rounded-2xl border bg-card shadow-lg transition-all hover:scale-110 hover:shadow-xl"
                      style={{ borderColor: agent.color + "40", animationDelay: delay }}
                    >
                      <Icon className="size-4 sm:size-5" style={{ color: agent.color }} />
                      <span className="text-[9px] sm:text-[10px] font-semibold text-muted-foreground">{agent.label}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* How it works */}
        <div className="animate-fade-up mt-28 w-full" style={{ animationDelay: "0.5s" }}>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">How it works</h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map((step, i) => {
              const Icon = step.icon
              return (
                <div
                  key={step.title}
                  className="group relative rounded-2xl border border-border bg-card p-6 text-left transition-all hover:-translate-y-1 hover:border-brand/40 hover:shadow-xl hover:shadow-brand/5"
                >
                  <div className="absolute right-4 top-4 font-mono text-xs text-muted-foreground/50">
                    0{i + 1}
                  </div>
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-subtle text-brand transition-all group-hover:scale-110 group-hover:bg-brand group-hover:text-brand-foreground">
                    <Icon className="size-5" />
                  </div>
                  <h3 className="mt-4 text-lg font-semibold">{step.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{step.desc}</p>
                </div>
              )
            })}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border/50 py-6 text-center">
        <p className="text-xs text-muted-foreground">
          Assembly &middot; Temporary teams of AI agents that produce measurably better answers
        </p>
      </footer>
    </div>
  )
}
