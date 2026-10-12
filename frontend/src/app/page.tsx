import Link from "next/link";
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  Code,
  Compass,
  Cpu,
  GitBranch,
  MessageSquare,
  Search,
  Sparkles,
  Users,
  Zap,
} from "lucide-react"

const agents = [
  { icon: Sparkles, label: "Gemini", role: "Family", color: "#4285F4" },
  { icon: Code, label: "GPT-OSS", role: "Family", color: "#10B981" },
  { icon: Search, label: "Qwen", role: "Family", color: "#059669" },
  { icon: Cpu, label: "Gemma", role: "Family", color: "#D97706" },
  { icon: Brain, label: "Nemotron", role: "Family", color: "#14B8A6" },
  { icon: Zap, label: "Solver", role: "Role", color: "#E8A020" },
  { icon: GitBranch, label: "Critic", role: "Role", color: "#8B5CF6" },
  { icon: Compass, label: "Researcher", role: "Role", color: "#E11D48" },
  { icon: CheckCircle2, label: "Verifier", role: "Role", color: "#2563EB" },
  { icon: MessageSquare, label: "Synthesizer", role: "Role", color: "#6366F1" },
]

const steps = [
  { icon: Zap, title: "Ask once", desc: "Put the hard question in. Pick 3, 5, 10 or 15 minutes." },
  { icon: Users, title: "Get a team", desc: "Agents from 3 or more model families take it separately." },
  { icon: GitBranch, title: "Watch them argue", desc: "Each answer gets cross examined before it counts." },
  { icon: Sparkles, title: "Keep one answer", desc: "Sources numbered. Confidence stated. Doubt flagged." },
]

