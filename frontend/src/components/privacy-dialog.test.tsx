import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { PrivacyDialog } from "./privacy-dialog"

describe("PrivacyDialog", () => {
  it("exposes a labelled modal dialog and requires explicit consent", () => {
    const onAck = vi.fn()
    render(<PrivacyDialog mode="web" providers={[{ id: "groq" }]} onAcknowledge={onAck} />)

    const dialog = screen.getByRole("dialog", { name: "Privacy notice" })
    expect(dialog.getAttribute("aria-modal")).toBe("true")
    expect(dialog.getAttribute("aria-describedby")).toBe("privacy-dialog-description")
    expect(document.getElementById("privacy-dialog-description")).not.toBeNull()
    expect(screen.getByTestId("privacy-acknowledge")).toHaveProperty("disabled", true)

    fireEvent.click(screen.getByLabelText(/my question is sent/i))
    fireEvent.click(screen.getByTestId("privacy-acknowledge"))
    expect(onAck).toHaveBeenCalledTimes(1)
  })

  it("shows provider notes only for enabled providers", () => {
    const geminiNote =
      "Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information."
    const { unmount } = render(
      <PrivacyDialog mode="web" providers={[{ id: "gemini", privacy_note: geminiNote }]} onAcknowledge={() => {}} />,
    )
    expect(screen.getByTestId("provider-note-gemini").textContent).toContain("Google")

    unmount()
    render(<PrivacyDialog mode="web" providers={[{ id: "groq" }]} onAcknowledge={() => {}} />)
    expect(screen.queryByTestId("provider-note-gemini")).toBeNull()
    expect(screen.getByTestId("provider-note-groq").textContent).toContain("Check this provider")
  })

  it("desktop mode omits server wording", () => {
    render(<PrivacyDialog mode="desktop" providers={[]} onAcknowledge={() => {}} />)
    expect(document.body.textContent).not.toContain("stores nothing on the server")
  })
})
