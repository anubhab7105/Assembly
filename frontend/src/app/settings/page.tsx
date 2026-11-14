"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { KeysManager } from "@/components/keys-manager";
import { PrivacySection } from "@/components/privacy-section";
import { ServerStatusBanner } from "@/components/server-status-banner";
import { ApiClient } from "@/lib/api-client";
import { env } from "@/lib/env";
import { X } from "lucide-react";

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
    <div className="assembly-settings-page min-h-screen pb-20">
      {/* Marigold Yellow Header */}
      <header className="assembly-settings-heading relative">
        <div className="w-full px-6 sm:px-10 lg:px-12 py-7 sm:py-9">
          <div className="max-w-2xl pr-16 sm:pr-24">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#000000]">
              <span className="assembly-settings-add-word">Add</span> your free keys
            </h1>
            <p className="text-sm text-[#000000]/80 mt-1 leading-relaxed font-medium">
              Configure at least two ready model families. Three are recommended; providers with unverified quota limits are excluded from runs.
            </p>
          </div>
        </div>

        {/* Top-Right Corner Close Button */}
        <Link
          href="/chat"
          className="assembly-settings-close-btn absolute top-3.5 right-4 sm:top-4 sm:right-6 shrink-0"
          aria-label="Back to investigation"
          title="Back to investigation"
        >
          <X className="size-4" />
          <span className="sr-only">Back to investigation</span>
        </Link>
      </header>

      {/* Content */}
      <main id="main-content" tabIndex={-1} className="assembly-settings-main mx-auto space-y-8">
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