export default function LandingPage() {
  const base = "https://assembly-murex.vercel.app"
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: "Assembly",
      url: `${base}/`,
    },
    {
      "@context": "https://schema.org",
      "@type": "Organization",
      name: "Assembly",
      url: `${base}/`,
      founder: { "@type": "Person", name: "Anubhab Das" },
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Home", item: `${base}/` },
        { "@type": "ListItem", position: 2, name: "Ask", item: `${base}/chat` },
        { "@type": "ListItem", position: 3, name: "Setup", item: `${base}/settings` },
      ],
    },
    {
      "@context": "https://schema.org",
      "@type": "FAQPage",
      mainEntity: [
        {
          "@type": "Question",
          name: "Getting keys sounds like work. Is it?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "Ten minutes, once. Grab free keys from two providers, paste them in, done. No card, no account.",
          },
        },
        {
          "@type": "Question",
          name: "Why not just ask one good model?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "One model gives one confident guess. Assembly makes agents from different families argue first, so weak claims die before you read them.",
          },
        },
        {
          "@type": "Question",
          name: "Do my keys or questions leave my machine?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "Keys stay in your browser. Questions go to the model providers you chose, nothing is stored on our server.",
          },
        },
        {
          "@type": "Question",
          name: "Can I trust the final answer?",
          acceptedAnswer: {
            "@type": "Answer",
            text: "Trust it the way you trust a cited draft. Every answer lists numbered sources, a confidence level, and what stayed uncertain.",
          },
        },
      ],
    },
  ]
  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-background text-foreground">
      {jsonLd.map((schema, i) => (
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
      ))}
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
        <Link
          href="/chat"
          className="group inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground transition-all hover:border-brand hover:text-brand hover:shadow-lg hover:shadow-brand/10"
        >
          Run my first question
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </header>

      {/* Hero */}
      <main className="relative z-10 mx-auto flex w-full max-w-6xl flex-1 flex-col px-6 py-12 lg:py-20">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-12 lg:gap-8">
          <div className="flex flex-1 flex-col items-start text-left">
            <div className="animate-fade-up inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand-subtle px-4 py-1.5 text-xs font-medium text-brand">
              <Sparkles className="size-3.5" />
              For skeptics with API keys
            </div>

            <h1 className="animate-fade-up mt-8 max-w-2xl text-5xl font-bold leading-[1.1] tracking-tight sm:text-7xl" style={{ animationDelay: "0.1s" }}>
              Stop trusting one model with hard questions.
            </h1>

            <p className="animate-fade-up mt-6 max-w-xl text-lg text-muted-foreground sm:text-xl" style={{ animationDelay: "0.2s" }}>
              Assembly runs your question past agents from 3 or more model families. You keep one sourced answer in 3 to 15 minutes.
            </p>

            <div className="animate-fade-up mt-10 flex flex-col items-start gap-4 sm:flex-row sm:items-center" style={{ animationDelay: "0.3s" }}>
              <Link
                href="/chat"
                className="group inline-flex h-12 items-center gap-2 rounded-xl bg-brand px-8 text-base font-semibold text-brand-foreground shadow-xl shadow-brand/30 transition-all hover:bg-brand-hover hover:shadow-2xl hover:shadow-brand/40 hover:-translate-y-0.5"
              >
                <Zap className="size-5" />
                Run my first question
                <ArrowRight className="size-5 transition-transform group-hover:translate-x-1" />
              </Link>
              <Link
                href="/settings"
                className="inline-flex h-12 items-center gap-2 rounded-xl border border-border bg-card px-8 text-base font-semibold text-foreground transition-all hover:border-brand/50 hover:text-brand hover:-translate-y-0.5"
              >
                Add my free keys
              </Link>
            </div>
            <p className="animate-fade-up mt-4 text-sm text-muted-foreground" style={{ animationDelay: "0.35s" }}>
              No account. Keys stay in your browser. First progress in seconds.
            </p>
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
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">One answer you can check</h2>
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
        {/* FAQ (visible; matches FAQPage schema above) */}
        <section aria-labelledby="faq-heading" className="mt-24 w-full max-w-3xl">
          <h2 id="faq-heading" className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">Worried? Read this</h2>
          <div className="mt-6 space-y-4 text-left">
            <div className="rounded-2xl border border-border bg-card p-6">
              <h3 className="font-semibold">Getting keys sounds like work. Is it?</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">Ten minutes, once. Grab free keys from two providers, paste them in, done. No card, no account.</p>
            </div>
            <div className="rounded-2xl border border-border bg-card p-6">
              <h3 className="font-semibold">Why not just ask one good model?</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">One model gives one confident guess. Assembly makes agents from different families argue first, so weak claims die before you read them.</p>
            </div>
            <div className="rounded-2xl border border-border bg-card p-6">
              <h3 className="font-semibold">Do my keys or questions leave my machine?</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">Keys stay in your browser. Questions go to the model providers you chose, nothing is stored on our server. Note: some free tiers (for example Gemini) may reuse inputs for training.</p>
            </div>
            <div className="rounded-2xl border border-border bg-card p-6">
              <h3 className="font-semibold">Can I trust the final answer?</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">Trust it the way you trust a cited draft. Every answer lists numbered sources, a confidence level, and what stayed uncertain.</p>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border/50 py-6 text-center">
        <nav aria-label="Breadcrumb" className="mb-4 flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <Link href="/" className="hover:text-brand">Home</Link>
          <span aria-hidden>/</span>
          <Link href="/chat" className="hover:text-brand">Ask</Link>
          <span aria-hidden>/</span>
          <Link href="/settings" className="hover:text-brand">Setup</Link>
          <span aria-hidden>/</span>
          <Link href="/executions" className="hover:text-brand">History</Link>
        </nav>
        <div className="flex flex-col items-center justify-center gap-2 text-xs text-muted-foreground sm:flex-row sm:gap-3">
          <p>
            Assembly &middot; One question in, one cited answer out
          </p>
          <span className="hidden sm:inline" aria-hidden>&middot;</span>
          <p>
            Developed by{" "}
            <a
              href="https://anubhab-protfolio.vercel.app"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-foreground underline decoration-brand/50 underline-offset-4 transition-colors hover:text-brand hover:decoration-brand"
            >
              Anubhab Das
            </a>
          </p>
          <span className="hidden sm:inline" aria-hidden>&middot;</span>
          <p>
            <a
              href="mailto:anubhab7105@gmail.com"
              className="inline-flex min-h-11 items-center font-medium text-foreground underline decoration-brand/50 underline-offset-4 transition-colors hover:text-brand hover:decoration-brand"
            >
              anubhab7105@gmail.com
            </a>
          </p>
        </div>
      </footer>
    </div>
  )
}
