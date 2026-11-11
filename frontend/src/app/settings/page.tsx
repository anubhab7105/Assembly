"use client"

import React, { useEffect, useState } from "react"
import { KeysManager } from "@/components/keys-manager"
import { PrivacySection } from "@/components/privacy-section"
import { ServerStatusBanner } from "@/components/server-status-banner"
import { ThemeToggle } from "@/components/theme-toggle"
import { useComfort, type ComfortSettings } from "@/components/cinematic/comfort"
import { ApiClient } from "@/lib/api-client"
import { env } from "@/lib/env"
import { KeyRound, Laptop, Shield, Accessibility, SunMedium } from "lucide-react"

const COMFORT_ROWS: Array<{
  key: keyof ComfortSettings
  title: string
  description: string
}> = [
  {
    key: "reduce3d",
    title: "Reduce 3D motion",
    description: "Stop the floating windows and parallax while keeping the layout intact.",
  },
  {
    key: "largerText",
    title: "Larger text",
    description: "Increase the base text size across the workspace.",
  },
  {
    key: "sourcesFirst",
    title: "Show sources first",
    description: "Place the cited sources above the answer instead of below it.",
  },
  {
    key: "matchSystem",
    title: "Match system theme",
    description: "Follow the operating system's light or dark preference, overriding the theme button.",
  },
]

export default function SetupPage() {
  const { settings, update } = useComfort()
  const [notes, setNotes] = useState<{ id: string; privacy_note?: string | null }[]>([])
  const [catalogFailed, setCatalogFailed] = useState(false)
  const [retryTick, setRetryTick] = useState(0)

  useEffect(() => {
    ApiClient.catalog()
      .then((c) => {
        setCatalogFailed(false)
        setNotes(
          c.providers
            .filter((p) => p.enabled)
            .map((p) => ({ id: p.id, privacy_note: (p as { privacy_note?: string | null }).privacy_note ?? null })),
        )
      })
      .catch(() => {
        setNotes([])
        setCatalogFailed(true)
      })
  }, [retryTick])

  return (
    <div className="cin-page cin-settings-page">
      <main id="main-content" tabIndex={-1} className="cin-main">
        <div className="cin-shell cin-page-inner">
          <header className="cin-page-head">
            <div className="cin-page-head-copy">
              <span className="cin-kicker">Settings</span>
              <h1 className="cin-title">Keys and comfort</h1>
              <p className="cin-lede">
                Configure at least two ready model families. Three are recommended. Providers with
                unverified quota limits are excluded from runs.
              </p>
            </div>
            <div className="cin-page-head-aside">
              <span className="cin-page-number">08 / 08</span>
              <span className="cin-chip cin-chip-brand">
                <Shield className="size-3.5" aria-hidden />
                BYOK · local to this device
              </span>
            </div>
          </header>

          {catalogFailed && (
            <div className="mb-5">
              <ServerStatusBanner url={env.apiUrl} onRetry={() => setRetryTick((t) => t + 1)} />
            </div>
          )}

          <div className="cin-settings-grid">
            <div className="min-w-0">
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
                <div>
                  <span className="cin-kicker !mb-1 !text-[0.68rem]">Provider keys</span>
                  <h2 className="m-0 text-xl font-bold tracking-tight text-foreground">Free tiers only</h2>
                </div>
                <span className="text-xs text-muted-foreground">
                  Save a key, test it, then return to Run.
                </span>
              </div>
              <div key={retryTick} className="min-w-0">
                <KeysManager />
              </div>
            </div>

            <aside className="min-w-0 space-y-4" aria-label="Comfort, appearance and storage">
              <section className="cin-window cin-settings-card">
                <h2>
                  <Accessibility className="mr-2 inline size-4 text-brand" aria-hidden />
                  Comfort
                </h2>
                <p>Adjust the interface without changing the work.</p>
                <div className="mt-1">
                  {COMFORT_ROWS.map((row) => (
                    <div className="cin-toggle-row" key={row.key}>
                      <div>
                        <b>{row.title}</b>
                        <span>{row.description}</span>
                      </div>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={settings[row.key]}
                        aria-label={row.title}
                        className="cin-switch"
                        onClick={() => update({ [row.key]: !settings[row.key] } as Partial<ComfortSettings>)}
                      />
                    </div>
                  ))}
                </div>
              </section>

              <section className="cin-window cin-settings-card">
                <h2>
                  <SunMedium className="mr-2 inline size-4 text-brand" aria-hidden />
                  Appearance
                </h2>
                <p>Switch the whole workspace between the light and dark surface.</p>
                <div className="cin-theme-row">
                  <div>
                    <b>Paper / Ink</b>
                    <span>Cinematic light and dark palettes.</span>
                  </div>
                  <ThemeToggle className="cin-theme-toggle" />
                </div>
              </section>

              <div className="cin-note">
                <b>Where your keys live</b>
                <p>
                  <Laptop aria-hidden />
                  Web mode keeps saved keys and run history in this browser. The backend receives a key
                  only for the request that uses it and never writes it to disk, a database, or a log.
                </p>
              </div>

              <div className="cin-note">
                <b>Minimum to run</b>
                <p>
                  <KeyRound aria-hidden />
                  Two distinct model families unlock a normal run; a single family runs only after an
                  explicit confirmation. A critic always comes from a different family than the position
                  it attacks.
                </p>
              </div>

              <div className="cin-note">
                <b>Privacy first</b>
                <p>
                  <Shield aria-hidden />
                  No account, no shared operator key, no billing path. Only the providers you select
                  receive your question. Read the full notice below.
                </p>
              </div>
            </aside>
          </div>

          <div className="mt-6">
            <PrivacySection providers={notes} />
          </div>
        </div>
      </main>
    </div>
  )
}
