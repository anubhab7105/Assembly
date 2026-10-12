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
  const [checked, setChecked] = React.useState(false);
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
        <label
          htmlFor="privacy-consent"
          className="mt-5 flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border border-border bg-muted/30 p-3 text-sm"
        >
          <input
            id="privacy-consent"
            type="checkbox"
            checked={checked}
            onChange={(e) => setChecked(e.target.checked)}
            className="mt-0.5 size-5 shrink-0 accent-brand"
          />
          <span>
            I understand my question is sent to the model providers I chose, under their policies.
          </span>
        </label>
        <Button
          data-testid="privacy-acknowledge"
          className="mt-3 w-full"
          disabled={!checked}
          onClick={onAcknowledge}
        >
          I understand
        </Button>
      </div>
    </div>
  );
}
