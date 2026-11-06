import {
  desktopIpc,
  isDesktop,
  BackendStatus,
  BackendState,
} from "./ipc";

const statusEl = document.getElementById("status")!;
const errorEl = document.getElementById("error")!;
const loaderEl = document.getElementById("loader")!;
const logLinkEl = document.getElementById("log-link")!;

let fullLogs = "";

logLinkEl.onclick = () => {
  alert("Backend Logs:\n\n" + fullLogs.substring(fullLogs.length - 1000));
};

function showError(message: string) {
  loaderEl.style.display = "none";
  statusEl.style.display = "none";
  errorEl.style.display = "block";
  errorEl.innerText = message;
  logLinkEl.style.display = "block";
}

function setStatus(text: string) {
  statusEl.innerText = text;
}

function renderLogs(lines: { stream: string; line: string }[]) {
  fullLogs = lines.map((l) => `[${l.stream}] ${l.line}`).join("\n");
}

async function pollUntilReady(maxSeconds = 30): Promise<BackendStatus> {
  const deadline = Date.now() + maxSeconds * 1000;
  while (Date.now() < deadline) {
    const status = await desktopIpc.backendStatus();
    if (status.state.type === "Ready") {
      return status;
    }
    if (status.state.type === "Failed" || status.state.type === "Crashed") {
      return status;
    }
    // Starting / Stopping: keep waiting.
    await new Promise((r) => setTimeout(r, 500));
  }
  return await desktopIpc.backendStatus();
}

function readyState(state: BackendState): Extract<BackendState, { type: "Ready" }> {
  if (state.type !== "Ready") {
    throw new Error("backend is not ready");
  }
  return state;
}

async function start() {
  if (!isDesktop()) {
    setStatus("Not running in desktop mode.");
    return;
  }

  loaderEl.style.display = "block";
  statusEl.style.display = "block";
  errorEl.style.display = "none";
  logLinkEl.style.display = "none";

  setStatus("Starting backend sidecar...");

  try {
    await desktopIpc.startBackend();
  } catch (err) {
    showError(`Failed to start backend: ${err instanceof Error ? err.message : String(err)}`);
    return;
  }

  setStatus("Waiting for backend to become ready...");
  const status = await pollUntilReady(30);

  if (status.state.type === "Ready") {
    renderLogs(await desktopIpc.backendLogs());
    const ready = readyState(status.state);
    // Expose the dynamic endpoint + token on window for the API client.
    (window as unknown as { ASSEMBLY_API_URL?: string; ASSEMBLY_TOKEN?: string }).ASSEMBLY_API_URL =
      status.endpoint ?? "";
    (window as unknown as { ASSEMBLY_TOKEN?: string }).ASSEMBLY_TOKEN = ready.token;

    setStatus("Backend ready. Loading frontend...");
    // Pass port/token in the URL for the next page load (secrets are not
    // written to localStorage/IndexedDB/sessionStorage).
    window.location.href = `/frontend/index.html?port=${ready.port}&token=${ready.token}`;
    return;
  }

  const reason =
    status.state.type === "Failed"
      ? status.state.reason
      : status.state.type === "Crashed"
        ? `Backend crashed (exit code ${status.state.code ?? "unknown"})`
        : "Backend failed to start";

  showError(`Backend unavailable: ${reason}`);
}

// Auto-retry once after a short backoff on crash/startup failure.
setTimeout(() => {
  const stillError = errorEl.style.display === "block";
  if (stillError) {
    start();
  }
}, 2500);

start();

// Expose a global retry hook for the host page.
(window as unknown as { __assembly_retry_backend?: () => void }).__assembly_retry_backend = start;

export {};
