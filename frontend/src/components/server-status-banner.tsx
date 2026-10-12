"use client"

import React from "react"
import { Button } from "@/components/ui/button"
import { AlertTriangle } from "lucide-react"

/** Reachability fallback when /api/catalog fails: never a silent empty page. */
export function ServerStatusBanner({ url, onRetry }: { url: string; onRetry: () => void }) {
  return (
    <div
      data-testid="server-unreachable-banner"
      className="flex items-center justify-between gap-4 rounded-xl border border-danger/30 bg-danger/10 p-4"
      role="alert"
    >
      <div className="text-sm text-danger">
        <p className="flex items-center gap-2 font-medium">
          <AlertTriangle className="size-4 shrink-0" />
          <span>Can&apos;t reach the Assembly server at {url}</span>
        </p>
        <p className="mt-1 text-xs opacity-80">
          Check the backend is running and reachable from this browser. This is a
          connection problem, not a key or permission issue.
        </p>
      </div>
      <Button size="sm" variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}
