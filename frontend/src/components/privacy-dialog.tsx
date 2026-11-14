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

  // Base UI marks every outside root aria-hidden while a modal is open. The
  // dialog already exposes aria-modal and traps focus, so hiding the app shell
  // as well only removes the sidebar navigation from the accessibility tree.
  React.useEffect(() => {
    const shell = document.querySelector<HTMLElement>(".assembly-app-shell")
    if (!shell) return
    const clearHidden = () => {
      if (shell.getAttribute("aria-hidden") === "true") {
        shell.removeAttribute("aria-hidden")
      }
    }
    clearHidden()
    const observer = new MutationObserver(clearHidden)
    observer.observe(shell, { attributes: true, attributeFilter: ["aria-hidden"] })
    return () => observer.disconnect()
  }, [])

  return (
    <Dialog open>
      <DialogContent
        showCloseButton={false}
        aria-modal="true"
        aria-describedby="privacy-dialog-description"
        data-testid="privacy-dialog"
        className="flex max-h-[min(90vh,48rem)] max-w-lg flex-col gap-4 overflow-hidden border border-border bg-card p-6 shadow-xl"
      >
        <DialogHeader>
          <DialogTitle className="text-lg font-bold">Privacy notice</DialogTitle>
          <DialogDescription id="privacy-dialog-description" className="sr-only">
            Review how your question and selected provider information are handled,
            then acknowledge the notice to continue.
          </DialogDescription>
        </DialogHeader>
        <div className="-mr-2 min-h-0 flex-1 space-y-3 overflow-y-auto pr-2 text-sm text-muted-foreground">
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
        <div className="space-y-3 border-t border-border pt-4">
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
        </div>
      </DialogContent>
    </Dialog>
  )
}
