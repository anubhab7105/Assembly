/**
 * Family-diversity gate — frontend mirror of the backend gate
 * (`src/providers/router.py`: FAMILY_GATE_THRESHOLDS, DiversityGate).
 *
 * The backend remains authoritative (status / preflight / run.started);
 * this module renders the same levels from browser-known keys + catalog
 * so the chip updates instantly without a round-trip.
 */

export const FAMILY_GATE_THRESHOLDS = { ok: 3, warn: 2 } as const;

export type GateLevel = "OK" | "WARN" | "BLOCKED";

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
  return {
    level: "BLOCKED",
    families_ready: ready,
    families_count: count,
    providers_count: providersCount,
    reasons: [
      count === 1
        ? `Only 1 distinct model family ready (${ready.join(", ")}). Assembly requires at least 2 independent model families to run. ${suggestFix(ready)}`
        : "No model families ready. Add valid keys for providers with at least 2 distinct usable model families, then try again.",
    ],
  };
}

export function gateChipText(gate: DiversityGate): string {
  if (gate.level === "BLOCKED") return `${gate.families_count} families ready`;
  return `${gate.families_count} families ready: ${gate.families_ready.join(", ")}`;
}
