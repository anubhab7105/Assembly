import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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

  it("keeps the latest selection in memory when browser storage is unavailable", () => {
    window.localStorage.setItem("assembly:theme", "light")
    render(
      <>
        <ThemeToggle />
        <ThemeToggle />
      </>,
    )

    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("Storage is unavailable")
    })
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("Storage is unavailable")
    })

    fireEvent.click(screen.getAllByRole("button", { name: "Switch to dark mode" })[0])

    expect(document.documentElement.classList.contains("dark")).toBe(true)
    expect(screen.getAllByRole("button", { name: "Switch to light mode" })).toHaveLength(2)

    render(<ThemeToggle />)
    expect(screen.getAllByRole("button", { name: "Switch to light mode" })).toHaveLength(3)

    getItem.mockRestore()
    setItem.mockRestore()
    fireEvent.click(screen.getAllByRole("button", { name: "Switch to light mode" })[0])
    expect(document.documentElement.classList.contains("dark")).toBe(false)
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
