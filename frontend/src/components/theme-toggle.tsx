"use client"

import { useEffect, useState } from "react"
import { Moon, Sun } from "lucide-react"

type Theme = "light" | "dark"

const STORAGE_KEY = "assembly:theme"
const THEME_EVENT = "assembly:theme-change"

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark")
  try {
    window.localStorage.setItem(STORAGE_KEY, theme)
  } catch {
    // The current page still receives the selected theme when storage is blocked.
  }
  window.dispatchEvent(new CustomEvent<Theme>(THEME_EVENT, { detail: theme }))
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, setTheme] = useState<Theme>("light")

  useEffect(() => {
    let initial: Theme = "light"
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY)
      if (stored === "light" || stored === "dark") initial = stored
      else if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) initial = "dark"
    } catch {
      // Fall back to the light palette when browser preferences are unavailable.
    }
    setTheme(initial)
    document.documentElement.classList.toggle("dark", initial === "dark")

    const syncTheme = (event: Event) => {
      const next = (event as CustomEvent<Theme>).detail
      if (next === "light" || next === "dark") setTheme(next)
    }
    window.addEventListener(THEME_EVENT, syncTheme)
    return () => window.removeEventListener(THEME_EVENT, syncTheme)
  }, [])

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark"
    setTheme(next)
    applyTheme(next)
  }

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
