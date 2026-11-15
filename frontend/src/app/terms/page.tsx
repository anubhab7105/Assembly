import type { Metadata } from "next"
import { LegalPageLayout } from "@/components/legal-page-layout"

export const metadata: Metadata = {
  title: "Terms of use",
  description:
    "The rules for using Assembly: free BYOK research tool, no accounts, answers with sources but no guarantees.",
  alternates: { canonical: "/terms" },
}

export default function TermsPage() {
  return (
    <LegalPageLayout title="Terms of Use">
      {/* What Assembly is */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          What Assembly is
        </h2>
        <div className="rounded-xl border border-border/40 bg-card/30 p-6">
          <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
            Assembly is a free, bring-your-own-key (BYOK) research tool run by Anubhab Das, Kolkata, India. You supply API keys from free model providers; Assembly coordinates them into one structured, cross-examined, and cited answer. There are no accounts, no subscriptions, and no fees of any kind.
          </p>
        </div>
      </section>

      {/* Your responsibilities */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          Your responsibilities
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">Legitimate API Keys</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Use only API keys you are entitled to use, and adhere to each respective provider&apos;s published terms, acceptable use policies, and rate limits.
            </p>
          </div>
          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">Sensitive Data</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Do not send sensitive, confidential, illegal, privileged, or personal data belonging to others as questions or context.
            </p>
          </div>
          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">System Integrity</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Do not abuse the platform: no automated scraping at scale, no evading rate limits, and no adversarial attacks against the backend APIs.
            </p>
          </div>
          <div className="rounded-xl border border-border/40 bg-card/30 p-5 space-y-1.5">
            <h3 className="text-sm font-semibold text-foreground">Browser Storage</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              You need a modern web browser supporting IndexedDB or localStorage for your configuration and run history to persist across sessions.
            </p>
          </div>
        </div>
      </section>

      {/* No guarantee on answers & Free tier */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            No guarantee on answers
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Answers are machine-generated research drafts with cited sources, confidence scores, and uncertainty notes where consensus is contested. AI models can hallucinate or produce incorrect claims. Always verify critical facts, legal opinions, medical advice, and financial guidance independently.
          </p>
        </section>

        <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Free tier &amp; provider quotas
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Assembly is strictly configured for free-tier usage. If an upstream provider begins billing for tokens or exceeds usage thresholds, that billing relationship is strictly between you and that provider. Assembly never collects payment details or charges fees.
          </p>
        </section>
      </div>

      {/* Intellectual property & Liability */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Intellectual property
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            You retain all rights to the research questions you formulate and submit. To the extent permissible under copyright laws, synthesized outputs belong to you, subject to the terms of the underlying model providers (e.g. Google, Meta, Mistral, Qwen).
          </p>
        </section>

        <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Limitation of liability
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Assembly is provided &ldquo;as is&rdquo; without warranty of any kind. Under no circumstances will the operators of Assembly be liable for any direct, indirect, incidental, special, or consequential damages resulting from the use or inability to use this research platform.
          </p>
        </section>
      </div>

      {/* Governing law and changes */}
      <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
        <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
          Governing law &amp; disputes
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          These terms are governed by the laws of India. Any disputes arising out of or in connection with these terms shall be subject to the exclusive jurisdiction of the competent courts in Kolkata, West Bengal, India.
        </p>
      </section>
    </LegalPageLayout>
  )
}
