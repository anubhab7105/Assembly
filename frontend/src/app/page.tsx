import Link from "next/link"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  GitBranch,
  LockKeyhole,
  MessageSquare,
  Search,
  ShieldCheck,
  Sparkles,
  Timer,
  Users,
  Zap,
} from "lucide-react"

const processSteps = [
  {
    number: "01",
    icon: Users,
    title: "Independent perspectives",
    description: "Different model families work on the same question separately before they see one another's conclusions.",
    detail: "Start with diversity, not groupthink.",
  },
  {
    number: "02",
    icon: GitBranch,
    title: "Challenge the weak points",
    description: "A critic looks for gaps and contradictions. Research can bring evidence into the discussion.",
    detail: "Disagreement is useful signal.",
  },
  {
    number: "03",
    icon: ShieldCheck,
    title: "A synthesis you can inspect",
    description: "The final answer brings the strongest points together, with sources, confidence, and uncertainty made visible.",
    detail: "You decide what deserves trust.",
  },
]

const faqs = [
  {
    question: "Why use more than one model?",
    answer: "A single model can miss a counterargument or sound certain about a weak claim. Assembly gives different model families independent passes, then uses cross-examination and evidence review before synthesizing an answer.",
  },
  {
    question: "Do I need an account or a subscription?",
    answer: "No account is required. Assembly uses bring-your-own-key (BYOK): you add your own provider keys and use the providers' available tiers and quotas.",
  },
  {
    question: "Where are my API keys and investigation history stored?",
    answer: "In web mode, saved keys and local history stay in your browser. All saved model-provider keys are sent to the Assembly backend over HTTPS for capacity preflight and key tests, regardless of model selection; every run also sends those keys and any saved Tavily key, even when search is not used. The backend uses them transiently to contact providers. Browser-stored keys are not encrypted at rest and can be read by same-origin JavaScript. Read the privacy notice for the full details before your first run.",
  },
  {
    question: "Can I control how long an investigation runs?",
    answer: "Yes. Choose a 3, 5, 10, or 15 minute time budget before you start. Assembly uses that budget to coordinate the research workflow.",
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
  return (
    <div className="assembly-landing-page">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />

      <div className="assembly-landing-atmosphere" aria-hidden="true">
        <div className="assembly-atmosphere-glow assembly-glow-one" />
        <div className="assembly-atmosphere-glow assembly-glow-two" />
        <div className="assembly-atmosphere-grid" />
      </div>

      <header className="assembly-landing-header">
        <Link href="/" className="assembly-wordmark" aria-label="Assembly home">
          <span className="assembly-wordmark-mark"><Zap className="size-5" fill="currentColor" /></span>
          <span>assembly</span>
          <span className="assembly-wordmark-dot">.</span>
        </Link>

        <nav className="assembly-landing-links" aria-label="Main navigation">
          <Link href="#how-it-works">How it works</Link>
          <Link href="#your-control">Your control</Link>
          <Link href="#faq">FAQ</Link>
        </nav>

        <div className="assembly-landing-actions">
          <ThemeToggle className="assembly-theme-toggle" />
          <Link href="/settings" className="assembly-nav-secondary">Set up keys</Link>
          <Link href="/chat" className="assembly-nav-cta">
            Start an investigation
            <ArrowUpRight className="size-4" />
          </Link>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="assembly-landing-main">
        <section className="assembly-hero">
          <div className="assembly-hero-copy">
            <div className="assembly-eyebrow">
              <span className="assembly-eyebrow-spark"><Sparkles className="size-3.5" /></span>
              A calmer way to research with AI
            </div>

            <h1>
              One question.
              <br />
              <span>More than one</span>
              <br />
              point of view.
            </h1>

            <p className="assembly-hero-description">
              Assembly brings independent AI perspectives into one focused research process — then gives you a sourced answer you can actually examine.
            </p>

            <div className="assembly-hero-actions">
              <Link href="/chat" className="assembly-button-primary">
                Start an investigation
                <ArrowRight className="size-4" />
              </Link>
              <Link href="#how-it-works" className="assembly-button-quiet">
                See how it works
                <span aria-hidden="true">↓</span>
              </Link>
            </div>

            <div className="assembly-trust-row" aria-label="Product principles">
              <span><LockKeyhole className="size-3.5" /> Bring your own keys</span>
              <i aria-hidden="true" />
              <span><Timer className="size-3.5" /> 3–15 minute budget</span>
              <i aria-hidden="true" />
              <span><ShieldCheck className="size-3.5" /> No account required</span>
            </div>
          </div>

          <div className="assembly-hero-visual" aria-label="Illustration of Assembly's research process">
            <div className="assembly-visual-frame">
              <div className="assembly-visual-topline">
                <span><span className="assembly-live-dot" /> THE RESEARCH LOOP</span>
                <span className="assembly-visual-tag">ILLUSTRATIVE</span>
              </div>

              <div className="assembly-network-stage">
                <svg className="assembly-network-lines" viewBox="0 0 600 420" fill="none" aria-hidden="true">
                  <defs>
                    <linearGradient id="assembly-line-a" x1="80" y1="30" x2="520" y2="390" gradientUnits="userSpaceOnUse">
                      <stop stopColor="var(--brand)" stopOpacity=".05" />
                      <stop offset=".5" stopColor="var(--brand)" stopOpacity=".65" />
                      <stop offset="1" stopColor="#6C9E99" stopOpacity=".12" />
                    </linearGradient>
                    <radialGradient id="assembly-node-glow">
                      <stop stopColor="var(--brand)" stopOpacity=".24" />
                      <stop offset="1" stopColor="var(--brand)" stopOpacity="0" />
                    </radialGradient>
                  </defs>
                  <circle cx="300" cy="204" r="154" stroke="var(--border)" strokeDasharray="3 8" />
                  <circle cx="300" cy="204" r="110" stroke="var(--border)" />
                  <circle cx="300" cy="204" r="76" fill="url(#assembly-node-glow)" />
                  <path d="M106 94 C180 94 197 154 260 178" stroke="url(#assembly-line-a)" strokeWidth="1.5" />
                  <path d="M492 94 C420 94 403 154 340 178" stroke="url(#assembly-line-a)" strokeWidth="1.5" />
                  <path d="M106 318 C180 318 197 254 260 230" stroke="url(#assembly-line-a)" strokeWidth="1.5" />
                  <path d="M492 318 C420 318 403 254 340 230" stroke="url(#assembly-line-a)" strokeWidth="1.5" />
                  <circle cx="106" cy="94" r="4" fill="var(--brand)" />
                  <circle cx="492" cy="94" r="4" fill="#77A49C" />
                  <circle cx="106" cy="318" r="4" fill="#8F8AC0" />
                  <circle cx="492" cy="318" r="4" fill="#77A49C" />
                </svg>

                <div className="assembly-agent-card assembly-agent-a">
                  <span className="assembly-agent-symbol symbol-amber">A</span>
                  <span><b>Independent pass</b><small>Model family one</small></span>
                  <span className="assembly-agent-index">01</span>
                </div>
                <div className="assembly-agent-card assembly-agent-b">
                  <span className="assembly-agent-symbol symbol-teal">B</span>
                  <span><b>Independent pass</b><small>Model family two</small></span>
                  <span className="assembly-agent-index">02</span>
                </div>
                <div className="assembly-agent-card assembly-agent-c">
                  <span className="assembly-agent-symbol symbol-violet">C</span>
                  <span><b>Cross-examination</b><small>Challenge assumptions</small></span>
                  <span className="assembly-agent-index">03</span>
                </div>
                <div className="assembly-agent-card assembly-agent-d">
                  <span className="assembly-agent-symbol symbol-blue">D</span>
                  <span><b>Evidence review</b><small>Check the supporting claims</small></span>
                  <span className="assembly-agent-index">04</span>
                </div>

                <div className="assembly-core">
                  <div className="assembly-core-mark"><Zap className="size-6" fill="currentColor" /></div>
                  <b>Assembly</b>
                  <small>Coordinate · Compare · Synthesize</small>
                  <span className="assembly-core-ring assembly-ring-one" />
                  <span className="assembly-core-ring assembly-ring-two" />
                </div>
              </div>

              <div className="assembly-visual-result">
                <div className="assembly-result-icon"><CheckCircle2 className="size-4" /></div>
                <div>
                  <b>One considered answer</b>
                  <small>Sources, confidence, and uncertainty — together.</small>
                </div>
                <ArrowUpRight className="size-4 assembly-result-arrow" />
              </div>
            </div>

            <div className="assembly-visual-caption">
              <span className="assembly-caption-line" />
              <span>Different perspectives. One clear place to think.</span>
            </div>
          </div>
        </section>

        <section id="how-it-works" className="assembly-section assembly-process-section">
          <div className="assembly-section-heading">
            <div>
              <span className="assembly-section-kicker">A process you can follow</span>
              <h2>Not another black box.</h2>
            </div>
            <p>
              The value is not in asking more models. It is in making their reasoning, disagreements, and evidence useful to you.
            </p>
          </div>

          <div className="assembly-process-grid">
            {processSteps.map((step) => {
              const Icon = step.icon
              return (
                <article className="assembly-process-card" key={step.number}>
                  <div className="assembly-process-card-top">
                    <span className="assembly-step-number">{step.number}</span>
                    <span className="assembly-process-icon"><Icon className="size-5" /></span>
                  </div>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                  <span className="assembly-process-detail">{step.detail}</span>
                </article>
              )
            })}
          </div>
        </section>

        <section id="your-control" className="assembly-control-section">
          <div className="assembly-control-copy">
            <span className="assembly-section-kicker">Built around your control</span>
            <h2>You set the boundaries.<br /><em>Assembly does the legwork.</em></h2>
            <p>
              Choose the time budget, decide which models take part, attach the context that matters, and inspect the answer before you rely on it.
            </p>
            <Link href="/chat" className="assembly-text-link">
              Open your research workspace <ArrowRight className="size-4" />
            </Link>
          </div>

          <div className="assembly-control-list">
            <div className="assembly-control-item">
              <span className="assembly-control-icon"><LockKeyhole className="size-4" /></span>
              <div><b>Your credentials</b><p>Bring your own provider keys. Saved web keys stay in your browser.</p></div>
              <CheckCircle2 className="size-4 assembly-control-check" />
            </div>
            <div className="assembly-control-item">
              <span className="assembly-control-icon"><Timer className="size-4" /></span>
              <div><b>Your time</b><p>Choose 3, 5, 10, or 15 minutes for the investigation.</p></div>
              <CheckCircle2 className="size-4 assembly-control-check" />
            </div>
            <div className="assembly-control-item">
              <span className="assembly-control-icon"><Search className="size-4" /></span>
              <div><b>Your evidence</b><p>Review cited sources, confidence, and areas that remain uncertain.</p></div>
              <CheckCircle2 className="size-4 assembly-control-check" />
            </div>
            <div className="assembly-control-item">
              <span className="assembly-control-icon"><MessageSquare className="size-4" /></span>
              <div><b>Your history</b><p>Return to investigations saved locally on this device.</p></div>
              <CheckCircle2 className="size-4 assembly-control-check" />
            </div>
          </div>
        </section>

        <section className="assembly-final-cta">
          <div className="assembly-cta-orbit" aria-hidden="true">
            <span /><span /><span />
          </div>
          <div className="assembly-cta-content">
            <span className="assembly-section-kicker">For questions worth getting right</span>
            <h2>Make room for a second opinion.<br />And a third.</h2>
            <p>Start with one question. You can shape the process as you go.</p>
            <Link href="/chat" className="assembly-button-primary assembly-button-light">
              Start an investigation <ArrowRight className="size-4" />
            </Link>
          </div>
          <div className="assembly-cta-foot">
            <span><ShieldCheck className="size-3.5" /> No account required</span>
            <span><LockKeyhole className="size-3.5" /> Bring your own keys</span>
            <span><Timer className="size-3.5" /> You choose the time budget</span>
          </div>
        </section>

        <section id="faq" className="assembly-faq-section">
          <div className="assembly-section-heading">
            <div>
              <span className="assembly-section-kicker">Good to know</span>
              <h2>Before you begin.</h2>
            </div>
            <p>Clear answers about what Assembly does, what it uses, and what stays in your control.</p>
          </div>
          <div className="assembly-faq-list">
            {faqs.map((faq) => (
              <details className="assembly-faq-item" key={faq.question}>
                <summary>{faq.question}<span><ArrowDownIcon /></span></summary>
                <p>{faq.answer}</p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <footer className="assembly-landing-footer">
        <Link href="/" className="assembly-wordmark assembly-wordmark-small">
          <span className="assembly-wordmark-mark"><Zap className="size-4" fill="currentColor" /></span>
          <span>assembly</span><span className="assembly-wordmark-dot">.</span>
        </Link>
        <span>Independent thinking, made inspectable.</span>
        <nav aria-label="Legal and product links">
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <Link href="/settings">Settings</Link>
        </nav>
      </footer>
    </div>
  )
}

function ArrowDownIcon() {
  return <ArrowRight className="size-4" aria-hidden="true" />
}
