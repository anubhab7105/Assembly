"use client"

import Link from "next/link"
import { useEffect, useRef } from "react"
import { ThemeToggle } from "@/components/theme-toggle"
import { Cursor3D } from "@/components/landing/cursor-3d"
import { ParticleSphere } from "@/components/landing/particle-sphere"
import { useMotionInput } from "@/components/landing/use-motion-input"
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  GitBranch,
  LockKeyhole,
  Search,
  ShieldCheck,
  Timer,
  Users,
  Video,
} from "lucide-react"

const processSteps = [
  {
    number: "01",
    icon: Users,
    title: "Independent perspectives",
    description:
      "Different model families work on the same question separately before they see one another's conclusions.",
    detail: "Start with diversity, not groupthink.",
  },
  {
    number: "02",
    icon: GitBranch,
    title: "Challenge the weak points",
    description:
      "A critic looks for gaps and contradictions. Research can bring evidence into the discussion.",
    detail: "Disagreement is useful signal.",
  },
  {
    number: "03",
    icon: ShieldCheck,
    title: "A synthesis you can inspect",
    description:
      "The final answer brings the strongest points together, with sources, confidence, and uncertainty made visible.",
    detail: "You decide what deserves trust.",
  },
]

const controlItems = [
  {
    icon: LockKeyhole,
    label: "Credentials",
    title: "Your keys",
    description: "Bring your own provider keys. Saved web keys stay in your browser.",
  },
  {
    icon: Timer,
    label: "Time",
    title: "Your budget",
    description: "Choose 3, 5, 10, or 15 minutes for the investigation.",
  },
  {
    icon: Search,
    label: "Evidence",
    title: "Your sources",
    description: "Review cited sources, confidence, and the areas that remain uncertain.",
  },
  {
    icon: CheckCircle2,
    label: "History",
    title: "Your record",
    description: "Return to investigations saved locally on this device.",
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
      "No account is required. Assembly uses bring-your-own-key (BYOK): you add your own provider keys and use the providers' available tiers and quotas.",
  },
  {
    question: "Where are my API keys and investigation history stored?",
    answer:
      "In web mode, saved keys and local history stay in your browser. Your question and selected provider information are sent to the providers you choose. Read the privacy notice for the full details before your first run.",
  },
  {
    question: "Can I control how long an investigation runs?",
    answer:
      "Yes. Choose a 3, 5, 10, or 15 minute time budget before you start. Assembly uses that budget to coordinate the research workflow.",
  },
]

const schema = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  name: "Assembly",
  url: "https://assembly-murex.vercel.app/",
  description: "Multi-model research that turns one hard question into one sourced, inspectable answer.",
}

const tickerItems = [
  "Plan → Solve → Compare → Synthesize",
  "Diverse model families",
  "Bring your own keys",
  "3 / 5 / 10 / 15 minute budgets",
  "Sources · confidence · uncertainty",
]

const crossPositions = [
  [7, 120],
  [19, 84],
  [32, 160],
  [45, 108],
  [58, 148],
  [71, 96],
  [84, 132],
  [93, 190],
  [12, 300],
  [26, 360],
  [41, 318],
  [55, 410],
  [68, 344],
  [81, 392],
  [90, 300],
  [6, 520],
  [22, 560],
  [38, 512],
  [52, 604],
  [66, 548],
  [79, 596],
  [91, 640],
]

