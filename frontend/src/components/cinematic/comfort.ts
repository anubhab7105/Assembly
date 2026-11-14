"use client"

import { useEffect, useState } from "react"

export type ComfortSettings = {
  reduce3d: boolean
  largerText: boolean
  sourcesFirst: boolean
  matchSystem: boolean
}

const STORAGE_KEY = "assembly:comfort"
const EVENT = "assembly:comfort-change"

export const DEFAULT_COMFORT: ComfortSettings = {
  reduce3d: false,
  largerText: false,
  sourcesFirst: false,
  matchSystem: false,
}

export function readComfort(): ComfortSettings {
  if (typeof window === "undefined") return DEFAULT_COMFORT
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_COMFORT
    const parsed = JSON.parse(raw) as Partial<ComfortSettings>
    return { ...DEFAULT_COMFORT, ...parsed }
  } catch {
    return DEFAULT_COMFORT
  }
}

export function applyComfort(settings: ComfortSettings, options: { applyTheme?: boolean } = {}) {
  if (typeof document === "undefined") return
  const root = document.documentElement
  root.classList.toggle("comfort-reduce-3d", settings.reduce3d)
  root.classList.toggle("comfort-large-text", settings.largerText)
  root.dataset.sourcesFirst = settings.sourcesFirst ? "true" : "false"

  if (options.applyTheme !== false && settings.matchSystem) {
    let dark = true
    try {
      dark = window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false
    } catch {
      dark = false
    }
    root.classList.toggle("dark", dark)
  }
}

export function writeComfort(settings: ComfortSettings) {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // Comfort is a preference, not a requirement; the current page remains usable.
  }
  applyComfort(settings)
  window.dispatchEvent(new CustomEvent<ComfortSettings>(EVENT, { detail: settings }))
}

export function useComfort() {
  const [settings, setSettings] = useState<ComfortSettings>(DEFAULT_COMFORT)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    const next = readComfort()
    applyComfort(next)
    // Read storage after paint so hydration starts from the same defaults on
    // the server and the client, then sync the controls to the saved choice.
    queueMicrotask(() => {
      setSettings(readComfort())
      setHydrated(true)
    })

    const sync = () => setSettings(readComfort())
    window.addEventListener(EVENT, sync)
    window.addEventListener("storage", sync)
    const media = window.matchMedia?.("(prefers-color-scheme: dark)")
    const onScheme = () => {
      if (readComfort().matchSystem) applyComfort(readComfort())
    }
    media?.addEventListener?.("change", onScheme)
    return () => {
      window.removeEventListener(EVENT, sync)
      window.removeEventListener("storage", sync)
      media?.removeEventListener?.("change", onScheme)
    }
  }, [])

  const update = (patch: Partial<ComfortSettings>) => {
    const next = { ...settings, ...patch }
    setSettings(next)
    writeComfort(next)
  }

  return { settings, hydrated, update }
}
