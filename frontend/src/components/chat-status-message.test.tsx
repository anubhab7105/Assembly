import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { ChatStatusMessage } from "./chat-status-message"
import type { ChatStatus, ChatStatusType } from "@/lib/chat-status"

function statusFor(type: ChatStatus["type"], text = "Status message."): ChatStatus {
  return { type, text }
}

function attributes(element: Element) {
  return {
    role: element.getAttribute("role"),
    ariaLive: element.getAttribute("aria-live"),
  }
}

describe("ChatStatusMessage", () => {
  it.each([
    ["success", "status", "polite", "bg-success-subtle", "text-success"],
    ["info", "status", "polite", "bg-info-subtle", "text-info"],
    ["progress", "status", "polite", "bg-brand/10", "text-brand"],
    ["warning", "status", "polite", "bg-warning-subtle", "text-warning"],
    ["error", "alert", "assertive", "bg-danger-subtle", "text-danger"],
  ])(
    "renders type %s with correct role, politeness, and styling",
    (type, role, live, bg, textColor) => {
      render(<ChatStatusMessage status={statusFor(type as ChatStatusType)} />)

      const region = screen.getByText("Status message.")
      expect(attributes(region).role).toBe(role)
      expect(attributes(region).ariaLive).toBe(live)
      expect(region.className).toContain(bg)
      expect(region.className).toContain(textColor)
    }
  )

  it.each(["success", "info", "progress", "warning"] as const)(
    "never renders type %s as an error alert",
    (type) => {
      const { getByText } = render(<ChatStatusMessage status={statusFor(type)} />)
      const region = getByText("Status message.")
      expect(region.getAttribute("role")).not.toBe("alert")
      expect(region.getAttribute("aria-live")).toBe("polite")
      expect(region.className).not.toContain("bg-danger-subtle")
      expect(region.className).not.toContain("text-danger")
    }
  )

  it("reserves role=alert and assertive announcement for genuine errors only", () => {
    render(<ChatStatusMessage status={statusFor("error", "Run failed.")} />)
    const alert = screen.getByRole("alert")
    expect(alert.textContent).toContain("Run failed.")
    expect(alert.getAttribute("aria-live")).toBe("assertive")
  })

  it("uses polite non-urgent semantics for success messages", () => {
    render(<ChatStatusMessage status={statusFor("success", "3 files ready.")} />)
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite")
  })

  it("uses polite non-urgent semantics for informational messages", () => {
    render(
      <ChatStatusMessage status={statusFor("info", "Please acknowledge the privacy notice.")} />
    )
    expect(screen.getByRole("status").getAttribute("aria-live")).toBe("polite")
  })

  it("updates presentation and announcement semantics when the type changes", () => {
    const { rerender } = render(
      <ChatStatusMessage status={statusFor("progress", "Checking capacity…")} />
    )
    let region = screen.getByText("Checking capacity…")
    expect(attributes(region).role).toBe("status")
    expect(region.className).toContain("bg-brand/10")

    rerender(<ChatStatusMessage status={statusFor("error", "Run failed.")} />)
    region = screen.getByText("Run failed.")
    expect(attributes(region).role).toBe("alert")
    expect(region.getAttribute("aria-live")).toBe("assertive")
    expect(region.className).toContain("bg-danger-subtle")
    expect(region.className).toContain("text-danger")
  })

  it("handles a missing/invalid type safely as neutral info, never as an error", () => {
    render(<ChatStatusMessage status={statusFor("info", "hello")} />)
    expect(screen.getByText("hello").getAttribute("role")).toBe("status")
    expect(screen.getByText("hello").getAttribute("aria-live")).toBe("polite")
    expect(screen.getByText("hello").className).not.toContain("bg-danger-subtle")
  })
})
