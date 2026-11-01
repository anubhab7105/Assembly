"use client"

import React from "react"
import {
  DESKTOP_PRIVACY_PARAGRAPHS,
  WEB_PRIVACY_PARAGRAPHS,
  providerNoteFor,
  type EnabledProviderNote,
} from "@/lib/privacy-notice"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export function PrivacyDialog({
  mode,
  providers,
  onAcknowledge,
}: {
  mode: "web" | "desktop"
  providers: EnabledProviderNote[]
  onAcknowledge: () => void
}) {
  const [checked, setChecked] = React.useState(false)
  const paragraphs =
    mode === "desktop" ? DESKTOP_PRIVACY_PARAGRAPHS : WEB_PRIVACY_PARAGRAPHS

  return (
    <Dialog open>
      <DialogContent
        showCloseButton={false}
        aria-describedby="privacy-dialog-description"
        data-testid="privacy-dialog"
        className="max-h-[min(90vh,48rem)] max-w-lg overflow-y-auto border border-border bg-card p-6 shadow-xl"
      >
        <DialogHeader>
          <DialogTitle className="text-lg font-bold">Privacy notice</DialogTitle>
          <DialogDescription id="privacy-dialog-description" className="sr-only">
            Review how your question and selected provider information are handled,
            then acknowledge the notice to continue.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm text-muted-foreground">
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
          className="flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border border-border bg-muted/30 p-3 text-sm"
        >
          <input
            id="privacy-consent"
            type="checkbox"
            checked={checked}
            onChange={(event) => setChecked(event.target.checked)}
            className="mt-0.5 size-5 shrink-0 accent-brand"
          />
          <span>
            I understand my question is sent to the model providers I chose, under their policies.
          </span>
        </label>
        <Button
          data-testid="privacy-acknowledge"
          className="w-full"
          disabled={!checked}
          onClick={onAcknowledge}
        >
          I understand
        </Button>
      </DialogContent>
    </Dialog>
  )
}
