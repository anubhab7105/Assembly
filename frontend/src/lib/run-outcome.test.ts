import { describe, it, expect } from "vitest";
import { failureMessage, isPresentableRun } from "./run-outcome";

describe("run-outcome guard", () => {
  it("presents only completed runs with a non-empty answer", () => {
    expect(isPresentableRun({ status: "completed", finalAnswer: "The team concludes 42." })).toBe(true);
    expect(isPresentableRun({ status: "completed", finalAnswer: "  " })).toBe(false);
    expect(isPresentableRun({ status: "completed", finalAnswer: "" })).toBe(false);
    expect(isPresentableRun({ status: "failed", finalAnswer: "The team concludes 42." })).toBe(false);
    expect(isPresentableRun({ status: "failed", finalAnswer: "" })).toBe(false);
    expect(isPresentableRun({ status: "unknown", finalAnswer: "" })).toBe(false);
    expect(isPresentableRun({ status: "cancelled", finalAnswer: "" })).toBe(false);
  });

  it("never lets an empty-answer failure look like an active run", () => {
    // The misleading screen was: save history + router.push to /executions
    // with status failed/unknown and answer "". The guard blocks navigation
    // for every such case, so the executions view never renders a blank
    // "forming team" screen for a settled failure.
    const failures = [
      { status: "failed", finalAnswer: "" },
      { status: "unknown", finalAnswer: "" },
      { status: "completed", finalAnswer: "" },
      { status: "cancelled", finalAnswer: "" },
    ];
    for (const f of failures) {
      expect(isPresentableRun(f)).toBe(false);
    }
  });

  it("builds an actionable failure message without secrets", () => {
    const msg = failureMessage({ status: "failed", stage: "planning", errorCode: "no_usable_models" });
    expect(msg).toContain("failed");
    expect(msg).toContain("planning");
    expect(msg).toContain("no_usable_models");
    expect(msg).toMatch(/keys|quota/i);
    expect(failureMessage({ status: "cancelled" })).toMatch(/cancelled/i);
  });
});
