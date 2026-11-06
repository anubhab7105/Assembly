"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"
import { AlertTriangle, RotateCcw } from "lucide-react"

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    // Log the error to an error reporting service if needed
    if (process.env.NODE_ENV !== "production") console.error("Global Error Boundary caught:", error)
  }, [error])

  return (
    <div className="asm-page flex min-h-[60vh] flex-col items-center justify-center px-6 py-12 text-center">
      <div className="mb-6 flex h-14 w-14 items-center justify-center border border-danger/40 bg-danger/10 text-danger">
        <AlertTriangle className="size-7" />
      </div>
      <p className="asm-index">[ Error / Interrupted ]</p>
      <h2 className="mt-4 text-3xl font-extrabold uppercase tracking-[-0.04em] text-foreground">
        That run hit a snag
      </h2>
      <p className="mx-auto mb-8 mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
        Your keys and history are safe. Reload the page to keep going.
      </p>

      <div className="mb-8 w-full max-w-md overflow-auto border border-border bg-muted/40 p-4 text-left font-mono text-xs text-muted-foreground">
        {error.message || "Unknown rendering error."}
      </div>

      <Button onClick={() => reset()} variant="default" size="lg">
        <RotateCcw className="mr-2 size-4" />
        Reload this page
      </Button>
    </div>
  )
}
