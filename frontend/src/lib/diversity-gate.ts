/**
 * Family-diversity gate — frontend mirror of the backend gate
 * (`src/providers/router.py`: FAMILY_GATE_THRESHOLDS, DiversityGate).
 *
 * The backend remains authoritative (status / preflight / run.started);
 * this module renders the same levels from browser-known keys + catalog
 * so the chip updates instantly without a round-trip.
 */

export const FAMILY_GATE_THRESHOLDS = { ok: 3, warn: 2 } as const;

export type GateLevel = "OK" | "WARN" | "DEGRADED" | "BLOCKED";

export interface DiversityGate {
  level: GateLevel;
  families_ready: string[];
  families_count: number;
  providers_count: number;
  reasons: string[];
}

function suggestFix(ready: string[]): string {
  const fallback = ["gemini", "mistral"].filter((f) => !ready.includes(f));
  const hint = fallback.slice(0, 2).join(" or ") || "another provider";
  return `Add a ${hint} key to reach 3 families.`;
}

export function evaluateGate(families: string[], providersCount: number): DiversityGate {
  const ready = [...new Set(families)].sort();
  const count = ready.length;
  if (count >= FAMILY_GATE_THRESHOLDS.ok) {
    return {
      level: "OK",
      families_ready: ready,
      families_count: count,
      providers_count: providersCount,
      reasons: [`${count} families ready: ${ready.join(", ")}.`],
    };
  }
  if (count === FAMILY_GATE_THRESHOLDS.warn) {
    return {
      level: "WARN",
      families_ready: ready,
      families_count: count,
      providers_count: providersCount,
      reasons: [
        `Only ${count} distinct model families ready (${ready.join(", ")}): independent reasoning is weakened. ${suggestFix(ready)}`,
      ],
    };
  }
  if (count === 1) {
    return {
      level: "DEGRADED",
      families_ready: ready,
      families_count: count,
      providers_count: providersCount,
      reasons: [
        `Only 1 model family ready (${ready.join(", ")}): agents cannot reason independently. Confirm to run anyway; the final answer will be labeled lower-confidence. ${suggestFix(ready)}`,
      ],
    };
  }
  return {
    level: "BLOCKED",
    families_ready: [],
    families_count: 0,
    providers_count: providersCount,
    reasons: [
      "No model families ready. Add keys for at least two providers covering 3 model families, then try again.",
    ],
  };
}

export function gateChipText(gate: DiversityGate): string {
  if (gate.level === "BLOCKED") return "0 families ready";
  return `${gate.families_count} families ready: ${gate.families_ready.join(", ")}`;
}
