import { describe, expect, it, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { FinalAnswer } from "./final-answer"
import type { ExecutionState } from "@/hooks/use-execution"

vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}))

function makeState(confidence: ExecutionState["confidence"]): ExecutionState {
  return {
    status: "completed",
    connectionState: "connected",
    team: [],
    consensusScore: 0.9,
    consensusHistory: [],
    disagreements: [],
    sources: [],
    timerSeconds: null,
    finalAnswer: "The answer is available.",
    confidence,
    uncertaintyNote: null,
    question: "What is the answer?",
    attachments: [],
    round: 1,
    degradedMode: false,
    quotaWarning: null,
    feed: [],
    summary: null,
  }
}

describe("FinalAnswer confidence display", () => {
  it.each([
    { confidence: "High" as const, expectedClass: "bg-success/20" },
    { confidence: "Moderate" as const, expectedClass: "bg-warning/20" },
    { confidence: "Low" as const, expectedClass: "bg-danger/20" },
  ])("renders an explicitly assessed $confidence confidence", ({ confidence, expectedClass }) => {
    render(<FinalAnswer state={makeState(confidence)} />)

    const label = screen.getByTestId("confidence-label")
    expect(label.textContent).toContain(`Confidence: ${confidence}`)
    expect(label.getAttribute("data-confidence")).toBe(confidence)
    expect(label.className).toContain(expectedClass)
    expect(label.getAttribute("aria-label")).toContain(`Confidence assessment: ${confidence}`)
  })

  it("renders missing confidence as a neutral, accessible Not assessed state", () => {
    render(<FinalAnswer state={makeState(null)} />)

    const label = screen.getByTestId("confidence-label")
    expect(label.textContent).toContain("Confidence: Not assessed")
    expect(label.getAttribute("data-confidence")).toBe("unknown")
    expect(label.className).toContain("text-muted-foreground")
    expect(label.className).toContain("border-border")
    expect(label.className).not.toContain("bg-success/20")
    expect(label.getAttribute("aria-label")).toContain("Confidence assessment: Not assessed")
    expect(label.getAttribute("aria-expanded")).toBe("false")

    fireEvent.click(label)
    expect(label.getAttribute("aria-expanded")).toBe("true")
    expect(screen.getByText("Team Size")).toBeDefined()
  })
})
