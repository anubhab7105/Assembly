"use client";

import React, { useEffect, useState } from "react";
import {
  PRIVACY_ACK_KEY,
  WEB_PRIVACY_PARAGRAPHS,
  providerNoteFor,
  type EnabledProviderNote,
} from "@/lib/privacy-notice";
import { storage } from "@/lib/storage";
import { Button } from "@/components/ui/button";

export function PrivacySection({
  providers,
}: {
  providers: EnabledProviderNote[];
}) {
  const [ackAt, setAckAt] = useState<string | null>(null);

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
      className="rounded-xl border border-border bg-card p-4 space-y-3"
    >
      <h3 className="text-sm font-semibold">Privacy</h3>
      <div className="space-y-2 text-sm text-muted-foreground">
        {WEB_PRIVACY_PARAGRAPHS.map((p, i) =>
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
