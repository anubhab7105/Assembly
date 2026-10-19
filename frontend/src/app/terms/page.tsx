import type { Metadata } from "next"
import Link from "next/link"

export const metadata: Metadata = {
  title: "Terms of use",
  description:
    "The rules for using Assembly: free BYOK research tool, no accounts, answers with sources but no guarantees.",
  alternates: { canonical: "/terms" },
}

export default function TermsPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12 lg:py-16">
      <h1 className="text-4xl font-bold tracking-tight">Terms of use</h1>
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
          <h2 className="text-xl font-semibold">What Assembly is</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Assembly is a free, bring-your-own-key research tool run by Anubhab Das, Kolkata, India. You
            supply API keys from free model providers; Assembly orchestrates them into one cited answer. There
            are no accounts, no subscriptions, and no fees of any kind.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Your responsibilities</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>Use only API keys you are entitled to use, and follow each provider&apos;s terms and rate limits.</li>
            <li>Do not send sensitive, confidential, illegal, or other people&apos;s personal content as questions.</li>
            <li>Do not abuse the service: no scraping at scale, no evading rate limits, no attacks on the API.</li>
            <li>You need a modern browser with IndexedDB or localStorage for keys and history to persist.</li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold">No guarantee on answers</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Answers are machine-generated drafts with numbered sources, a confidence level, and uncertainty
            notes where consensus is weak. They can be wrong. Verify anything important independently before
            acting on it. Assembly is not professional advice (medical, legal, financial, or otherwise).
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Availability and limits</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Runs are limited to 3, 5, 10 or 15 minute budgets with per-IP rate limits. The service is provided
            as-is, without uptime promises, and may change or stop at any time. Provider outages, quota
            exhaustion, or revoked keys can fail a run; failed runs are never presented as completed.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Your content</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Your questions and keys stay yours. You grant Assembly only the transient right to forward them to
            your chosen providers to fulfil a run. Model providers process inputs under their own policies;
            check them before sending anything sensitive.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Liability</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            To the maximum extent the law allows, Assembly and its operator are not liable for decisions you
            make from generated answers, for provider behavior or charges (Assembly itself charges nothing),
            or for loss of browser-stored keys and history. Nothing here removes rights consumer law gives
            you, including under India&apos;s Consumer Protection Act 2019 where it applies.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Governing law</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            These terms are governed by the laws of India, with courts at Kolkata having jurisdiction, except
            where mandatory local consumer or data-protection law says otherwise. EU users keep all mandatory
            rights under EU law.
          </p>
        </section>

        <nav aria-label="Legal" className="flex flex-wrap gap-x-4 gap-y-2 border-t border-border pt-6 text-sm">
          <Link href="/privacy" className="text-brand hover:underline">Privacy policy</Link>
          <Link href="/cookies" className="text-brand hover:underline">Cookie policy</Link>
          <Link href="/refunds" className="text-brand hover:underline">Refund policy</Link>
          <Link href="/" className="text-brand hover:underline">Home</Link>
        </nav>
      </div>
    </main>
  )
}
