import type { Metadata } from "next"
import Link from "next/link"

export const metadata: Metadata = {
  title: "Privacy policy",
  description:
    "How Assembly stores API keys, processes requests, and shares data with AI providers and hosting services.",
  alternates: { canonical: "/privacy" },
}

export default function PrivacyPage() {
  return (
    <main id="main-content" tabIndex={-1} className="asm-legal mx-auto w-full max-w-3xl px-6 py-12 lg:py-16">
      <span className="asm-index">[ 08 / Privacy ]</span>
      <h1 className="text-4xl font-bold tracking-tight">Privacy policy</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Last updated: 8 November 2026. Contact:{" "}
        <a
          href="mailto:anubhab7105@gmail.com"
          className="font-medium text-foreground underline decoration-brand/50 underline-offset-4 hover:text-brand"
        >
          anubhab7105@gmail.com
        </a>
      </p>

      <div className="mt-8 space-y-8 text-left">
        <section>
          <h2 className="text-xl font-semibold">The short version</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>No accounts. No login. No tracking. No cookies set by Assembly.</li>
            <li>Saved web API keys stay in your browser (IndexedDB with a localStorage fallback). They are readable values, not encrypted at rest or protected by the operating system. If browser storage fails during removal, a key may remain saved; clearing browser/site data removes the browser copy.</li>
            <li>For hosted web capacity preflight, the browser sends all saved model-provider keys to the Assembly backend over HTTPS, regardless of model selection. A key-test request sends only the provider key being tested. Every run request sends all saved model-provider keys and any saved Tavily key, even when search is not used. The Assembly application uses submitted keys transiently and does not persist them to its application database or disk.</li>
            <li>The Assembly backend makes outbound requests to your selected providers. Hosting providers may process network traffic and keep their own operational logs under their policies.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Data we handle</h2>
          <div className="mt-3 space-y-3 text-sm text-muted-foreground">
            <p>
              <strong className="text-foreground">Saved in your browser:</strong> provider API keys, run
              history (questions, answers, sources, scores), settings, usage counters, and your privacy
              notice acknowledgment. Keys are stored as readable values in IndexedDB with a localStorage fallback; they are not encrypted at rest or stored in an OS-protected credential vault. Same-origin JavaScript, including code injected through an XSS vulnerability, can read them while they are available to the app. Remove keys in Settings or clear browser site data to delete the browser copy. If browser storage fails during removal, a key may remain saved.
            </p>
            <p>
              <strong className="text-foreground">On the hosted Assembly backend, transiently:</strong> capacity preflight sends all saved model-provider keys to the backend over HTTPS, independently of the selected models; a key-test request sends only the provider key being tested; every run sends all saved model-provider keys, any saved Tavily key, the question and model choices in an HTTPS request body, even when search is not used. The backend uses submitted keys for that request/run and does not write them to the Assembly application database or disk. Application logs record operational metadata such as timings, counts and search-query lengths, not raw request bodies, search-query text or key values; key-like values are also scrubbed by the logging filter. This describes the Assembly application, not the independent retention practices of hosting providers.
            </p>
            <p>
              <strong className="text-foreground">Application logs and limits:</strong> Assembly records operational metadata such as run identifiers, time budgets, timings and token counts. The rate limiter uses the client IP address to enforce per-IP limits; those rate-limit records are held in application memory and expire. Hosting platforms such as Vercel and Render operate their own infrastructure and logging under their respective policies.
            </p>
            <p>
              <strong className="text-foreground">What we never collect:</strong> names, emails, passwords,
              payment details, precise location, or analytics profiles. There is no sign-up form, so there is
              nothing to hand over.
            </p>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Third parties who see your inputs</h2>
          <div className="mt-3 space-y-3 text-sm text-muted-foreground">
            <p>
              Each run sends your question to the selected model providers (for example Gemini, Groq,
              OpenRouter or Hugging Face). If you saved a Tavily key, that key is included in every run
              request to the Assembly backend; Tavily receives a search request only when research actually
              uses it. When research runs, Assembly may send your full question as a search query to Tavily, Wikipedia, arXiv, Semantic Scholar or DuckDuckGo, depending on the search fallback path. Tavily receives it only when available and selected by that path; the other listed services do not require a Tavily key. Those providers process inputs under their own policies. Free tiers may reuse inputs to improve their products (Google states this for Gemini
              free-tier requests). Avoid sending sensitive or confidential information.
            </p>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Windows desktop mode</h2>
          <div className="mt-3 space-y-3 text-sm text-muted-foreground">
            <p>
              Desktop mode runs an Assembly backend locally on your PC and does not route its requests through
              the hosted Assembly web backend. The current Settings flow stores keys in the embedded WebView
              browser profile (IndexedDB with a localStorage fallback) as readable values, not encrypted at
              rest. Same-origin JavaScript, including code injected through an XSS vulnerability, can read them.
              If browser storage fails during removal, a key may remain saved; clearing WebView site data removes
              the browser copy.
            </p>
            <p>
              Preflight sends all saved model-provider keys from the WebView to the local backend over loopback,
              independently of model selection; a key-test request sends only the provider key being tested.
              Every run request sends all saved model-provider keys and any saved Tavily key,
              even when search is not used; the local backend authenticates to selected providers and uses Tavily
              only when a search request is made. The repository contains a Windows
              Credential Manager keyring adapter, but the current Settings save flow does not use it as the
              primary key store. Desktop execution history is stored locally in SQLite; the database is not
              intended to hold provider key values.
            </p>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Your rights (India and the EU)</h2>
          <div className="mt-3 space-y-3 text-sm text-muted-foreground">
            <p>
              Assembly is built for users in India, and EU visitors are possible, so this policy is written
              with India&apos;s DPDP Act 2023 and the EU GDPR in mind. Because almost everything lives in your
              own browser, you exercise most rights directly: view, correct, export (History, Export) and
              delete (History, delete or clear; Settings, remove keys) your data without asking us.
            </p>
            <p>
              For anything held server-side (transient run data, memory-only rate-limit records, host logs we
              cannot see), email{" "}
              <a
                href="mailto:anubhab7105@gmail.com"
                className="font-medium text-foreground underline decoration-brand/50 underline-offset-4 hover:text-brand"
              >
                anubhab7105@gmail.com
              </a>{" "}
              with your request. We reply within 30 days. You may also complain to India&apos;s Data Protection
              Board or your EU supervisory authority.
            </p>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Children</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Assembly is not directed at children under 13 (or under the age your country requires for
            consent). Do not use it with a child&apos;s personal information.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Changes</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            If this policy changes materially, the in-app privacy notice version is bumped and you are asked
            to acknowledge it again before running.
          </p>
        </section>

        <nav aria-label="Legal" className="flex flex-wrap gap-x-4 gap-y-2 border-t border-border pt-6 text-sm">
          <Link href="/terms" className="text-brand hover:underline">Terms</Link>
          <Link href="/cookies" className="text-brand hover:underline">Cookie policy</Link>
          <Link href="/refunds" className="text-brand hover:underline">Refund policy</Link>
          <Link href="/" className="text-brand hover:underline">Home</Link>
        </nav>
      </div>
    </main>
  )
}
