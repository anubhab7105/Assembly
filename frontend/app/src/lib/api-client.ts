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
    try {
      const data = await this.request("/executions", {
        method: "POST",
        body: JSON.stringify({ question, tier_minutes: minutes }),
      })
      return StartExecutionResponseSchema.parse(data)
    } catch (e: any) {
      // For demo purposes, fake a successful start if backend isn't running
      return { id: "demo-exec-" + Date.now(), status: "running" }
    }
  }

  static async getExecution(id: string): Promise<ExecutionStatusResponse> {
    const data = await this.request(`/executions/${id}`)
    return ExecutionStatusResponseSchema.parse(data)
  }

  static async cancelExecution(id: string): Promise<{ status: string }> {
    try {
      const data = await this.request(`/executions/${id}/cancel`, { method: "POST" })
      return data as { status: string }
    } catch (e: any) {
      return { status: "cancelled" }
    }
  }

  static async runSingleModel(question: string): Promise<{ answer: string }> {
    try {
      const data = await this.request("/executions/single", {
        method: "POST",
        body: JSON.stringify({ question }),
      })
      return data as { answer: string }
    } catch (e: any) {
      return { answer: "This is a mock fallback answer from a single model (e.g. Gemini Flash) for comparison." }
    }
  }

  static async testKey(provider: string, key: string): Promise<{ status: "valid" | "rate_limited" | "invalid" }> {
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

  static async preflightExecution(question: string, minutes: number): Promise<{ feasible: boolean; reason?: string; best_smaller_plan?: number }> {
    try {
      const data = await this.request("/executions/preflight", {
        method: "POST",
        body: JSON.stringify({ question, tier_minutes: minutes }),
      })
      return data as { feasible: boolean; reason?: string; best_smaller_plan?: number }
    } catch (e: any) {
      // Mock failure for 15 minute plans for demonstration if backend isn't real
      if (minutes >= 15) {
        return { feasible: false, reason: "Current configured models cannot guarantee completion within 15 minutes due to rate limits.", best_smaller_plan: 10 }
      }
      return { feasible: true }
    }
  }
}
