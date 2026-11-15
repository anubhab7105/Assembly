"use client";

import React, { useEffect, useState } from "react";
import {
  PRIVACY_ACK_KEY,
  WEB_PRIVACY_PARAGRAPHS,
  DESKTOP_PRIVACY_PARAGRAPHS,
  providerNoteFor,
  type EnabledProviderNote,
} from "@/lib/privacy-notice";
import { storage } from "@/lib/storage";
import { env } from "@/lib/env";
import { Button } from "@/components/ui/button";
import { Shield } from "lucide-react";

export function PrivacySection({
  providers,
}: {
  providers: EnabledProviderNote[];
}) {
  const [ackAt, setAckAt] = useState<string | null>(null);
  const paragraphs = env.NEXT_PUBLIC_APP_MODE === "desktop"
    ? DESKTOP_PRIVACY_PARAGRAPHS
    : WEB_PRIVACY_PARAGRAPHS;

  useEffect(() => {
    storage
      .getSetting(PRIVACY_ACK_KEY)
      .then((raw) => {
        if (!raw) {
          setAckAt(null);
          return;
        }
        try {
          setAckAt((JSON.parse(raw) as { acknowledged_at?: string }).acknowledged_at ?? null);
        } catch {
          setAckAt(null);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <section
      data-testid="privacy-section"
      className="rounded-xl border border-border bg-card p-4 space-y-4"
    >
      <h3 className="text-sm font-semibold">Privacy</h3>

      <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3.5 text-xs text-white/80 leading-relaxed flex items-start gap-2.5">
        <Shield className="size-4 text-brand shrink-0 mt-0.5" />
        <p>
          Saved keys stay in this browser across refreshes and can be removed here or cleared with site data. Keys are stored unencrypted in local browser storage, not protected by the OS.
        </p>
      </div>

      <div className="space-y-2 text-sm text-muted-foreground">
        {paragraphs.map((p, i) =>
          p === "Each model provider handles your inputs under its own policy:" ? (
            <div key={i}>
              <p>{p}</p>
              <ul className="mt-1 space-y-1">
                {providers.map((pr) => (
                  <li key={pr.id}>
                    <span className="font-mono font-medium text-foreground">
                      {pr.id}
                    </span>
                    {": "}
                    {providerNoteFor(pr)}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p key={i}>{p}</p>
          ),
        )}
      </div>
      {ackAt && <p className="text-xs text-muted-foreground">Acknowledged: {ackAt}</p>}
      <Button
        variant="outline"
        size="sm"
        data-testid="privacy-review-again"
        onClick={() => storage.setSetting(PRIVACY_ACK_KEY, "")}
      >
        Review again
      </Button>
    </section>
  );
}
