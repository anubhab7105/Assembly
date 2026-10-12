import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ServerStatusBanner } from "./server-status-banner"

describe("ServerStatusBanner", () => {
  it("states a connection problem, never an auth problem, with retry", () => {
    const onRetry = vi.fn()
    render(<ServerStatusBanner url="http://localhost:8000" onRetry={onRetry} />)
    const banner = screen.getByTestId("server-unreachable-banner")
    expect(banner.textContent).toContain("Can't reach the Assembly server")
    expect(banner.textContent).toContain("connection problem")
    // The banner must disclaim auth framing, not imply it.
    expect(banner.textContent).toContain("not a login")
    fireEvent.click(screen.getByRole("button", { name: "Retry" }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
