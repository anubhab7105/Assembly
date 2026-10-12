"use client";

import React, { useEffect, useState } from "react";
import { KeysManager } from "@/components/keys-manager";
import { PrivacySection } from "@/components/privacy-section";
import { ServerStatusBanner } from "@/components/server-status-banner";
import { ApiClient } from "@/lib/api-client";
import { env } from "@/lib/env";
import { Shield } from "lucide-react";

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
    <div className="min-h-screen bg-background pb-20">
      {/* Header */}
      <header className="border-b border-border bg-card">
        <div className="mx-auto max-w-5xl px-6 py-10">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-brand-foreground shadow-sm">
              <Shield className="size-5" />
            </span>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-foreground">Add your free keys</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Paste two free keys. Get answers from three or more model families.
              </p>
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-5xl px-6 pt-8 space-y-8">
        {catalogFailed && (
          <ServerStatusBanner url={env.apiUrl} onRetry={() => setRetryTick((t) => t + 1)} />
        )}
        <div key={retryTick}>
          <KeysManager />
        </div>
        <PrivacySection providers={notes} />
      </main>
    </div>
  )
}
