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

  it("web mode explains HTTPS transit, readable browser storage and hosting logs", () => {
    render(<PrivacyDialog mode="web" providers={[]} onAcknowledge={() => {}} />)
    expect(document.body.textContent).toContain("hosted Assembly backend over HTTPS")
    expect(document.body.textContent).toContain("all saved model-provider keys")
    expect(document.body.textContent).toContain("only the provider key being tested")
    expect(document.body.textContent).toContain("any saved Tavily key")
    expect(document.body.textContent).toContain("even when search is not used")
    expect(document.body.textContent).toContain("not encrypted at rest")
    expect(document.body.textContent).toContain("same-origin JavaScript")
    expect(document.body.textContent).toContain("Hosting providers may process network traffic")
    expect(document.body.textContent).not.toContain("Windows Credential Manager")
  })

  it("desktop mode describes local WebView storage and loopback requests", () => {
    render(<PrivacyDialog mode="desktop" providers={[]} onAcknowledge={() => {}} />)
    expect(document.body.textContent).toContain("WebView browser profile")
    expect(document.body.textContent).toContain("over loopback")
    expect(document.body.textContent).toContain("all saved model-provider keys")
    expect(document.body.textContent).toContain("only the provider key being tested")
    expect(document.body.textContent).toContain("any saved Tavily key")
    expect(document.body.textContent).toContain("even when search is not used")
    expect(document.body.textContent).toContain("not encrypted at rest")
    expect(document.body.textContent).toContain("XSS incident")
    expect(document.body.textContent).toContain("Windows Credential Manager adapter")
    expect(document.body.textContent).not.toContain("hosted Assembly backend over HTTPS")
  })
})
