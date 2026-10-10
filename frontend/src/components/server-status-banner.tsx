"use client"

import React from "react"
import { Button } from "@/components/ui/button"
import { AlertTriangle } from "lucide-react"

/** Visible fallback when /api/catalog is unreachable: never a silent empty page. */
export function ServerStatusBanner({ url, onRetry }: { url: string; onRetry: () => void }) {
  return (
    <div
      data-testid="server-unreachable-banner"
      className="flex items-center justify-between gap-4 rounded-xl border border-danger/30 bg-danger/10 p-4"
      role="alert"
    >
      <p className="flex items-center gap-2 text-sm text-danger">
        <AlertTriangle className="size-4 shrink-0" />
        <span>Can&apos;t reach the Assembly server at {url}</span>
      </p>
      <Button size="sm" variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}
