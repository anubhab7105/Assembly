/**
 * Key-setup helpers (FR-30): fallback text, prefix hints, why-lines.
 * No provider-specific signup facts are invented here; unknown values
 * render the shared fallback.
 */

export const SENSITIVE_SIGNUP_FALLBACK =
  "Check this during signup; if it asks for payment, skip this provider (Assembly is free-tier only)";

export const MIN_FAMILIES_TO_START = 3;

export function sensitiveSignupText(value: string | null | undefined): string {
  if (typeof value === "string" && value.trim().length > 0) return value;
  return SENSITIVE_SIGNUP_FALLBACK;
}

/**
 * Soft key-format hint (prefix only, never blocking). Returns a display
 * string; validation must never reject on its basis (see isKeyFormatOk).
 */
export function keyPrefixHint(providerId: string): string {
  const hints: Record<string, string> = {
    groq: "Keys usually start with gsk_ — paste the full value.",
    gemini: "Keys usually start with AIza — paste the full value.",
    openrouter: "Keys usually start with sk-or- — paste the full value.",
    huggingface: "Keys usually start with hf_ — paste the full value.",
  };
  return hints[providerId] ?? "Paste the full key value as shown by the provider.";
}

/** Prefix hint never blocks saving: always true by design. */
export function isKeyFormatOk(_providerId: string, _key: string): boolean {
  return true;
}

export interface WhyInput {
  id: string;
  models: { family: string; roles: string[] }[];
}

export function whyProviderLine(provider: WhyInput): string {
  const families = [...new Set(provider.models.map((m) => m.family))].sort();
  const roles = [...new Set(provider.models.flatMap((m) => m.roles))].sort();
  if (families.length === 0) return `Why this provider: ${provider.id} has no models listed.`;
  return `Why this provider: ${families.join(", ")} (${roles.join("/") || "general"} coverage).`;
}

export function minimumToStartBanner(
  readyFamilies: number,
  recommendedOrder: string[],
): string {
  const order = recommendedOrder.length > 0 ? recommendedOrder.join(" → ") : "catalog order";
  if (readyFamilies >= MIN_FAMILIES_TO_START) {
    return `Minimum to start: met (${readyFamilies} families). Recommended order: ${order}.`;
  }
  if (readyFamilies === 2) {
    return `Minimum to start: add keys for at least 3 model families (2 works with a warning). Recommended order: ${order}.`;
  }
  return `Minimum to start: add keys for at least 3 model families (2 works with a warning). Recommended order: ${order}.`;
}
