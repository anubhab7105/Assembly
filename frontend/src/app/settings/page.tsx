"use client";

import React, { useEffect, useState } from "react";
import { KeysManager } from "@/components/keys-manager";
import { PrivacySection } from "@/components/privacy-section";
import { ServerStatusBanner } from "@/components/server-status-banner";
import { ThemeToggle } from "@/components/theme-toggle";
import { ApiClient } from "@/lib/api-client";
import { env } from "@/lib/env";
import { KeyRound, Laptop, Shield } from "lucide-react";

export default function SetupPage() {
  const [notes, setNotes] = useState<{ id: string; privacy_note?: string | null }[]>([]);
  const [catalogFailed, setCatalogFailed] = useState(false);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    ApiClient.catalog()
      .then((c) => {
        setCatalogFailed(false);
        setNotes(
          c.providers
            .filter((p) => p.enabled)
            .map((p) => ({ id: p.id, privacy_note: (p as { privacy_note?: string | null }).privacy_note ?? null })),
        );
      })
      .catch(() => {
        setNotes([]);
        setCatalogFailed(true);
      });
  }, [retryTick]);

  return (
    <div className="asm-page asm-settings-page min-h-screen pb-20">
      <header className="asm-page-head-wrap">
        <div className="asm-settings !py-0">
          <div className="asm-page-head">
            <div>
              <span className="asm-index">[ 07 / Settings ]</span>
              <h1 className="asm-page-title">Settings &amp; keys</h1>
            </div>
            <p className="asm-page-head-note">
              Configure at least two ready model families. Three are recommended. Providers with unverified
              quota limits are excluded from runs.
            </p>
          </div>
        </div>
      </header>

      <main id="main-content" tabIndex={-1} className="asm-settings">
        {catalogFailed && (
          <div className="mb-5">
            <ServerStatusBanner url={env.apiUrl} onRetry={() => setRetryTick((t) => t + 1)} />
          </div>
        )}

        <div className="asm-settings-grid">
          <div key={retryTick} className="min-w-0">
            <KeysManager />
          </div>

          <aside className="asm-settings-side" aria-label="Storage and appearance">
            <div className="asm-theme-card">
              <div className="asm-block-head">
                <span className="asm-label">Appearance</span>
                <span className="asm-label">Theme</span>
              </div>
              <div className="asm-theme-row">
                <div>
                  <p className="text-xs font-medium text-foreground">Paper / Ink</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                    Switch the whole workspace between the light and dark surface.
                  </p>
                </div>
                <ThemeToggle className="asm-theme-toggle" />
              </div>
            </div>

            <div className="asm-storage-note">
              <b>Where your keys live</b>
              <p className="flex gap-2">
                <Laptop className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden />
                Web mode keeps saved keys and run history in this browser. The backend receives a key only
                for the request that uses it and never writes it to disk, a database, or a log.
              </p>
            </div>

            <div className="asm-storage-note">
              <b>Minimum to run</b>
              <p className="flex gap-2">
                <KeyRound className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden />
                Two distinct model families unlock a normal run; a single family runs only after an explicit
                confirmation. A critic always comes from a different family than the position it attacks.
              </p>
            </div>

            <div className="asm-storage-note">
              <b>Privacy first</b>
              <p className="flex gap-2">
                <Shield className="mt-0.5 size-3.5 shrink-0 text-brand" aria-hidden />
                No account, no shared operator key, no billing path. Only the providers you select receive
                your question. Read the full notice below.
              </p>
            </div>
          </aside>
        </div>

        <div className="mt-5">
          <PrivacySection providers={notes} />
        </div>
      </main>
    </div>
  );
}
