"use client"

import { useEffect, useSyncExternalStore } from "react"
import { Moon, Sun } from "lucide-react"

type Theme = "light" | "dark"

const STORAGE_KEY = "assembly:theme"
const THEME_EVENT = "assembly:theme-change"
let memoryTheme: Theme | null = null

function getSystemTheme(): Theme {
  try {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"
  } catch {
    return "light"
  }
}

function getThemeSnapshot(): Theme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored === "light" || stored === "dark") return stored
  } catch {
    return memoryTheme ?? getSystemTheme()
  }
  return memoryTheme ?? getSystemTheme()
}

function getServerThemeSnapshot(): Theme {
  return "light"
}

function subscribeTheme(onStoreChange: () => void) {
  window.addEventListener(THEME_EVENT, onStoreChange)
  window.addEventListener("storage", onStoreChange)
  return () => {
    window.removeEventListener(THEME_EVENT, onStoreChange)
    window.removeEventListener("storage", onStoreChange)
  }
}

function subscribeHydration() {
  return () => {}
}

function getHydrationSnapshot() {
  return true
}

function getServerHydrationSnapshot() {
  return false
}

function applyTheme(theme: Theme) {
  memoryTheme = theme
  document.documentElement.classList.toggle("dark", theme === "dark")
  try {
    window.localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // The in-memory selection keeps the current page usable without browser storage.
  }
  window.dispatchEvent(new CustomEvent<Theme>(THEME_EVENT, { detail: theme }))
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const theme = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getServerThemeSnapshot)
  const hydrated = useSyncExternalStore(
    subscribeHydration,
    getHydrationSnapshot,
    getServerHydrationSnapshot,
  )

  useEffect(() => {
    if (!hydrated) return
    document.documentElement.classList.toggle("dark", theme === "dark")
  }, [hydrated, theme])

  const toggle = () => applyTheme(theme === "dark" ? "light" : "dark")

  return (
    <button
      type="button"
      onClick={toggle}
      className={className}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  )
}
