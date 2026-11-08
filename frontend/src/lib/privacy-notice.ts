/**
 * Privacy notice — single source of truth for the consent dialog text.
 *
 * Both the blocking first-run dialog (privacy-dialog.tsx) and the Settings
 * Privacy section (privacy-section.tsx) import these strings; docs/privacy.md
 * carries the same wording. Do not duplicate the text elsewhere.
 */

export const PRIVACY_NOTICE_VERSION = 3;

export const PRIVACY_ACK_KEY = "privacy_notice_ack";

export const GENERIC_PROVIDER_NOTE =
  "Check this provider's terms for how free-tier inputs are handled.";

export interface EnabledProviderNote {
  id: string;
  privacy_note?: string | null;
}

/** Web-mode dialog paragraphs (a)–(g), in order. */
export const WEB_PRIVACY_PARAGRAPHS: string[] = [
  "Assembly web mode sends your question, API keys and model choices to the hosted Assembly backend over HTTPS (localhost is used for local development). Submitted API keys are used for preflight, key-test or run requests and are not persisted by the Assembly application.",
  "Saved web API keys stay in this browser across refreshes. They are stored as readable values (not encrypted at rest) in IndexedDB with a localStorage fallback until you remove them in Settings or clear browser/site data. Browser storage is not an OS-protected credential vault; same-origin JavaScript, including code injected through an XSS vulnerability, can read saved keys.",
  "The Assembly application processes active request/run data in memory and does not write submitted web keys, questions or answers to its application database or disk. Its application logs record operational metadata (run id, tier, timings, counts and search-query lengths), not raw request bodies, search-query text or key values. Hosting providers may process network traffic and keep their own operational logs under their policies.",
  "Your run history and settings stay in this browser (IndexedDB, with the documented localStorage fallback). The hosted application does not persist web run content or submitted API keys.",
  "Each model provider handles your inputs under its own policy:",
  "Avoid sending sensitive or confidential information.",
];

/** Desktop-mode dialog paragraphs (shorter, no server wording). */
export const DESKTOP_PRIVACY_PARAGRAPHS: string[] = [
  "Desktop mode uses an Assembly backend running locally on your PC. Its requests do not pass through the hosted Assembly web backend.",
  "Desktop run history is stored locally in SQLite. UI settings and the current Settings key vault use the embedded WebView browser storage. Saved keys are readable values, not encrypted at rest; same-origin JavaScript, including injected code in an XSS incident, can read them.",
  "Each model provider handles your inputs under its own policy:",
  "Avoid sending sensitive or confidential information.",
  "The current Settings flow stores keys as readable values in the WebView browser profile (IndexedDB with a localStorage fallback; not encrypted at rest). Preflight, key tests and runs send them to the local backend over loopback, and that backend makes provider requests. The repository has a Windows Credential Manager adapter, but the current Settings save flow does not use it as the primary key store.",
];

export function providerNoteFor(provider: EnabledProviderNote): string {
  return provider.privacy_note || GENERIC_PROVIDER_NOTE;
}

export interface PrivacyAck {
  version: number;
  acknowledged_at: string;
}

export function needsAck(stored: PrivacyAck | null): boolean {
  if (!stored) return true;
  return stored.version !== PRIVACY_NOTICE_VERSION;
}

export function buildAck(): PrivacyAck {
  return {
    version: PRIVACY_NOTICE_VERSION,
    acknowledged_at: new Date().toISOString(),
  };
}
