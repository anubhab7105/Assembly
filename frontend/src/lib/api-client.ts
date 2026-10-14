import { env } from "./env"

/** Model catalog shapes (GET /api/catalog). */
export interface CatalogModel {
  id: string
  family: string
  roles: string[]
  scope: string
}

export interface CatalogProvider {
  id: string
  enabled: boolean
  limits_ready: boolean
  limits_issue?: string | null
  key_url: string
  privacy_note?: string | null
  key_steps?: string[] | null
  key_notes?: string[] | null
  sensitive_signup?: string | null
  models: CatalogModel[]
}

export interface Catalog {
  providers: CatalogProvider[]
  families: string[]
  recommended_order?: string[]
  minimum_families?: number
  sensitive_signup_fallback?: string
}

export interface UsageEntry {
  provider: string
  model: string
  count: number
  tokens: number
}

export interface ModelSelection {
  selected: string[]
  pins: Record<string, string>
}

export interface RunStreamEvent {
  event_type: string
  [key: string]: unknown
}

export class ApiClient {
  private static headers(extra: Record<string, string> = {}): Record<string, string> {
    const auth: Record<string, string> = {}
    if (env.NEXT_PUBLIC_APP_MODE === "desktop" && env.desktopToken) {
      auth["X-Assembly-Token"] = env.desktopToken
    }
    return { "Content-Type": "application/json", ...auth, ...extra }
  }

  private static async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${env.apiUrl}${endpoint}`
    const response = await fetch(url, {
      ...options,
      headers: { ...this.headers(), ...options.headers },
    })
    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`)
    }
    return response.json() as Promise<T>
  }

  static catalog(): Promise<Catalog> {
    return this.request<Catalog>("/api/catalog")
  }

  static preflight(
    question: string,
    minutes: number,
    usage: UsageEntry[] = [],
    providerKeys: Record<string, string> = {},
    selection: ModelSelection = { selected: [], pins: {} },
  ) {
    return this.request("/api/preflight", {
      method: "POST",
      body: JSON.stringify({
        question,
        time_budget_minutes: minutes,
        provider_keys: providerKeys,
        model_selection: selection,
        usage_snapshot: usage,
      }),
    }) as Promise<{ feasible: boolean; explanation?: string; feasible_tier?: number }>
  }

  /** POST /api/run and stream SSE events to onEvent. Resolves on run.finished. */
  static async startRunStream(
    args: {
      question: string
      minutes: number
      providerKeys: Record<string, string>
      searchKeys?: Record<string, string>
      selection: ModelSelection
      usage: UsageEntry[]
      signal?: AbortSignal
    },
    onEvent: (event: RunStreamEvent) => void,
  ): Promise<{
    status: string
    usage: UsageEntry[]
    stage?: string
    errorCode?: string
    errorClass?: string
    message?: string
  }> {
    const response = await fetch(`${env.apiUrl}/api/run`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        question: args.question,
        time_budget_minutes: args.minutes,
        provider_keys: args.providerKeys,
        // Omitted when no search key exists: the server then uses its own
        // key where allowed, else keyless sources.
        ...(args.searchKeys && Object.keys(args.searchKeys).length > 0
          ? { search_keys: args.searchKeys }
          : {}),
        model_selection: args.selection,
        usage_snapshot: args.usage,
      }),
      signal: args.signal,
    })
    if (!response.ok || !response.body) {
      // Surface machine-readable server errors (e.g. blocked_no_usable_keys).
      let detail = `Run failed: ${response.status}`
      try {
        const data = (await response.json()) as { detail?: unknown; code?: unknown }
        if (typeof data.detail === "string" && data.detail) detail = data.detail
      } catch {
        // Non-JSON error body: keep the status text.
      }
      throw new Error(detail)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let status = "unknown"
    let usage: UsageEntry[] = []
    let finished = false
    let stage: string | undefined
    let errorCode: string | undefined
    let errorClass: string | undefined
    let message: string | undefined
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split("\n\n")
      buffer = parts.pop() ?? ""
      for (const part of parts) {
        const lines = part.split("\n").filter((l) => l.startsWith("data: "))
        for (const line of lines) {
          const event = JSON.parse(line.slice(6))
          onEvent(event)
          if (event.event_type === "run.finished") {
            finished = true
            status = event.status ?? "unknown"
            usage = event.usage ?? []
            if (typeof event.stage === "string") stage = event.stage
            if (typeof event.error_code === "string") errorCode = event.error_code
            if (typeof event.error_class === "string") errorClass = event.error_class
            if (typeof event.message === "string") message = event.message
          }
        }
      }
    }
    if (!finished) {
      throw new Error(
        "Run stream closed without completion (no run.finished). Check your connection and try again.",
      )
    }
    return { status, usage, stage, errorCode, errorClass, message }
  }

  static async cancelExecution(id: string): Promise<{ status: string }> {
    const data = await this.request<{ status: string }>(`/api/executions/${id}/cancel`, {
      method: "POST",
    })
    return data
  }

  static async testKey(
    provider: string,
    key: string,
  ): Promise<{
    status: "valid" | "rate_limited" | "invalid" | "model_unavailable" | "unreachable"
    message?: string
    availableModels?: string[]
  }> {
    try {
      const data = await this.request<{
        valid: boolean
        rate_limited: boolean
        error_code?: string | null
        message?: string | null
        available_models?: string[] | null
      }>(
        "/api/keys/test",
        { method: "POST", body: JSON.stringify({ provider, key }) },
      )
      const message = data.message ?? undefined
      const availableModels = data.available_models ?? undefined
      // Order matters: quota and model states ride on valid keys, so they
      // must win over the valid flag. Only an auth failure is "invalid".
      if (data.rate_limited) return { status: "rate_limited", message, availableModels }
      if (data.error_code === "model_not_found")
        return { status: "model_unavailable", message, availableModels }
      if (data.error_code === "unreachable")
        return { status: "unreachable", message, availableModels }
      if (data.valid) return { status: "valid", message, availableModels }
      return { status: "invalid", message, availableModels }
    } catch (e: unknown) {
      // The endpoint's own per-IP limiter answers HTTP 429: provider quota,
      // never an invalid key. Anything else means we never got an answer.
      if (String((e as Error)?.message ?? e).includes("429"))
        return { status: "rate_limited", message: "Too many test attempts; wait a minute and try again." }
      return { status: "unreachable", message: "Couldn't reach the server; try again." }
    }
  }

  static async clearAllKeys(): Promise<void> {
    await this.request("/api/keys", { method: "DELETE" })
  }

  static async wakeup(): Promise<void> {
    try {
      const baseUrl = env.apiUrl.endsWith("/api") ? env.apiUrl.replace("/api", "") : env.apiUrl
      await fetch(`${baseUrl}/health`).catch(() => {})
    } catch {
      // Ignore
    }
  }
}
