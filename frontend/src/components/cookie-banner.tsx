"use client"

import React, { useState } from "react"
import Link from "next/link"

const CHOICE_KEY = "assembly:cookie-choice"

/** Informational banner: Assembly sets no cookies and runs no analytics. */
export function CookieBanner() {
  const [visible, setVisible] = useState(() => {
    if (typeof window === "undefined") return false
    try {
      return !window.localStorage.getItem(CHOICE_KEY)
    } catch {
      return true
    }
  })

  if (!visible) return null

  const dismiss = () => {
    try {
      window.localStorage.setItem(CHOICE_KEY, "dismissed")
    } catch {
      // Banner dismissal is best-effort only.
    }
    setVisible(false)
  }

  return (
    <div
      role="region"
      aria-label="Cookie notice"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 px-4 py-3 backdrop-blur sm:px-6"
    >
      <div className="mx-auto flex w-full max-w-6xl flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-2xl text-xs text-muted-foreground">
          Assembly sets no cookies and runs no analytics. Keys and history stay on your device.{" "}
          <Link href="/cookies" className="font-medium text-foreground underline decoration-brand/50 underline-offset-4 hover:text-brand">
            Cookie policy
          </Link>
        </p>
        <button
          onClick={dismiss}
          className="inline-flex min-h-11 items-center rounded-lg bg-brand px-5 text-sm font-semibold text-brand-foreground"
        >
          Got it
        </button>
      </div>
    </div>
  )
}
