import type { Metadata } from "next"
import { LegalPageLayout } from "@/components/legal-page-layout"

export const metadata: Metadata = {
  title: "Privacy policy",
  description:
    "How Assembly stores API keys, processes requests, and shares data with AI providers and hosting services.",
  alternates: { canonical: "/privacy" },
}

export default function PrivacyPage() {
  return (
    <LegalPageLayout title="Privacy Policy">
      {/* The short version */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          The short version
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          <div className="rounded-xl border border-border/40 bg-card/40 p-5 space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Zero tracking &amp; zero accounts</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              No accounts. No login. No tracking cookies or analytics scripts set by Assembly.
            </p>
          </div>
          <div className="rounded-xl border border-border/40 bg-card/40 p-5 space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Keys stay in your browser</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Saved web API keys stay in your browser (IndexedDB with a localStorage fallback). They are readable values, not encrypted at rest or protected by an OS keychain.
            </p>
          </div>
          <div className="rounded-xl border border-border/40 bg-card/40 p-5 space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Transient execution only</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              For capacity preflight and run requests, keys are sent transiently over HTTPS to contact your selected providers. Assembly never writes your keys to an application database or disk.
            </p>
          </div>
          <div className="rounded-xl border border-border/40 bg-card/40 p-5 space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Outbound provider traffic</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              The Assembly backend makes outbound requests only to your selected providers. Hosting platforms process network traffic under their own operational policies.
            </p>
          </div>
        </div>
      </section>

      {/* Data we handle */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          Data we handle
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
          <div className="space-y-2 rounded-xl border border-border/40 bg-card/20 p-6">
            <h3 className="text-base font-semibold text-foreground">
              Saved in your browser
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Provider API keys, run history (questions, answers, sources, scores), settings, usage counters, and your privacy notice acknowledgment. Keys are stored as readable values in IndexedDB with a localStorage fallback; they are not encrypted at rest or stored in an OS-protected credential vault. Remove keys in Settings or clear browser site data to delete the browser copy.
            </p>
          </div>

          <div className="space-y-2 rounded-xl border border-border/40 bg-card/20 p-6">
            <h3 className="text-base font-semibold text-foreground">
              On the hosted Assembly backend (transiently)
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Capacity preflight sends saved model-provider keys over HTTPS to check quota readiness; every run request sends provider keys and questions transiently to contact model APIs. The backend uses submitted keys only for that active request and never writes them to the database or disk. Application logs scrub all key-like values.
            </p>
          </div>

          <div className="space-y-2 rounded-xl border border-border/40 bg-card/20 p-6">
            <h3 className="text-base font-semibold text-foreground">
              Application logs &amp; rate limits
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Assembly records operational metadata such as run identifiers, time budgets, response timings, and token counts. The in-memory rate limiter tracks client IP addresses to enforce fair-use limits. Hosting platforms (such as Vercel and Render) operate infrastructure logs under their respective terms.
            </p>
          </div>

          <div className="space-y-2 rounded-xl border border-border/40 bg-card/20 p-6">
            <h3 className="text-base font-semibold text-foreground">
              What we never collect
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Names, emails, passwords, payment card details, precise location, or advertising profiles. There is no user registration or sign-up form, so there is no user database to hand over.
            </p>
          </div>
        </div>
      </section>

      {/* Third parties who see your inputs */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          Third parties who see your inputs
        </h2>
        <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
          Assembly sends your questions and context only to the providers and research sources that your run actually uses:
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
          <div className="rounded-xl border border-border/30 bg-card/30 p-4 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">Model Providers</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Google (Gemini), Groq, OpenRouter, Cerebras, GitHub Models, Sambanova. Your selected models receive prompt tokens under your own API credentials.
            </p>
          </div>
          <div className="rounded-xl border border-border/30 bg-card/30 p-4 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">Web Search Services</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Tavily (when a Tavily key is supplied) receives query keywords. Fallback services include DuckDuckGo, Wikipedia, arXiv, and Semantic Scholar.
            </p>
          </div>
          <div className="rounded-xl border border-border/30 bg-card/30 p-4 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">Hosting Infrastructure</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Frontend edge CDN (Vercel) and backend application hosting (Render). They process incoming network traffic under standard operational logging.
            </p>
          </div>
        </div>
      </section>

      {/* Your rights */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          Your rights (DPDP Act &amp; GDPR)
        </h2>
        <div className="space-y-3 text-sm sm:text-base text-muted-foreground leading-relaxed">
          <p>
            Under India&apos;s Digital Personal Data Protection Act 2023 (DPDP) and the European Union&apos;s General Data Protection Regulation (GDPR), you have the right to know what personal data is held about you, to correct it, to have it erased, and to withdraw consent.
          </p>
          <p>
            Because Assembly stores your data in your own browser, you can exercise these rights directly:
          </p>
          <ul className="list-disc pl-6 space-y-1.5 text-sm">
            <li><strong className="text-foreground">To delete keys:</strong> Open Settings and click Remove on each provider card, or clear browser site data.</li>
            <li><strong className="text-foreground">To delete history:</strong> Open History in the sidebar or executions view and delete any or all saved runs.</li>
            <li><strong className="text-foreground">For server log inquiries:</strong> Email <a href="mailto:anubhab7105@gmail.com" className="font-medium text-foreground underline decoration-brand/50 hover:text-brand">anubhab7105@gmail.com</a> with your approximate run timestamp and IP address. We reply within 30 days.</li>
          </ul>
        </div>
      </section>

      {/* Children & Changes */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-4">
        <section className="space-y-3">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Children
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Assembly is not directed at children under 13 (or under the age your jurisdiction requires for consent). Do not submit children&apos;s personal information into the research composer.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Changes to this notice
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            If this privacy policy changes materially, the in-app privacy notice version is incremented and you will be asked to review and acknowledge it again before running investigations.
          </p>
        </section>
      </div>
    </LegalPageLayout>
  )
}
