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
  roles_ready: string[];
  reasons: string[];
}

function suggestFix(ready: string[]): string {
  const fallback = ["gemini", "mistral"].filter((f) => !ready.includes(f));
  const hint = fallback.slice(0, 2).join(" or ") || "another provider";
  return `Add a ${hint} key to reach 3 families.`;
}

export function evaluateGate(
  families: string[],
  providersCount: number,
  rolesReady: string[] = ["solver", "critic"],
): DiversityGate {
  const ready = [...new Set(families)].sort();
  const roles = [...new Set(rolesReady)].sort();
  const count = ready.length;
  const missingRoles = ["solver", "critic"].filter((role) => !roles.includes(role));
  const base = {
    families_ready: ready,
    families_count: count,
    providers_count: providersCount,
    roles_ready: roles,
  };
  if (missingRoles.length > 0) {
    return {
      ...base,
      level: "BLOCKED",
      reasons: [
        `No usable ${missingRoles.join(" or ")} model is ready. Check saved API keys, verified quota limits, and model selection.`,
      ],
    };
  }
  if (count >= FAMILY_GATE_THRESHOLDS.ok) {
    return { ...base, level: "OK", reasons: [`${count} distinct solver/critic families ready: ${ready.join(", ")}.`] };
  }
  if (count === FAMILY_GATE_THRESHOLDS.warn) {
    return {
      ...base,
      level: "WARN",
      reasons: [
        `Only ${count} distinct solver/critic families ready (${ready.join(", ")}): independent reasoning is weakened. ${suggestFix(ready)}`,
      ],
    };
  }
  return {
    ...base,
    level: "BLOCKED",
    reasons: [
      count === 1
        ? `Only 1 distinct solver/critic family is ready (${ready.join(", ")}). Assembly requires at least 2 distinct usable families to run. ${suggestFix(ready)}`
        : "No usable solver/critic model families are ready. Add valid keys for providers with verified quota limits, then try again.",
    ],
  };
}

export function gateChipText(gate: DiversityGate): string {
  const readyFamilies = gate.families_ready.length
    ? `: ${gate.families_ready.join(", ")}`
    : ""
  return `${gate.families_count} families ready${readyFamilies}`
}
