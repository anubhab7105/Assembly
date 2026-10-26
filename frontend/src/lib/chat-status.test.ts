import { describe, expect, it } from "vitest"
import {
  chatStatusAriaLive,
  chatStatusClass,
  chatStatusRole,
  makeChatStatus,
  safeChatStatus,
  type ChatStatusType,
} from "./chat-status"

describe("chat-status semantic model", () => {
  it.each([
    ["info", "border-info/30 bg-info-subtle text-info", "status", "polite"],
    ["progress", "border-brand/30 bg-brand/10 text-brand", "status", "polite"],
    ["success", "border-success/30 bg-success-subtle text-success", "status", "polite"],
    ["warning", "border-warning/30 bg-warning-subtle text-warning", "status", "polite"],
    ["error", "border-danger/40 bg-danger-subtle text-danger", "alert", "assertive"],
  ])("maps type %s to presentation and ARIA semantics", (type, cls, role, live) => {
    expect(chatStatusClass(type as ChatStatusType)).toContain(cls.split(" ")[0])
    expect(chatStatusRole(type as ChatStatusType)).toBe(role)
    expect(chatStatusAriaLive(type as ChatStatusType)).toBe(live)
  })

  it("keeps text separate from semantic type", () => {
    const status = makeChatStatus("Files ready.", "success")
    expect(status.type).toBe("success")
    expect(status.text).toBe("Files ready.")
  })

  it("defaults a missing type to info (safe, never error)", () => {
    expect(makeChatStatus("hello").type).toBe("info")
    expect(makeChatStatus("hello", undefined).type).toBe("info")
  })

  it("treats missing/invalid status as info, never error", () => {
    expect(safeChatStatus("anything").type).toBe("info")
    expect(safeChatStatus("anything").text).toBe("anything")
    expect(chatStatusRole("error")).toBe("alert")
    expect(chatStatusRole("info")).toBe("status")
    expect(chatStatusAriaLive("error")).toBe("assertive")
    expect(chatStatusAriaLive("info")).toBe("polite")
  })

  it("does not classify success/info/progress/warning as alerts", () => {
    for (const type of ["info", "progress", "success", "warning"] as ChatStatusType[]) {
      expect(chatStatusRole(type)).not.toBe("alert")
      expect(chatStatusAriaLive(type)).toBe("polite")
      expect(chatStatusClass(type)).not.toContain("bg-danger-subtle")
      expect(chatStatusClass(type)).not.toContain("text-danger")
    }
  })
})
