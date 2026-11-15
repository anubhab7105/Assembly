import type { Metadata } from "next"
import { LegalPageLayout } from "@/components/legal-page-layout"

export const metadata: Metadata = {
  title: "Refund policy",
  description:
    "Assembly is free with no payments. There is nothing to refund. What costs can still appear, and what to do.",
  alternates: { canonical: "/refunds" },
}

export default function RefundsPage() {
  return (
    <LegalPageLayout title="Refund Policy">
      {/* There is nothing to refund */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          There is nothing to refund
        </h2>
        <div className="rounded-xl border border-border/40 bg-card/30 p-6">
          <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
            Assembly charges absolutely nothing. There are no subscriptions, no paywalls, no one-time unlocking fees, no in-app token purchases, and no payment card information is ever solicited or stored. Because no monetary transactions occur through Assembly, no refunds can or will arise from us.
          </p>
        </div>
      </section>

      {/* Upstream costs and Failed runs */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Third-party provider costs
          </h2>
          <div className="text-sm text-muted-foreground leading-relaxed space-y-2">
            <p>
              Your model providers (Google, Groq, OpenRouter, Cerebras) have free-tier allocations. If a provider modifies their tier rules or you exceed your free quota, any billing is governed exclusively by your agreement with that third-party provider.
            </p>
            <p>
              Assembly recommends using keys specifically restricted to zero-cost or developer free tiers.
            </p>
          </div>
        </section>

        <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Failed investigations
          </h2>
          <div className="text-sm text-muted-foreground leading-relaxed space-y-2">
            <p>
              An aborted or failed investigation costs you zero dollars from Assembly. Quota tokens consumed upstream during reasoning or synthesis are governed by that provider&apos;s API policies.
            </p>
            <p>
              If you suspect an erroneous charge from an upstream provider, contact that provider directly with your run timestamps. Never share your secret API key with anyone.
            </p>
          </div>
        </section>
      </div>

      {/* Changes */}
      <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
        <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
          Changes to this policy
        </h2>
        <p className="text-sm text-muted-foreground leading-relaxed">
          Assembly was founded on the principle of bringing your own free-tier keys to open-source and free API tiers. If our architectural model ever evolves, this statement will be updated transparently in advance.
        </p>
      </section>
    </LegalPageLayout>
  )
}
