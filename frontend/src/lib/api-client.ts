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
  key_url: string
  privacy_note?: string | null
  models: CatalogModel[]
}

export interface Catalog {
  providers: CatalogProvider[]
  families: string[]
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

  static preflight(question: string, minutes: number, usage: UsageEntry[] = []) {
    return this.request("/api/executions/preflight", {
      method: "POST",
      body: JSON.stringify({
        question,
        time_budget_minutes: minutes,
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
      selection: ModelSelection
      usage: UsageEntry[]
      signal?: AbortSignal
    },
    onEvent: (event: RunStreamEvent) => void,
  ): Promise<{ status: string; usage: UsageEntry[] }> {
    const response = await fetch(`${env.apiUrl}/api/run`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({
        question: args.question,
        time_budget_minutes: args.minutes,
        provider_keys: args.providerKeys,
        model_selection: args.selection,
        usage_snapshot: args.usage,
      }),
      signal: args.signal,
    })
    if (!response.ok || !response.body) {
      throw new Error(`Run failed: ${response.status}`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let status = "unknown"
    let usage: UsageEntry[] = []
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
            status = event.status ?? "unknown"
            usage = event.usage ?? []
          }
        }
      }
    }
    return { status, usage }
  }

  static async cancelExecution(id: string): Promise<{ status: string }> {
    const data = await this.request<{ status: string }>(`/api/executions/${id}/cancel`, {
      method: "POST",
    })
    return data
  }

  static async testKey(provider: string, key: string): Promise<{ status: "valid" | "rate_limited" | "invalid" }> {
    try {
      const data = await this.request<{ valid: boolean; rate_limited: boolean }>(
        "/api/keys/test",
        { method: "POST", body: JSON.stringify({ provider, key }) },
      )
      if (data.valid) return { status: "valid" }
      if (data.rate_limited) return { status: "rate_limited" }
      return { status: "invalid" }
    } catch (e: unknown) {
      if (String((e as Error)?.message ?? e).includes("429")) return { status: "rate_limited" }
      return { status: "invalid" }
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
