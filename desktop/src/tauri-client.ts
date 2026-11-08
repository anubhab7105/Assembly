/**
 * Thin client over Tauri IPC (`invoke`/`listen`) for the desktop shell.
 *
 * The types mirror the Rust `#[tauri::command]` contract in
 * `desktop/src-tauri/src/commands.rs`. All provider secrets flow one way:
 * into Rust (to the OS keyring); they are never echoed back.
 *
 * In web (non-Tauri) builds this module is never imported by the shared
 * frontend, so the web bundle is unaffected.
 */

import { invoke, listen } from "@tauri-apps/api/core"

export interface BackendStatusResponse {
  state: string // stopped | starting | ready | stopping | failed | crashed
  base_url: string | null
  token: string | null
  ready: boolean
}

export interface CredentialSaveRequest {
  provider: string
  secret: string
}

export interface CredentialSaveResponse {
  provider: string
}

export interface CredentialExistsResponse {
  provider: string
  exists: boolean
}

export interface CredentialDeleteResponse {
  provider: string
}

export interface CredentialListResponse {
  providers: string[]
}

export interface CommandError {
  code: string
  message: string
}

export class DesktopIpcError extends Error {
  public readonly code: string
  constructor(message: string, code: string) {
    super(message)
    this.name = "DesktopIpcError"
    this.code = code
  }
}

function toIpcError(e: unknown): DesktopIpcError {
  if (e instanceof DesktopIpcError) return e
  if (e && typeof e === "object" && "code" in e && "message" in e) {
    return new DesktopIpcError(String((e as { message: unknown }).message), String((e as { code: unknown }).code))
  }
  return new DesktopIpcError(String(e ?? "IPC error"), "unknown")
}

// ────────────────────────────────────────────────────────────
// Commands
// ────────────────────────────────────────────────────────────

export async function backendStatus(): Promise<BackendStatusResponse> {
  return invoke<BackendStatusResponse>("backend_status")
}

export async function backendRestart(): Promise<void> {
  return invoke<void>("backend_restart")
}

export async function credentialSave(
  provider: string,
  secret: string,
): Promise<CredentialSaveResponse> {
  return invoke<CredentialSaveResponse>("credential_save", { provider, secret })
}

export async function credentialExists(
  provider: string,
): Promise<CredentialExistsResponse> {
  return invoke<CredentialExistsResponse>("credential_exists", { provider })
}

export async function credentialDelete(provider: string): Promise<CredentialDeleteResponse> {
  return invoke<CredentialDeleteResponse>("credential_delete", { provider })
}

export async function credentialList(): Promise<CredentialListResponse> {
  return invoke<CredentialListResponse>("credential_list")
}

// ────────────────────────────────────────────────────────────
// Events (payloads match Rust `serde_json::json!` emissions)
// ────────────────────────────────────────────────────────────

export const EVENT_BACKEND_READY = "backend://ready"
export const EVENT_BACKEND_CRASHED = "backend://crashed"
export const EVENT_BACKEND_FAILED = "backend://failed"
export const EVENT_BACKEND_STOPPED = "backend://stopped"

export interface BackendReadyPayload { base_url: string }
export interface BackendCrashedPayload { exit_code: number | null }
export interface BackendFailedPayload { reason: string }

type Unsubscribe = () => Promise<void>

export function onBackendReady(handler: (p: BackendReadyPayload) => void): Promise<Unsubscribe> {
  return listen<EVENT_BACKEND_READY_PAYLOAD>(EVENT_BACKEND_READY, (event) => handler(event.payload))
}

export function onBackendCrashed(handler: (p: BackendCrashedPayload) => void): Promise<Unsubscribe> {
  return listen(EVENT_BACKEND_CRASHED, (event) => handler(event.payload))
}

export function onBackendFailed(handler: (p: BackendFailedPayload) => void): Promise<Unsubscribe> {
  return listen(EVENT_BACKEND_FAILED, (event) => handler(event.payload))
}

export function onBackendStopped(handler: () => void): Promise<Unsubscribe> {
  return listen(EVENT_BACKEND_STOPPED, () => handler())
}

// ────────────────────────────────────────────────────────────
// Platform detection
// ────────────────────────────────────────────────────────────

/** True when running inside the Tauri desktop shell. */
export function isTauri(): boolean {
  return (
    typeof window !== "undefined" &&
    !!(window as unknown as Record<string, unknown>)["__TAURI__"]
  )
}

type EVENT_BACKEND_READY_PAYLOAD = BackendReadyPayload
