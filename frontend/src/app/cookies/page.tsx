import type { Metadata } from "next"
import { LegalPageLayout } from "@/components/legal-page-layout"

export const metadata: Metadata = {
  title: "Cookie policy",
  description:
    "Assembly sets no cookies and runs no analytics. Storage used instead: IndexedDB and localStorage on your device.",
  alternates: { canonical: "/cookies" },
}

const ROWS: [string, string, string][] = [
  ["_none by Assembly_", "No cookies are set by this site.", "Not applicable. Accept and Reject both leave the site cookie-free; only your choice is saved."],
  ["assembly (IndexedDB)", "Your keys, run history, settings, usage counters, privacy acknowledgment. Stays on your device.", "Delete via History and Settings, or clear browser site data."],
  ["assembly:* (localStorage)", "Fallback mirror used only when IndexedDB is unavailable, plus the cookie-banner choice (accepted or rejected).", "Clear browser site data. Runs still work; saved data may not persist."],
  ["Host logs (Vercel, Render)", "IP addresses and request metadata in platform operational logs under their policies.", "Platform-controlled. See their policies."],
]

export default function CookiesPage() {
  return (
    <LegalPageLayout title="Cookie Policy">
      {/* No cookies, no analytics */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          No cookies, no analytics
        </h2>
        <div className="rounded-xl border border-border/40 bg-card/30 p-6 space-y-3">
          <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
            Assembly sets zero cookies: no session cookies (there are no accounts), no consent-tracking cookies, and no third-party advertising or analytics cookies.
          </p>
          <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
            There is no Google Analytics, no Meta Pixel, no Hotjar, and no social tracking beacons on this site. Fonts are fully self-hosted, ensuring loading a page never calls external font CDNs. Both the &ldquo;Accept&rdquo; and &ldquo;Reject&rdquo; options in the bottom notice leave the site 100% cookie-free.
          </p>
        </div>
      </section>

      {/* What is stored instead table */}
      <section className="space-y-4">
        <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground border-b border-border/30 pb-3">
          What is stored instead
        </h2>
        <div className="overflow-hidden rounded-xl border border-border/40 bg-card/20">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border/40 bg-muted/40 font-semibold text-foreground">
                <tr>
                  <th scope="col" className="p-4 sm:px-6">Storage mechanism</th>
                  <th scope="col" className="p-4 sm:px-6">What is stored &amp; why</th>
                  <th scope="col" className="p-4 sm:px-6">How to remove</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {ROWS.map(([name, purpose, optOut]) => (
                  <tr key={name} className="hover:bg-muted/10 transition-colors">
                    <td className="p-4 sm:px-6 font-mono text-xs sm:text-sm font-medium text-foreground whitespace-nowrap align-top">
                      {name}
                    </td>
                    <td className="p-4 sm:px-6 text-muted-foreground leading-relaxed align-top">
                      {purpose}
                    </td>
                    <td className="p-4 sm:px-6 text-muted-foreground leading-relaxed align-top">
                      {optOut}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* How to inspect and clear your data */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Inspect &amp; clear your data
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            You can verify Assembly&apos;s storage yourself by pressing F12 in your browser, opening Developer Tools, and navigating to the Application / Storage tab. There are zero entries under Cookies. To wipe all local research data, click &ldquo;Clear site data&rdquo; or delete keys in Settings.
          </p>
        </section>

        <section className="space-y-3 rounded-xl border border-border/40 bg-card/20 p-6">
          <h2 className="text-lg sm:text-xl font-bold tracking-tight text-foreground border-b border-border/30 pb-2">
            Changes to storage practice
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">
            If we ever introduce local caching mechanisms or alter our storage architecture, this document will be updated immediately with explicit disclosure and opt-out instructions.
          </p>
        </section>
      </div>
    </LegalPageLayout>
  )
}
