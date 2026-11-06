// Assembly — Desktop IPC contract.
//
// This file mirrors the Rust IPC types in `desktop/src-tauri/src/{lib,sidecar,keyring}.rs`.
// Keep the two in sync: adding/removing/renaming a command or field requires
// updating both sides. The Rust side is the source of truth for command
// names and error codes; this file is the TypeScript mirror consumed by the
// desktop webview.

/** Backend state machine, mirrors `BackendState` in Rust. */
export type BackendState =
  | { type: "Starting" }
  | { type: "Ready"; port: number; token: string }
  | { type: "Failed"; reason: string }
  | { type: "Crashed"; code: number | null }
  | { type: "Stopping" }
  | { type: "Stopped" };

/** Serialized supervisor snapshot, mirrors `BackendStatus` in Rust. */
export interface BackendStatus {
  state: BackendState;
  restarts: number;
  pid: number | null;
  endpoint: string | null;
}

/** Base URL + per-launch auth token, mirrors `BackendEndpoint` in Rust. */
export interface BackendEndpoint {
  url: string;
  token: string;
}

export type LogStream = "Stdout" | "Stderr";

/** One redacted log line, mirrors `LogLine` in Rust. */
export interface LogLine {
  stream: LogStream;
  line: string;
}

/** Typed IPC error, mirrors `CommandError` in Rust. Never a raw string. */
export interface CommandError {
  code: string;
  message: string;
}

/** Allowed provider names — allowlist for keyring and validation. Must match
 * the provider ids accepted by the backend catalog / keyring. */
export type ProviderName =
  | "gemini"
  | "groq"
  | "cerebras"
  | "openrouter"
  | "huggingface";

export const PROVIDER_NAMES: ProviderName[] = [
  "gemini",
  "groq",
  "cerebras",
  "openrouter",
  "huggingface",
];

export function isProviderName(value: unknown): value is ProviderName {
  return typeof value === "string" && PROVIDER_NAMES.includes(value as ProviderName);
}

/** Maximum length for a provider key value (defense against huge inputs). */
export const MAX_KEY_LENGTH = 4096;

/** Minimum length for a provider key (rejects empty/placeholder values). */
export const MIN_KEY_LENGTH = 10;

/** Validate a provider key string before sending to IPC. */
export function validateProviderKey(key: unknown): { ok: true; value: string } | { ok: false; error: string } {
  if (typeof key !== "string") {
    return { ok: false, error: "key must be a string" };
  }
  const trimmed = key.replace(/\s+/g, "").trim();
  if (trimmed.length < MIN_KEY_LENGTH) {
    return { ok: false, error: "key is too short" };
  }
  if (trimmed.length > MAX_KEY_LENGTH) {
    return { ok: false, error: "key is too long" };
  }
  return { ok: true, value: trimmed };
}

import { invoke } from "@tauri-apps/api/core";

/** Desktop detection: true when running inside the Tauri webview. */
export function isDesktop(): boolean {
  return typeof window !== "undefined" && !!(window as unknown as { __TAURI__?: unknown }).__TAURI__;
}

/** Thin adapter over Tauri `invoke`. Desktop-only; off-desktop callers should
 * check `isDesktop()` first and use the web API client instead. */
export class DesktopIpc {
  private async command<T = unknown>(name: string, args?: Record<string, unknown>): Promise<T> {
    if (typeof invoke !== "function") {
      throw new Error("Tauri invoke is unavailable (not running in desktop mode)");
    }
    return invoke(name, args);
  }

  async startBackend(): Promise<BackendStatus> {
    return this.command("start_backend");
  }
  async backendStatus(): Promise<BackendStatus> {
    return this.command("get_backend_status");
  }
  async backendEndpoint(): Promise<BackendEndpoint> {
    return this.command("get_backend_endpoint");
  }
  async restartBackend(): Promise<BackendStatus> {
    return this.command("restart_backend");
  }
  async stopBackend(): Promise<BackendStatus> {
    return this.command("stop_backend");
  }
  async backendLogs(): Promise<LogLine[]> {
    return this.command("get_backend_logs");
  }

  async saveProviderKey(provider: string, key: string): Promise<void> {
    if (!isProviderName(provider)) {
      throw new Error(`unknown provider: ${provider}`);
    }
    return this.command("save_provider_key", { provider, key });
  }
  async hasProviderKey(provider: string): Promise<boolean> {
    if (!isProviderName(provider)) {
      throw new Error(`unknown provider: ${provider}`);
    }
    return this.command("has_provider_key", { provider });
  }
  async deleteProviderKey(provider: string): Promise<void> {
    if (!isProviderName(provider)) {
      throw new Error(`unknown provider: ${provider}`);
    }
    return this.command("delete_provider_key", { provider });
  }
  async readProviderKey(provider: string): Promise<string | null> {
    if (!isProviderName(provider)) {
      throw new Error(`unknown provider: ${provider}`);
    }
    return this.command("read_provider_key", { provider });
  }
}

export const desktopIpc = new DesktopIpc();
