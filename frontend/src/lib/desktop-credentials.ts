/**
 * Desktop credential bridge: provider secrets flow into Tauri IPC and land
 * in the OS keyring (Windows Credential Manager). They are never returned
 * to the webview and never written to browser storage.
 *
 * The `@tauri-apps/api` import is dynamic and only reached when
 * `env.NEXT_PUBLIC_APP_MODE === "desktop"` (i.e. inside Tauri), so the web
 * build is completely unaffected and never bundles or calls Tauri APIs.
 */

interface InvokeResult<T = unknown> {
  data?: T
}

async function tauriInvoke<T = unknown>(
  cmd: string,
  args: Record<string, unknown>,
): Promise<T> {
  // Dynamically imported so the web build never references Tauri APIs.
  const { invoke } = await import("@tauri-apps/api/core")
  return invoke<T>(cmd, args)
}

export interface CredentialSaveResponse {
  provider: string
}

export interface CredentialExistsResponse {
  provider: string
  exists: boolean
}

export interface CredentialListResponse {
  providers: string[]
}

/** Store a provider secret in the OS keyring (desktop only). */
export async function desktopCredentialSave(
  provider: string,
  secret: string,
): Promise<CredentialSaveResponse> {
  return tauriInvoke<CredentialSaveResponse>("credential_save", {
    provider,
    secret,
  })
}

/** Delete a provider secret from the OS keyring (desktop only). */
export async function desktopCredentialDelete(
  provider: string,
): Promise<void> {
  await tauriInvoke<void>("credential_delete", { provider })
}

/** List provider names that have a stored credential (names only). */
export async function desktopCredentialList(): Promise<CredentialListResponse> {
  return tauriInvoke<CredentialListResponse>("credential_list", {})
}

/** Check whether a credential exists for a provider (no value revealed). */
export async function desktopCredentialExists(
  provider: string,
): Promise<CredentialExistsResponse> {
  return tauriInvoke<CredentialExistsResponse>("credential_exists", {
    provider,
  })
}
