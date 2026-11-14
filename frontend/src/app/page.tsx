import { LandingHeader } from "@/components/landing-header"
import { LandingFooter } from "@/components/landing-footer"
import { AboutHeroSection } from "@/components/about-hero-section"
import { TextIntroScene } from "@/components/text-intro-scene"
import {
  ArrowRight,
  CheckCircle2,
  LockKeyhole,
  MessageSquare,
  Search,
  Timer,
} from "lucide-react"

const controlItems = [
  {
    icon: LockKeyhole,
    title: "Your credentials",
    description: "Bring your own provider keys. Saved web keys stay in your browser.",
  },
  {
    icon: Timer,
    title: "Your time",
    description: "Choose 3, 5, 10, or 15 minutes for the investigation.",
  },
  {
    icon: Search,
    title: "Your evidence",
    description: "Review cited sources, confidence, and areas that remain uncertain.",
  },
  {
    icon: MessageSquare,
    title: "Your history",
    description: "Return to investigations saved locally on this device.",
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
    answer: "In web mode, saved keys and local history stay in your browser. All saved model-provider keys are sent to the Assembly backend over HTTPS for capacity preflight, regardless of model selection; a key-test request sends only the provider key being tested; every run also sends all saved model-provider keys and any saved Tavily key, even when search is not used. The backend uses them transiently to contact providers. Browser-stored keys are not encrypted at rest and can be read by same-origin JavaScript. Read the privacy notice for the full details before your first run.",
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

      <LandingHeader />

      <main id="main-content" tabIndex={-1} className="assembly-landing-curtain">
        <div className="assembly-hero-yellow-stage">
          <AboutHeroSection />
        </div>

        <section id="your-control" className="assembly-control-section">
            <div className="assembly-control-inner">
              <div className="assembly-control-copy">
                <span className="assembly-section-kicker">Built around your control</span>
                <h2>You set the boundaries.<br /><em>Assembly does the <span className="assembly-legwork">legwork.</span></em></h2>
                <p>
                  Choose the time budget, decide which models take part, attach the context that matters, and inspect the answer before you rely on it.
                </p>
              </div>

              <div className="assembly-control-list-wrapper">
                <div className="assembly-control-marquee">
                  <div className="assembly-control-marquee-track">
                    {[...controlItems, ...controlItems].map((item, idx) => {
                      const Icon = item.icon
                      return (
                        <div
                          key={idx}
                          className="assembly-control-item"
                          aria-hidden={idx >= controlItems.length ? "true" : undefined}
                        >
                          <span className="assembly-control-icon">
                            <Icon className="size-4" />
                          </span>
                          <div>
                            <b>{item.title}</b>
                            <p>{item.description}</p>
                          </div>
                          <CheckCircle2 className="size-4 assembly-control-check" />
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section id="get-started" className="assembly-section assembly-intro-text-section" aria-label="Assembly intro animation">
            <div className="assembly-intro-text-stage">
              <TextIntroScene />
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

          <LandingFooter />
        </main>
    </div>
  )
}

function ArrowDownIcon() {
  return <ArrowRight className="size-4" aria-hidden="true" />
}
