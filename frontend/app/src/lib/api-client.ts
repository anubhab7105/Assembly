import { env } from "./env"
import { z } from "zod"

// Zod schemas for backend responses
export const StartExecutionResponseSchema = z.object({
  id: z.string(),
  status: z.string(),
})

export type StartExecutionResponse = z.infer<typeof StartExecutionResponseSchema>

export const ExecutionStatusResponseSchema = z.object({
  id: z.string(),
  status: z.string(),
  events: z.array(z.any()), // Can be refined to ProgressEvent schema if needed
})

export type ExecutionStatusResponse = z.infer<typeof ExecutionStatusResponseSchema>

export class ApiClient {
  private static async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${env.apiUrl}${endpoint}`
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    })

    if (!response.ok) {
      throw new Error(`API Error: ${response.status} ${response.statusText}`)
    }

    return response.json()
  }

  static async startExecution(question: string, minutes: number): Promise<StartExecutionResponse> {
    const data = await this.request("/executions", {
      method: "POST",
      body: JSON.stringify({ question, tier_minutes: minutes }),
    })
    return StartExecutionResponseSchema.parse(data)
  }

  static async getExecution(id: string): Promise<ExecutionStatusResponse> {
    const data = await this.request(`/executions/${id}`)
    return ExecutionStatusResponseSchema.parse(data)
  }

  static async testKey(provider: string, key: string): Promise<{ status: "valid" | "rate_limited" | "invalid" }> {
    // In a real app this would call the backend.
    // Assuming backend endpoint: POST /providers/{provider}/test with body { key }
    try {
      const data = await this.request(`/providers/${provider}/test`, {
        method: "POST",
        body: JSON.stringify({ key }),
      })
      return data as { status: "valid" | "rate_limited" | "invalid" }
    } catch (e: any) {
      if (e.message.includes("429")) return { status: "rate_limited" }
      return { status: "invalid" }
    }
  }
}
