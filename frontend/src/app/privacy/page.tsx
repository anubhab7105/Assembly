import type { Metadata } from "next"
import Link from "next/link"

export const metadata: Metadata = {
  title: "Privacy policy",
  description:
    "What Assembly collects, where it stays, and who to contact. No accounts, no tracking, nothing stored on our server.",
  alternates: { canonical: "/privacy" },
}

export default function PrivacyPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12 lg:py-16">
      <h1 className="text-4xl font-bold tracking-tight">Privacy policy</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Last updated: 12 October 2026. Contact:{" "}
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
            <li>Your API keys, questions and run history stay in your browser (IndexedDB, with a localStorage fallback).</li>
            <li>Our server keeps a run in memory only while it executes, then drops it. Server logs hold metadata only.</li>
            <li>Your question and keys are sent to the model providers you chose. Their policies apply to those inputs.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Data we handle</h2>
          <div className="mt-3 space-y-3 text-sm text-muted-foreground">
            <p>
              <strong className="text-foreground">In your browser only:</strong> provider API keys, run
              history (questions, answers, sources, scores), settings, usage counters, and your privacy
              notice acknowledgment. Delete them anytime from History (delete) and Settings (remove keys).
              Clearing browser site data removes everything.
            </p>
            <p>
              <strong className="text-foreground">On our server, transiently:</strong> your question, model
              choices and API keys travel inside encrypted HTTPS request bodies for one run. Keys are never
              written to disk, URLs, or logs. Key-shaped text is scrubbed from logs automatically.
            </p>
            <p>
              <strong className="text-foreground">Server logs and limits:</strong> run id, time budget,
              timings, token counts, and the client IP address used only to enforce per-IP rate limits.
              Rate-limit records live in server memory and expire automatically.
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
              Each run sends your question to the model providers holding your keys (for example Gemini,
              Groq, OpenRouter, Hugging Face) and, when research is on, to search sources (for example
              Wikipedia, arXiv, Tavily if you added a key). Those providers process inputs under their own
              policies. Free tiers may reuse inputs to improve their products (Google states this for Gemini
              free-tier requests). Avoid sending sensitive or confidential information.
            </p>
            <p>
              Hosting platforms (Vercel for the site, Render for the API) necessarily handle network traffic
              and keep their own operational logs, including IP addresses, under their policies.
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
