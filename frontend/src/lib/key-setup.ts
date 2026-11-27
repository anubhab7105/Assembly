/**
 * Key-setup helpers (FR-30): fallback text, prefix hints, why-lines.
 * No provider-specific signup facts are invented here; unknown values
 * render the shared fallback.
 */

export const SENSITIVE_SIGNUP_FALLBACK =
  "Check this during signup; if it asks for payment, skip this provider (Assembly is free-tier only)";

export const MIN_FAMILIES_TO_START = 2;
export const RECOMMENDED_FAMILIES = 3;

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
    groq: "Keys usually start with gsk_. Paste the full value.",
    gemini: "Keys usually start with AIza. Paste the full value.",
    openrouter: "Keys usually start with sk-or-. Paste the full value.",
    mistral: "Paste the API key from your Mistral console.",
    cerebras: "Keys usually start with csk-. Paste the full value.",
    huggingface: "Keys usually start with hf_. Paste the full value.",
    nvidia: "Keys usually start with nvapi-. Paste the full value.",
  };
  return hints[providerId] ?? "Paste the full key value as shown by the provider.";
}

/** Prefix hint never blocks saving: always true by design. */
export function isKeyFormatOk(providerId: string, key: string): boolean {
  // Prefix hints intentionally never block saving a provider key.
  void providerId;
  void key;
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
    return `Minimum to start: met (${readyFamilies} families). Three families are recommended. Recommended order: ${order}.`;
  }
  return `Minimum to start: add keys for at least 2 distinct solver/critic model families. Three families are recommended. Recommended order: ${order}.`;
}

/**
 * Detect provider ID from key prefix.
 */
export function detectProviderByPrefix(key: string): string | null {
  const clean = key.trim();
  if (clean.startsWith("AIza")) return "gemini";
  if (clean.startsWith("gsk_") || clean.startsWith("gsk-")) return "groq";
  if (clean.startsWith("csk-") || clean.startsWith("csk_")) return "cerebras";
  if (clean.startsWith("sk-or-") || clean.startsWith("sk-or_")) return "openrouter";
  if (clean.startsWith("hf_")) return "huggingface";
  if (clean.startsWith("nvapi-")) return "nvidia";
  if (clean.startsWith("tvly-") || clean.startsWith("tvly_")) return "tavily";
  return null;
}
