import type { Metadata } from "next"
import Link from "next/link"

export const metadata: Metadata = {
  title: "Refund policy",
  description:
    "Assembly is free with no payments. There is nothing to refund. What costs can still appear, and what to do.",
  alternates: { canonical: "/refunds" },
}

export default function RefundsPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12 lg:py-16">
      <h1 className="text-4xl font-bold tracking-tight">Refund policy</h1>
      <p className="mt-2 text-sm text-muted-foreground">Last updated: 12 October 2026.</p>

      <div className="mt-8 space-y-8 text-left">
        <section>
          <h2 className="text-xl font-semibold">There is nothing to refund</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Assembly charges nothing. There are no subscriptions, no one-time fees, no in-app purchases, and no
            payment method is ever collected. Because no money changes hands with us, no refund can arise from us.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Costs that can still appear (not ours)</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>
              Your model providers&apos; free tiers have quotas. If a key exceeds quota or a provider starts
              billing on its side, that is between you and the provider. Check each provider&apos;s pricing
              before pasting a key.
            </li>
            <li>
              The setup screen warns you off any provider that asks for payment during signup. Assembly is
              free-tier only by design.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Failed runs</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            A failed run costs you nothing from Assembly. Provider-side quota consumed by a failed run is
            governed by that provider&apos;s policy, not ours. If you believe a charge from a provider is
            wrong, contact that provider with the run time and key name (never share the key itself).
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Questions</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            <a
              href="mailto:anubhab7105@gmail.com"
              className="font-medium text-foreground underline decoration-brand/50 underline-offset-4 hover:text-brand"
            >
              anubhab7105@gmail.com
            </a>
          </p>
        </section>

        <nav aria-label="Legal" className="flex flex-wrap gap-x-4 gap-y-2 border-t border-border pt-6 text-sm">
          <Link href="/privacy" className="text-brand hover:underline">Privacy policy</Link>
          <Link href="/terms" className="text-brand hover:underline">Terms</Link>
          <Link href="/cookies" className="text-brand hover:underline">Cookie policy</Link>
          <Link href="/" className="text-brand hover:underline">Home</Link>
        </nav>
      </div>
    </main>
  )
}
