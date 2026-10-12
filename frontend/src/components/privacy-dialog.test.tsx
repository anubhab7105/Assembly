import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PrivacyDialog } from "./privacy-dialog";

describe("PrivacyDialog", () => {
  it("blocks with an explicit consent checkbox before I understand", () => {
    const onAck = vi.fn();
    render(<PrivacyDialog mode="web" providers={[{ id: "groq" }]} onAcknowledge={onAck} />);
    expect(screen.getByTestId("privacy-dialog")).toBeDefined();
    // Button stays disabled until the consent box is ticked.
    expect(screen.getByTestId("privacy-acknowledge")).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByLabelText(/my question is sent/i));
    fireEvent.click(screen.getByTestId("privacy-acknowledge"));
    expect(onAck).toHaveBeenCalledTimes(1);
  });

  it("shows the gemini note only when gemini is enabled", () => {
    const geminiNote =
      "Free-tier requests may be used by Google to improve its products. Avoid sending sensitive or confidential information.";
    const { unmount } = render(
      <PrivacyDialog mode="web" providers={[{ id: "gemini", privacy_note: geminiNote }]} onAcknowledge={() => {}} />,
    );
    expect(screen.getByTestId("provider-note-gemini").textContent).toContain("Google");
    unmount();
    render(<PrivacyDialog mode="web" providers={[{ id: "groq" }]} onAcknowledge={() => {}} />);
    expect(screen.queryByTestId("provider-note-gemini")).toBeNull();
    expect(screen.getByTestId("provider-note-groq").textContent).toContain("Check this provider");
  });

  it("desktop mode omits server wording", () => {
    render(<PrivacyDialog mode="desktop" providers={[]} onAcknowledge={() => {}} />);
    expect(document.body.textContent).not.toContain("stores nothing on the server");
  });
});
