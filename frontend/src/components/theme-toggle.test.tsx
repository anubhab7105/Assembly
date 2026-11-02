import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { ThemeToggle } from "./theme-toggle"

describe("ThemeToggle", () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.classList.remove("dark")
  })

  afterEach(() => {
    cleanup()
    document.documentElement.classList.remove("dark")
  })

  it("persists the chosen theme and synchronizes multiple controls", () => {
    render(
      <>
        <ThemeToggle />
        <ThemeToggle />
      </>,
    )

    const toggles = screen.getAllByRole("button", { name: "Switch to dark mode" })
    expect(toggles).toHaveLength(2)

    fireEvent.click(toggles[0])

    expect(document.documentElement.classList.contains("dark")).toBe(true)
    expect(window.localStorage.getItem("assembly:theme")).toBe("dark")
    expect(screen.getAllByRole("button", { name: "Switch to light mode" })).toHaveLength(2)
  })

  it("restores the saved preference when mounted", async () => {
    window.localStorage.setItem("assembly:theme", "dark")
    render(<ThemeToggle />)

    await waitFor(() => {
      expect(document.documentElement.classList.contains("dark")).toBe(true)
    })
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeTruthy()
  })
})
