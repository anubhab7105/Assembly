/**
 * Privacy notice — single source of truth for the consent dialog text.
 *
 * Both the blocking first-run dialog (privacy-dialog.tsx) and the Settings
 * Privacy section (privacy-section.tsx) import these strings; docs/privacy.md
 * carries the same wording. Do not duplicate the text elsewhere.
 */

export const PRIVACY_NOTICE_VERSION = 2;

export const PRIVACY_ACK_KEY = "privacy_notice_ack";

export const GENERIC_PROVIDER_NOTE =
  "Check this provider's terms for how free-tier inputs are handled.";

export interface EnabledProviderNote {
  id: string;
  privacy_note?: string | null;
}

/** Web-mode dialog paragraphs (a)–(g), in order. */
export const WEB_PRIVACY_PARAGRAPHS: string[] = [
  "Assembly web mode sends your question, API keys and model choices to the Assembly backend over HTTPS. The backend uses submitted API keys only for the key-test or run request and does not persist them.",
  "Saved web API keys stay in this browser across refreshes. They are stored in IndexedDB with a localStorage fallback until you remove them in Settings or clear browser/site data. Browser storage is not an OS-protected credential vault; protect access to your browser profile and device.",
  "Server logs contain metadata only (run id, tier, timings, counts). Never your questions, answers or keys.",
  "Your history and settings stay in this browser (IndexedDB). Nothing is stored on the server.",
  "Each model provider handles your inputs under its own policy:",
  "Avoid sending sensitive or confidential information.",
  "The desktop app keeps keys in the Windows Credential Manager and sends requests straight from your PC. Keys never leave your machine except to authenticate with the provider.",
];

/** Desktop-mode dialog paragraphs (shorter, no server wording). */
export const DESKTOP_PRIVACY_PARAGRAPHS: string[] = [
  "Assembly desktop mode runs entirely on your PC.",
  "Your history and settings stay in this browser (IndexedDB).",
  "Each model provider handles your inputs under its own policy:",
  "Avoid sending sensitive or confidential information.",
  "Keys are kept in the Windows Credential Manager and requests go straight from your PC. Keys never leave your machine except to authenticate with the provider.",
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
