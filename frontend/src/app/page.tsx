"use client"

import Link from "next/link"
import { useEffect, useRef } from "react"
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  GitBranch,
  Play,
  Search,
  ShieldCheck,
  Users,
} from "lucide-react"
import { BrandMark } from "@/components/cinematic/brand-mark"
import { FloatingWindows } from "@/components/cinematic/floating-windows"
import { ThemeToggle } from "@/components/theme-toggle"

const DOCS_URL = "https://github.com/arkap1502/Assembly#readme"

const steps = [
  {
    number: "01",
    title: "Independent perspectives",
    description:
      "Different model families take the same question separately, before they can see one another's conclusions.",
    icon: Users,
  },
  {
    number: "02",
    title: "Cross-examination",
    description:
      "A critic from another family attacks the weak points and names the contradictions worth resolving.",
    icon: GitBranch,
  },
  {
    number: "03",
    title: "Evidence, not vibes",
    description:
      "A researcher checks claims against sources. Disagreement runs another round only when it still matters.",
    icon: Search,
  },
  {
    number: "04",
    title: "One inspectable answer",
    description:
      "The synthesis carries its sources, confidence, and the uncertainties that remain. You decide what to trust.",
    icon: ShieldCheck,
  },
]

const faqs = [
  {
    question: "Why use more than one model?",
    answer:
      "A single model can miss a counterargument or sound certain about a weak claim. Assembly gives different model families independent passes, then uses cross-examination and evidence review before synthesizing an answer.",
  },
  {
    question: "Do I need an account or a subscription?",
    answer:
      "No account is required. Assembly is BYOK: you add your own provider keys and use the providers' available free tiers and quotas.",
  },
  {
    question: "Where are my keys and history stored?",
    answer:
      "In web mode, saved keys and history stay in your browser. Your question is sent only to the providers you choose for a run. The backend never writes keys to disk, a database, or a log.",
  },
  {
    question: "Can I control how long an investigation runs?",
    answer:
      "Yes. Choose a 3, 5, 10, or 15 minute budget before you start. The budget is a hard cutoff that shapes how many rounds the team can run.",
  },
]

const schema = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Assembly",
  url: "https://assembly-murex.vercel.app/",
  description: "Multi-model research that turns one hard question into one sourced, inspectable answer.",
}

