import { describe, it, expect } from "vitest";
import { evaluateGate, gateChipText, FAMILY_GATE_THRESHOLDS } from "./diversity-gate";

describe("diversity-gate chip states", () => {
  it("groq + openrouter gives 4 families and OK", () => {
    const gate = evaluateGate(["gpt-oss", "qwen", "gemma", "nemotron"], 2);
    expect(gate.level).toBe("OK");
    expect(gate.families_count).toBe(4);
    expect(gateChipText(gate)).toBe("4 families ready: gemma, gpt-oss, nemotron, qwen");
  });

  it("2 families gives WARN with a fix hint", () => {
    const gate = evaluateGate(["gpt-oss", "qwen"], 2);
    expect(gate.level).toBe("WARN");
    expect(gateChipText(gate)).toContain("2 families ready");
    expect(gate.reasons[0]).toContain("to reach 3 families");
  });

  it("1 family is blocked because independent reasoning needs 2 families", () => {
    const gate = evaluateGate(["llama"], 2);
    expect(gate.level).toBe("BLOCKED");
    expect(gate.families_count).toBe(1);
    expect(gateChipText(gate)).toBe("1 families ready: llama");
    expect(gate.reasons[0]).toContain("at least 2 independent model families");
  });

  it("0 families gives BLOCKED", () => {
    const gate = evaluateGate([], 0);
    expect(gate.level).toBe("BLOCKED");
    expect(gateChipText(gate)).toBe("0 families ready");
  });

  it("thresholds live in one constant", () => {
    expect(FAMILY_GATE_THRESHOLDS).toEqual({ ok: 3, warn: 2 });
  });

  it("same family twice counts once and remains blocked", () => {
    const gate = evaluateGate(["llama", "llama"], 2);
    expect(gate.level).toBe("BLOCKED");
    expect(gate.families_count).toBe(1);
  });

  it("blocks when a core role has no usable model", () => {
    const gate = evaluateGate(["llama", "qwen"], 2, ["solver"]);
    expect(gate.level).toBe("BLOCKED");
    expect(gate.roles_ready).toEqual(["solver"]);
    expect(gate.reasons[0]).toContain("critic");
  });
});
