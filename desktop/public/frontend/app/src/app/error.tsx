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
    console.error("Global Error Boundary caught:", error)
  }, [error])

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center px-6 py-12 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-danger/10 text-danger mb-6">
        <AlertTriangle className="size-8" />
      </div>
      <h2 className="text-2xl font-bold tracking-tight text-foreground mb-2">
        Something went wrong!
      </h2>
      <p className="text-muted-foreground max-w-md mx-auto mb-8">
        We encountered an unexpected error. The application state might be corrupted. 
        Please try recovering the page.
      </p>
      
      <div className="bg-muted p-4 rounded-md text-xs font-mono text-left w-full max-w-md overflow-auto mb-8 border border-border">
        {error.message || "Unknown rendering error."}
      </div>

      <Button onClick={() => reset()} variant="default" size="lg">
        <RotateCcw className="size-4 mr-2" />
        Try again
      </Button>
    </div>
  )
}
