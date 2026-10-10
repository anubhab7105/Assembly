"use client";

import React from "react";
import {
  DESKTOP_PRIVACY_PARAGRAPHS,
  WEB_PRIVACY_PARAGRAPHS,
  providerNoteFor,
  type EnabledProviderNote,
} from "@/lib/privacy-notice";
import { Button } from "@/components/ui/button";

export function PrivacyDialog({
  mode,
  providers,
  onAcknowledge,
}: {
  mode: "web" | "desktop";
  providers: EnabledProviderNote[];
  onAcknowledge: () => void;
}) {
  const paragraphs =
    mode === "desktop" ? DESKTOP_PRIVACY_PARAGRAPHS : WEB_PRIVACY_PARAGRAPHS;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Privacy notice"
      data-testid="privacy-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-xl">
        <h2 className="text-lg font-bold">Privacy notice</h2>
        <div className="mt-3 space-y-3 text-sm text-muted-foreground">
          {paragraphs.map((p, i) =>
            p === "Each model provider handles your inputs under its own policy:" ? (
              <div key={i}>
                <p>{p}</p>
                <ul className="mt-2 space-y-1" data-testid="provider-notes">
                  {providers.map((pr) => (
                    <li key={pr.id} data-testid={`provider-note-${pr.id}`}>
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
        <Button
          data-testid="privacy-acknowledge"
          className="mt-5 w-full"
          onClick={onAcknowledge}
        >
          I understand
        </Button>
      </div>
    </div>
  );
}