export default function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null)
  const heroRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const nodes = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"))
    if (!nodes.length) return
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      nodes.forEach((node) => node.classList.add("is-visible"))
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible")
            observer.unobserve(entry.target)
          }
        }
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 },
    )
    nodes.forEach((node) => observer.observe(node))
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={rootRef} className="cin-landing">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />

      <header className="cin-topbar is-transparent cin-landing-top">
        <Link href="/" className="cin-brand" aria-label="Assembly home">
          <BrandMark />
          <span className="cin-brand-word">Assembly</span>
        </Link>

        <nav className="cin-landing-nav" aria-label="Main navigation">
          <a href="#product">Product</a>
          <a href="#how">How it works</a>
          <a href={DOCS_URL} target="_blank" rel="noreferrer">
            Docs
          </a>
          <a href={DOCS_URL} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </nav>

        <div className="cin-topbar-actions">
          <ThemeToggle className="cin-icon-button cin-landing-theme" />
          <Link href="/chat" className="cin-btn cin-btn-sm cin-btn-primary" aria-label="Launch the Assembly app">
            Launch app
            <ArrowUpRight className="size-4" aria-hidden />
          </Link>
        </div>
      </header>

      <main id="main-content" tabIndex={-1}>
        <section
          ref={heroRef}
          id="product"
          className="cin-hero"
          aria-label="Assembly introduction"
        >
          <div className="cin-hero-copy">
            <p className="cin-badge">
              Open source
              <span className="cin-badge-sep" aria-hidden>
                ·
              </span>
              Multi-agent research
            </p>

            <h1
              className="cin-hero-title"
              aria-label="Convene many minds. Leave with one answer."
            >
              Convene many minds.
              <span className="accent">Leave with one answer.</span>
            </h1>

            <p className="cin-hero-desc">
              Set a time budget and ask. A team of AI agents works separately, challenges each other, and
              returns one answer with sources and doubts.
            </p>

            <div className="cin-hero-actions">
              <Link href="/chat" className="cin-btn cin-btn-primary cin-btn-lg" aria-label="Start an investigation">
                Start an Assembly
                <ArrowRight className="size-4" aria-hidden />
              </Link>
              <a href="#how" className="cin-btn cin-btn-outline cin-btn-lg">
                <Play className="size-3.5 fill-current" aria-hidden />
                Watch 1-min demo
              </a>
            </div>

            <dl className="cin-hero-stats" aria-label="Product principles">
              <div className="cin-hero-stat">
                <strong>3–15 min</strong>
                <span>Time budgets</span>
              </div>
              <div className="cin-hero-stat">
                <strong>4+ roles</strong>
                <span>Agent team</span>
              </div>
              <div className="cin-hero-stat">
                <strong>BYOK</strong>
                <span>Keys stay local</span>
              </div>
              <div className="cin-hero-stat">
                <strong>Apache 2.0</strong>
                <span>Open source</span>
              </div>
            </dl>
          </div>

          <FloatingWindows heroRef={heroRef} />
        </section>

        <p className="cin-landing-footnote">
          Experimental research project. Not a sole source for high-stakes medical, legal or financial
          decisions.
        </p>

        <section id="how" className="cin-section">
          <div className="cin-shell">
            <div className="cin-section-head">
              <div>
                <span className="cin-kicker">How it works</span>
                <h2>Disagreement is the point.</h2>
              </div>
              <p>
                Asking more models is not the value. The value is independent reasoning that gets
                cross-examined, evidence that gets checked, and an answer that shows its work.
              </p>
            </div>

            <div className="cin-flow-grid">
              {steps.map((step) => {
                const Icon = step.icon
                return (
                  <article className="cin-flow-card" key={step.number}>
                    <span className="cin-flow-num">{step.number}</span>
                    <span className="cin-flow-icon">
                      <Icon className="size-5" aria-hidden />
                    </span>
                    <h3>{step.title}</h3>
                    <p>{step.description}</p>
                  </article>
                )
              })}
            </div>
          </div>
        </section>

        <section className="cin-section">
          <div className="cin-shell">
            <div className="cin-section-head">
              <div>
                <span className="cin-kicker">Receipts</span>
                <h2>Built to be checked.</h2>
              </div>
              <p>
                No shared operator key, no hidden paid path, no account. Every run leaves a trail you can
                read, export, and challenge.
              </p>
            </div>

            <div className="cin-proof-band">
              <div className="cin-proof">
                <strong>
                  3<em>+</em>
                </strong>
                <span>Distinct model families minimum, counted by family — never by provider.</span>
              </div>
              <div className="cin-proof">
                <strong>
                  0<em> keys</em>
                </strong>
                <span>Written to the backend. Web keys stay in your browser; desktop uses the OS keyring.</span>
              </div>
              <div className="cin-proof">
                <strong>
                  1<em> answer</em>
                </strong>
                <span>With sources, confidence, and an explicit statement of what remains uncertain.</span>
              </div>
            </div>
          </div>
        </section>

        <section className="cin-section" id="faq">
          <div className="cin-shell">
            <div className="cin-section-head">
              <div>
                <span className="cin-kicker">Good to know</span>
                <h2>Before you begin.</h2>
              </div>
              <p>What Assembly does, what it uses, and what stays in your control.</p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {faqs.map((faq) => (
                <details
                  key={faq.question}
                  className="group rounded-2xl border border-border/70 bg-card/40 p-5 backdrop-blur-md"
                >
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-semibold text-foreground">
                    {faq.question}
                    <span className="text-lg text-brand transition-transform group-open:rotate-45" aria-hidden>
                      +
                    </span>
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{faq.answer}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className="cin-section">
          <div className="cin-shell">
            <div className="cin-cta">
              <div>
                <span className="cin-kicker">Begin</span>
                <h2>
                  Make room for a<br />
                  second opinion.
                </h2>
                <p>Start with one hard question. Add a third opinion when the stakes go up.</p>
              </div>
              <Link href="/chat" className="cin-btn cin-btn-primary cin-btn-lg" aria-label="Start an investigation">
                Start an investigation
                <ArrowRight className="size-4" aria-hidden />
              </Link>
            </div>
          </div>
        </section>

        <footer className="cin-shell cin-landing-footer">
          <div className="flex items-center gap-3">
            <BrandMark />
            <span>Independent thinking, made inspectable.</span>
          </div>
          <nav aria-label="Legal and product links">
            <Link href="/history">History</Link>
            <Link href="/models">Models</Link>
            <Link href="/settings">Settings</Link>
            <Link href="/privacy">Privacy</Link>
            <Link href="/terms">Terms</Link>
          </nav>
          <span className="flex items-center gap-2">
            <CheckCircle2 className="size-3.5 text-success" aria-hidden />
            No account required
          </span>
        </footer>
      </main>
    </div>
  )
}
