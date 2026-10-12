import type { Metadata } from "next"
import Link from "next/link"

export const metadata: Metadata = {
  title: "Cookie policy",
  description:
    "Assembly sets no cookies and runs no analytics. Storage used instead: IndexedDB and localStorage on your device.",
  alternates: { canonical: "/cookies" },
}

const ROWS: [string, string, string][] = [
  ["_none by Assembly_", "No cookies are set by this site.", "Not applicable. There is nothing to accept or reject."],
  ["assembly (IndexedDB)", "Your keys, run history, settings, usage counters, privacy acknowledgment. Stays on your device.", "Delete via History and Settings, or clear browser site data."],
  ["assembly:* (localStorage)", "Fallback mirror used only when IndexedDB is unavailable, plus the cookie-banner dismissal.", "Clear browser site data. Runs still work; saved data may not persist."],
  ["Host logs (Vercel, Render)", "IP addresses and request metadata in platform operational logs under their policies.", "Platform-controlled. See their policies."],
]

export default function CookiesPage() {
  return (
    <main className="mx-auto w-full max-w-3xl px-6 py-12 lg:py-16">
      <p className="rounded-xl border border-warning/40 bg-warning-subtle px-4 py-3 text-sm font-medium text-warning">
        Draft, not legal advice. A real lawyer must review this page before you
        rely on it.
      </p>
      <h1 className="mt-6 text-4xl font-bold tracking-tight">Cookie policy</h1>
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
          <h2 className="text-xl font-semibold">No cookies, no analytics</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            Assembly sets zero cookies: no login cookies (there are no accounts), no consent-tracking cookies,
            and no third-party advertising or analytics cookies. There is no Google Analytics, no Meta Pixel, no
            Hotjar, and no social-media trackers on this site. Fonts are self-hosted, so loading a page does
            not call Google Fonts servers. Because there are no non-essential cookies, there is nothing for a
            consent banner to switch off; the banner on this site is informational and dismisses without
            recording anything about you beyond its own dismissal.
          </p>
        </section>

        <section>
          <h2 className="text-xl font-semibold">What is stored instead</h2>
          <div className="mt-3 overflow-x-auto rounded-xl border border-border">
            <table className="w-full min-w-132 text-left text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 font-semibold">Storage</th>
                  <th className="px-4 py-3 font-semibold">Purpose</th>
                  <th className="px-4 py-3 font-semibold">Control</th>
                </tr>
              </thead>
              <tbody className="text-muted-foreground">
                {ROWS.map(([name, purpose, control]) => (
                  <tr key={name} className="border-b border-border/50 last:border-0">
                    <td className="px-4 py-3 font-mono text-xs text-foreground">{name}</td>
                    <td className="px-4 py-3">{purpose}</td>
                    <td className="px-4 py-3">{control}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold">Do-not-track and consent</h2>
          <p className="mt-3 text-sm text-muted-foreground">
            With no analytics or advertising, there is no behavioral tracking to opt out of. The one consent
            that matters is the in-app privacy notice: a run cannot start until you tick the acknowledgment
            checkbox confirming your question goes to your chosen providers. Withdrawing that consent is the
            same as stopping use: remove your keys and clear site data.
          </p>
        </section>

        <nav aria-label="Legal" className="flex flex-wrap gap-x-4 gap-y-2 border-t border-border pt-6 text-sm">
          <Link href="/privacy" className="text-brand hover:underline">Privacy policy</Link>
          <Link href="/terms" className="text-brand hover:underline">Terms</Link>
          <Link href="/refunds" className="text-brand hover:underline">Refund policy</Link>
          <Link href="/" className="text-brand hover:underline">Home</Link>
        </nav>
      </div>
    </main>
  )
}
