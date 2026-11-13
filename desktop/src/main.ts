/**
 * Desktop boot client.
 *
 * The Tauri shell (Rust) now starts and supervises the backend sidecar; this
 * script only waits for the readiness signal, exposes the backend base URL
 * and auth token to the page (`window.ASSEMBLY_*`), and wires up runtime
 * crash/shutdown events. It runs only on the boot page (`index.html`); the
 * application page detects that the environment is already set and does not
 * re-boot.
 *
 * This keeps the web build unaffected: `isTauri()` is false outside Tauri.
 */

import {
  backendStatus,
  backendRestart,
  isTauri,
  onBackendCrashed,
  onBackendFailed,
  onBackendReady,
  onBackendStopped,
} from "./tauri-client"

const BOOT_EL = "status"
const POLL_INTERVAL_MS = 250
const POLL_MAX_ATTEMPTS = 120 // ~30 s total readiness budget

function el(id: string): HTMLElement | null {
  return document.getElementById(id)
}

function show(id: string, visible: boolean) {
  const e = el(id)
  if (e) e.style.display = visible ? "" : "none"
}

function setStatus(text: string) {
  const e = el("status")
  if (e) e.textContent = text
}

function setError(text: string) {
  const e = el("error")
  if (e) {
    e.textContent = text
    e.style.display = ""
  }
  show("loader", false)
  show("status", false)
}

async function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/** Poll `backend_status` until Ready, with a bounded timeout. */
async function waitForReady(): Promise<{ baseUrl: string; token: string } | null> {
  let attempts = 0
  while (attempts < POLL_MAX_ATTEMPTS) {
    try {
      const st = await backendStatus()
      if (st.ready && st.base_url && st.token) {
        return { baseUrl: st.base_url, token: st.token }
      }
    } catch {
      // Backend not up yet; keep polling.
    }
    attempts++
    await sleep(POLL_INTERVAL_MS)
  }
  return null
}

function exposeEnv(baseUrl: string, token: string): void {
  // Held in memory for this session only; never written to storage.
  ;(window as unknown as Record<string, string>).ASSEMBLY_API_URL = baseUrl
  ;(window as unknown as Record<string, string>).ASSEMBLY_TOKEN = token
  ;(window as unknown as Record<string, string>).ASSEMBLY_APP_MODE = "desktop"
}

async function boot(): Promise<void> {
  show("loader", true)
  show("error", false)
  show("status", true)
  setStatus("Starting backend sidecar...")

  const ready = await waitForReady()
  if (!ready) {
    setError(
      "Backend did not become ready in time. Click Retry to attempt starting it again.",
    )
    return
  }

  exposeEnv(ready.baseUrl, ready.token)
  setStatus("Backend ready. Loading application...")
  await sleep(300)
  // The application page reads window.ASSEMBLY_* (set above) and persists in
  // the same tab, so no credentials travel in the URL.
  window.location.href = "/frontend/index.html"
}

async function handleRetry(): Promise<void> {
  const btn = el("retry")
  if (btn) btn.style.display = "none"
  try {
    await backendRestart()
  } catch {
    // Ignore; the readiness poll below will surface the real state.
  }
  setStatus("Restarting backend sidecar...")
  const ready = await waitForReady()
  if (!ready) {
    setError("Backend still did not become ready. Try again later.")
    return
  }
  exposeEnv(ready.baseUrl, ready.token)
  setStatus("Backend ready. Loading application...")
  await sleep(300)
  window.location.href = "/frontend/index.html"
}

// Only the boot page runs this logic. The application page (which also loads
// main.ts) skips it and uses the already-exposed environment.
if (!el(BOOT_EL)) {
  // Application page: nothing to do; the boot page already exposed the
  // environment and navigated here.
  ;(window as unknown as Record<string, string>).ASSEMBLY_APP_MODE = "desktop"
} else if (isTauri()) {
  // Wire runtime events so a crash/shutdown mid-session is visible.
  const retryBtn = el("retry")
  onBackendReady(({ base_url }) => {
    setStatus(`Backend ready on ${base_url}.`)
  })
  onBackendCrashed(({ exit_code }) => {
    show("loader", false)
    show("status", false)
    setError(`Backend crashed (exit ${exit_code ?? "unknown"}).`)
  })
  onBackendFailed(({ reason }) => {
    show("loader", false)
    show("status", false)
    setError(`Backend failed: ${reason}.`)
  })
  onBackendStopped(() => {
    show("loader", false)
    show("status", false)
    setError("Backend stopped.")
  })

  if (retryBtn) {
    retryBtn.onclick = () => void handleRetry()
    retryBtn.style.display = "none"
  }

  void boot()
} else {
  // Not running under Tauri (web build): leave env to NEXT_PUBLIC_*.
}