export default function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null)
  const {
    field,
    cameraState,
    cameraError,
    cameraActive,
    handActive,
    toggleCamera,
    sensorState,
    sensorActive,
    toggleSensors,
  } = useMotionInput({ rootRef })

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

  const cameraLabel =
    cameraState === "requesting"
      ? "ASKING"
      : cameraState === "unsupported"
        ? "N/A"
        : cameraActive
          ? handActive
            ? "TRACKING"
            : "ON"
          : "OFF"
  const showSensorToggle = sensorState !== "unsupported"

  return (
    <div ref={rootRef} className="asm-landing">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
      />

      <Cursor3D />

      <div className="asm-landing-crosses" aria-hidden="true">
        {crossPositions.map(([left, top]) => (
          <span key={`${left}-${top}`} className="asm-landing-cross" style={{ left: `${left}%`, top }} />
        ))}
      </div>

      <header className="asm-topbar">
        <Link href="/" className="asm-brand" aria-label="Assembly home">
          <span className="asm-mark" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
          <span>Assembly</span>
        </Link>

        <nav className="asm-nav" aria-label="Main navigation">
          <Link href="/chat">Run ↗</Link>
          <Link href="/history">History ↗</Link>
          <Link href="/settings">Settings ↗</Link>
          <a href="https://github.com/arkap1502/Assembly#readme" target="_blank" rel="noreferrer">
            Docs ↗
          </a>
        </nav>

        <div className="asm-topbar-actions">
          <ThemeToggle className="asm-theme-toggle" />
          <Link href="/settings" className="asm-link-quiet">
            Set up keys
          </Link>
          <Link href="/chat" className="asm-btn asm-btn-primary">
            Start an investigation
            <ArrowUpRight className="size-3.5" />
          </Link>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="asm-landing-main">
        <section className="asm-hero" aria-label="Assembly introduction">
          <div className="asm-hero-copy">
            <div className="asm-eyebrow">
              <span className="asm-eyebrow-tick" aria-hidden="true" />
              [ Multi-agent AI workspace ]
            </div>

            <h1>
              One question.
              <br />
              <em>Many models.</em>
              <br />
              <span className="asm-hero-outline">One answer.</span>
            </h1>

            <p className="asm-hero-description">
              Assembly gives independent AI perspectives their own pass at a hard question, cross-examines
              the disagreements, and returns one sourced answer you can actually inspect.
            </p>

            <div className="asm-hero-actions">
              <Link href="/chat" className="asm-btn asm-btn-primary asm-btn-lg">
                Start an investigation
                <ArrowRight className="size-4" />
              </Link>
              <Link href="#process" className="asm-btn asm-btn-outline asm-btn-lg">
                See the loop
                <span aria-hidden="true">↓</span>
              </Link>
            </div>

            <dl className="asm-hero-meta" aria-label="Product principles">
              <div>
                <dt>[ BYOK ]</dt>
                <dd>Your keys. Your browser.</dd>
              </div>
              <div>
                <dt>[ 3–15 MIN ]</dt>
                <dd>A budget you set.</dd>
              </div>
              <div>
                <dt>[ NO ACCOUNT ]</dt>
                <dd>No sign-up, no tracking.</dd>
              </div>
            </dl>
          </div>

          <div className="asm-hero-visual">
            <div className="asm-orb">
              <div className="asm-orb-frame" aria-hidden="true" />
              <div className="asm-orb-stage" aria-hidden="true">
                <ParticleSphere field={field} />
                <span className="asm-orb-halo" />
              </div>
              <div className="asm-orb-hud asm-orb-hud-top">
                <span className="is-live">Temporary team / live field</span>
                <span>(A)</span>
              </div>
              <div className="asm-orb-hud asm-orb-hud-bottom">
                <span>001 / 008</span>
                <span>Solvers · critic · synthesis</span>
              </div>
              <span className="asm-orb-tag asm-orb-tag-1">Independent pass</span>
              <span className="asm-orb-tag asm-orb-tag-2">Cross-examination</span>
              <span className="asm-orb-tag asm-orb-tag-3">Evidence review</span>
              <span className="asm-orb-tag asm-orb-tag-4">Synthesis</span>
            </div>

            <div className="asm-sensor-bar">
              <div>
                <span className="asm-label">
                  {cameraActive
                    ? handActive
                      ? "Hand field / tracking"
                      : "Hand field / searching"
                    : "Hand field"}
                </span>
                <p>
                  {cameraActive
                    ? handActive
                      ? "Move your hand to drag the cloud. Open it to scatter the particles, close it to gather them."
                      : "Hold your hand in frame. The field follows skin and motion in this tab — nothing is recorded or uploaded."
                    : "Hold a hand in frame to drag the cloud and scatter its particles. Frames are analysed on this device — never recorded, never uploaded."}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {showSensorToggle && (
                  <button
                    type="button"
                    className="asm-sensor-toggle"
                    data-state={sensorActive ? "on" : "off"}
                    aria-pressed={sensorActive}
                    onClick={toggleSensors}
                    title="Use device orientation to move the field"
                  >
                    Tilt
                    <span className="asm-switch" aria-hidden="true" />
                  </button>
                )}
                <button
                  type="button"
                  className="asm-sensor-toggle"
                  data-state={cameraActive ? "on" : "off"}
                  aria-pressed={cameraActive}
                  onClick={() => void toggleCamera()}
                  disabled={cameraState === "unsupported"}
                  title="Use the camera to track your hand locally"
                >
                  <Video className="size-3" aria-hidden="true" />
                  {cameraLabel}
                  <span className="asm-switch" aria-hidden="true" />
                </button>
              </div>
            </div>
            {cameraError && (
              <p className="asm-sensor-error" role="status">
                {cameraError}
              </p>
            )}
          </div>
        </section>

        <div className="asm-ticker" aria-hidden="true">
          <div className="asm-ticker-track">
            {[...tickerItems, ...tickerItems].map((item, index) => (
              <span key={`${item}-${index}`}>{item}</span>
            ))}
          </div>
        </div>

        <section id="process" className="asm-section asm-shell" aria-labelledby="process-title">
          <div className="asm-section-head" data-reveal>
            <span className="asm-index">[ 01 / Process ]</span>
            <h2 id="process-title">Not another black box.</h2>
            <p>
              The value is not in asking more models. It is in making their reasoning, disagreements, and
              evidence useful to you.
            </p>
          </div>

          <div className="asm-process">
            {processSteps.map((step, index) => {
              const Icon = step.icon
              return (
                <article
                  className="asm-process-card"
                  key={step.number}
                  data-reveal
                  style={{ transitionDelay: `${index * 70}ms` }}
                >
                  <div className="asm-process-top">
                    <span className="asm-process-num">[ {step.number} ]</span>
                    <span className="asm-process-icon">
                      <Icon className="size-4" />
                    </span>
                  </div>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                  <span className="asm-process-tag">{step.detail}</span>
                </article>
              )
            })}
          </div>

          <div className="asm-flow" aria-hidden="true">
            <span>
              <b>Plan</b> →
            </span>
            <span>
              <b>Solve</b> →
            </span>
            <span>
              <b>Compare</b> →
            </span>
            <span>
              <b>Synthesize</b>
            </span>
            <span>Same question / independent passes</span>
          </div>
        </section>

        <section id="control" className="asm-shell asm-control" aria-labelledby="control-title">
          <div className="asm-control-copy" data-reveal>
            <span className="asm-index">[ 02 / Control ]</span>
            <h2 id="control-title">
              You set the boundaries.
              <br />
              <em>Assembly does the legwork.</em>
            </h2>
            <p>
              Choose the time budget, decide which models take part, attach the context that matters, and
              inspect the answer before you rely on it.
            </p>
            <Link href="/chat" className="asm-control-link">
              Open your research workspace <ArrowRight className="size-4" />
            </Link>
          </div>

          <div className="asm-control-list" data-reveal>
            {controlItems.map((item) => {
              const Icon = item.icon
              return (
                <div className="asm-control-item" key={item.title}>
                  <span className="asm-label">
                    <Icon className="mr-2 inline size-3" aria-hidden="true" />
                    {item.label}
                  </span>
                  <div>
                    <b>{item.title}</b>
                    <p>{item.description}</p>
                  </div>
                  <CheckCircle2 className="size-4" aria-hidden="true" />
                </div>
              )
            })}
          </div>
        </section>

        <section className="asm-shell" aria-label="Assembly principles">
          <div className="asm-section-head" data-reveal>
            <span className="asm-index">[ 03 / Receipts ]</span>
            <h2>Built to be checked.</h2>
            <p>
              No shared operator key. No hidden paid tier. Every run leaves a trail you can read, export,
              and challenge.
            </p>
          </div>
          <div className="asm-proof" data-reveal>
            <div>
              <strong>
                3<span>+</span>
              </strong>
              <small>Distinct model families minimum, counted by family—not provider</small>
            </div>
            <div>
              <strong>
                4<span>×</span>
              </strong>
              <small>Plan, solve, compare, and synthesize before anything is called an answer</small>
            </div>
            <div>
              <strong>
                0<span> keys</span>
              </strong>
              <small>Stored by the backend. Web keys stay in this browser. Desktop uses the OS keyring</small>
            </div>
          </div>
        </section>

        <section className="asm-shell">
          <div className="asm-cta" data-reveal>
            <div className="asm-cta-rings" aria-hidden="true">
              <i />
              <i />
              <i />
              <b />
              <b />
              <b />
            </div>
            <div className="asm-cta-content">
              <span className="asm-index">[ 04 / Begin ]</span>
              <h2>
                Make room for a<br />
                <em>second opinion.</em>
                <br />
                And a third.
              </h2>
              <p>Start with one question. You can shape the process as you go.</p>
              <Link href="/chat" className="asm-btn asm-btn-primary asm-btn-lg">
                Start an investigation
                <ArrowRight className="size-4" />
              </Link>
            </div>
            <div className="asm-cta-foot">
              <span>
                <ShieldCheck className="mr-1 inline size-3" /> No account required
              </span>
              <span>
                <LockKeyhole className="mr-1 inline size-3" /> Bring your own keys
              </span>
              <span>
                <Timer className="mr-1 inline size-3" /> You choose the budget
              </span>
            </div>
          </div>
        </section>

        <section id="faq" className="asm-shell asm-faq" aria-labelledby="faq-title">
          <div className="asm-faq-intro" data-reveal>
            <span className="asm-index">[ 05 / Good to know ]</span>
            <h2 id="faq-title">Before you begin.</h2>
            <p>Clear answers about what Assembly does, what it uses, and what stays in your control.</p>
          </div>
          <div className="asm-faq-list">
            {faqs.map((faq) => (
              <details className="asm-faq-item" key={faq.question}>
                <summary>
                  {faq.question}
                  <span aria-hidden="true">+</span>
                </summary>
                <p>{faq.answer}</p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <footer className="asm-footer">
        <Link href="/" className="asm-brand" aria-label="Assembly home">
          <span className="asm-mark" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
          <span>Assembly</span>
        </Link>
        <p>Independent thinking, made inspectable.</p>
        <nav aria-label="Legal and product links">
          <Link href="/history">History</Link>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <Link href="/settings">Settings</Link>
        </nav>
        <span className="asm-footer-end">[ 001 / 008 ]</span>
      </footer>
    </div>
  )
}
